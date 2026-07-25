# server/app/task/policies.py
from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal, Protocol, Sequence

from app.infra.config import Config
from app.protocol import Action, Perception
from app.task.context import TaskContext
from app.task.fsm import TaskState

logger = logging.getLogger(__name__)

VerdictKind = Literal["continue", "terminate", "intercept"]


@dataclass(frozen=True)
class Verdict:
    """策略裁决结果:continue 放行 / terminate 终止任务 / intercept 下发动作。

    policy 由 run_pipeline 在短路返回时填充(裁决来源策略名),
    供 LLM 反馈通道说明「被谁拦截」。
    """

    kind: VerdictKind
    reason: str = ""
    status: str = ""
    actions: list[Action] | None = None
    policy: str = ""


def continue_() -> Verdict:
    return Verdict(kind="continue")


def terminate(reason: str, status: str) -> Verdict:
    return Verdict(kind="terminate", reason=reason, status=status)


def intercept(actions: list[Action], reason: str = "") -> Verdict:
    """策略拦截:下发替换动作并说明原因。

    reason 写进 verdict,handlers.py 据此构造 LLM feedback,
    让 LLM 区分「动作未生效已改发 read_screen 等稳定」与
    「动作重复,已改发 back 脱困」。
    """
    return Verdict(kind="intercept", actions=actions, reason=reason)


class Policy(Protocol):
    """策略协议:对感知帧与任务上下文做检查,返回裁决。"""

    name: str

    def inspect(self, frame: Perception | None, ctx: TaskContext) -> Verdict: ...


class BudgetPolicy:
    """步数预算:ctx.steps 达到 max_steps 即终止任务。"""

    name = "budget"

    def inspect(self, frame: Perception | None, ctx: TaskContext) -> Verdict:
        if ctx.steps >= ctx.max_steps:
            logger.info(
                "步数预算耗尽: task_id=%s steps=%s max_steps=%s",
                ctx.task_id,
                ctx.steps,
                ctx.max_steps,
            )
            return terminate("budget_exhausted", "aborted")
        return continue_()


class ConfirmTimeoutPolicy:
    """确认超时:AWAITING_CONFIRM 超过阈值即终止任务。"""

    name = "confirm_timeout"

    def inspect(self, frame: Perception | None, ctx: TaskContext) -> Verdict:
        if ctx.fsm.check_awaiting_confirm_timeout(datetime.now()):
            logger.info("确认等待超时: task_id=%s", ctx.task_id)
            return terminate("confirm_timeout", "aborted")
        return continue_()


# ---- 停滞/循环检测(帧签名 × 决策签名)----


def frame_signature(frame: Perception) -> str:
    """帧签名:pkg + 各节点 (text/desc/rid/editable/clickable) 的哈希。

    屏幕内容任一可见变化都会改变签名;滚动列表 swipe 后内容变了,
    签名随之变化,不会被误判为停滞。
    """
    h = hashlib.md5()
    h.update((frame.pkg or "").encode())
    for n in frame.nodeTree:
        h.update((n.text or "").strip().encode())
        h.update(b"|")
        h.update((n.desc or "").strip().encode())
        h.update(b"|")
        h.update((n.viewIdResourceName or "").encode())
        h.update(b"|")
        h.update(b"e" if n.editable else b"-")
        h.update(b"c" if n.clickable else b"-")
        h.update(b";")
    return h.hexdigest()


def decision_signature(actions: Sequence[Action]) -> str:
    """决策签名:op + 语义锚点(优先 match_text/text/desc,退化坐标)。"""
    parts: list[str] = []
    for a in actions:
        p = a.params or {}
        anchor = (
            p.get("match_text") or p.get("text") or p.get("desc")
            or p.get("direction") or p.get("ms")
            or ("%s,%s" % (p.get("x"), p.get("y")) if p.get("x") else "")
        )
        parts.append("%s:%s" % (a.op, anchor))
    return ";".join(parts)


class LoopGuardPolicy:
    """停滞/循环守卫(内核策略,对所有任务生效)。

    ack 只代表手势已派发,不代表 UI 已生效:ack 后的抓帧常是「动作生效前
    的旧画面」,此时重复下发必点歪/退过头(真机七轮:重复 tap 群名命中
    聊天页标题进设置、重复 back 退过头、confirm 落在旧帧补发失败)。

    处置阶梯(同一(帧,决策)的连续重复次数):
      第 LOOP_GUARD_SETTLE(2) 次:压下动作改发 read_screen,等 UI 稳定;
      第 3 次:两帧未变确认动作真未生效,放行真·重试;
      第 LOOP_GUARD_BACK(4) 次起:机械 back 脱困(≤LOOP_GUARD_MAX_BACKS 次),
      仍循环 terminate(stuck_loop)。帧或决策任一变化即重置。

    额外检测「back+home 振荡」:LLM 进入「找不出路」的状态时,常表现
    为 back→home→back→home 反复。该模式不触发帧签名重复(每帧 pkg
    在切换),单凭(帧,决策)签名无法捕获。统计 guard["op_recent"] 最近
    OP_BACKOFF_WINDOW 个 op,发现 back/home 交替 ≥ OP_BACKHOME_THRESHOLD 次
    判定为「退出路径迷失」,给 LLM 一次明确的「当前 scene + exit_hint」
    反馈,而不是放任它继续振荡。
    """

    name = "loop_guard"

    OP_BACKOFF_WINDOW = 6      # 最近 op 滑窗长度
    OP_BACKHOME_THRESHOLD = 3  # 窗内 back/home 交替达此阈值判定振荡
    EXIT_LOSER_HINT_REPEATS = 2  # 振荡命中后压下 N 帧直接 read_screen

    def inspect(self, frame: Perception | None, ctx: TaskContext) -> Verdict:
        if frame is None or not ctx.decided_actions:
            return continue_()

        # --- 记录最近 op 序列(供 back+home 振荡检测)---
        gd = ctx.guard if isinstance(ctx.guard, dict) else {}
        recent: list[str] = list(gd.get("op_recent") or [])
        for a in ctx.decided_actions:
            op = a.op
            if op in ("back", "home", "swipe"):
                recent.append(op)
        if len(recent) > self.OP_BACKOFF_WINDOW:
            recent = recent[-self.OP_BACKOFF_WINDOW:]
        gd["op_recent"] = recent

        # back+home 振荡模式:相邻项交替且次数达阈值
        # 例: ["back","home","back","home","back","home"] → 5 个交替
        alternating_pairs = 0
        for i in range(1, len(recent)):
            if {recent[i - 1], recent[i]} == {"back", "home"}:
                alternating_pairs += 1
        oscillating_backhome = (
            alternating_pairs >= self.OP_BACKHOME_THRESHOLD
            and any(o == "back" for o in recent)
            and any(o == "home" for o in recent)
        )

        # 振荡命中后压下 N 帧直接 read_screen,并把当前 scene + exit_hint
        # 反馈给 LLM,让它重读一下当前布局再决策
        if oscillating_backhome:
            gd["loop_backhome_hits"] = gd.get("loop_backhome_hits", 0) + 1
            if gd["loop_backhome_hits"] <= self.EXIT_LOSER_HINT_REPEATS:
                hint = self._build_exit_loser_hint(frame)
                logger.warning(
                    "[LOOP_BACKHOME] task_id=%s op_recent=%s hits=%d, 压下读帧+给 exit_hint",
                    ctx.task_id, recent, gd["loop_backhome_hits"],
                )
                return intercept(
                    [Action(actionId=str(uuid.uuid4()), op="read_screen", params={})],
                    reason=hint,
                )

        # --- 标准 (帧,决策) 停滞检测 ---
        fsig = frame_signature(frame)
        dsig = decision_signature(ctx.decided_actions)
        if fsig == ctx.loop_frame_sig and dsig == ctx.loop_decision_sig:
            ctx.loop_repeats += 1
        else:
            ctx.loop_frame_sig = fsig
            ctx.loop_decision_sig = dsig
            ctx.loop_repeats = 1
            ctx.loop_backs = 0

        if ctx.loop_repeats < Config.LOOP_GUARD_SETTLE:
            return continue_()
        if ctx.loop_repeats == Config.LOOP_GUARD_SETTLE:
            logger.info(
                "[LOOP_GUARD_SETTLE] task_id=%s 同帧同决策第 2 次,压下等稳定",
                ctx.task_id,
            )
            return intercept([Action(actionId=str(uuid.uuid4()),
                                     op="read_screen", params={})],
                             reason="动作可能未生效,等帧稳定")
        if ctx.loop_repeats < Config.LOOP_GUARD_BACK:
            return continue_()
        if ctx.loop_backs >= Config.LOOP_GUARD_MAX_BACKS:
            logger.error(
                "[LOOP_GUARD_ABORT] task_id=%s back %d 次仍循环,放弃",
                ctx.task_id, ctx.loop_backs,
            )
            ctx.fsm.transition(TaskState.ABORT, reason=self.name)
            return terminate("stuck_loop", "aborted")
        ctx.loop_backs += 1
        logger.warning(
            "[LOOP_GUARD] task_id=%s 第 %d 次相同(帧,决策),改发 back (%d/%d)",
            ctx.task_id, ctx.loop_repeats, ctx.loop_backs, Config.LOOP_GUARD_MAX_BACKS,
        )
        return intercept([Action(actionId=str(uuid.uuid4()), op="back", params={})],
                         reason="动作重复未生效,执行 back 脱困")

    @staticmethod
    def _build_exit_loser_hint(frame: Perception) -> str:
        """构造「退出路径迷失」反馈文本,让 LLM 重读 exit_hint 再决策。"""
        from app.decision.app_page import AppPage, detect_app_page
        from app.decision.exit_hint import exit_hint
        from app.decision.pkg_guard import Scene, detect_scene
        scene = detect_scene(frame)
        page = detect_app_page(frame) if scene == Scene.IN_APP else AppPage.UNKNOWN
        hint = exit_hint(scene, page)
        return (
            f"检测到 back+home 振荡({LoopGuardPolicy.OP_BACKHOME_THRESHOLD}+ 次交替),"
            f"说明你在「找出去的路」时反复横跳。当前 scene={scene.value} "
            f"page={page.value},标准退出路径:{hint}。"
            f"请停止 back+home,严格按 exit_hint 单步退出后再 read 看新画面。"
        )


def run_pipeline(
    policies: Sequence[Policy],
    frame: Perception | None,
    ctx: TaskContext,
) -> Verdict:
    """顺序执行策略,首个非 continue 裁决短路返回;全部通过则 continue。"""
    for policy in policies:
        verdict = policy.inspect(frame, ctx)
        if verdict.kind != "continue":
            logger.info(
                "策略管道短路: task_id=%s policy=%s kind=%s reason=%s",
                ctx.task_id,
                policy.name,
                verdict.kind,
                verdict.reason,
            )
            return replace(verdict, policy=policy.name)
    return continue_()
