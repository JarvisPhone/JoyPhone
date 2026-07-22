# server/app/task/policies.py
from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass
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
    """策略裁决结果:continue 放行 / terminate 终止任务 / intercept 下发动作。"""

    kind: VerdictKind
    reason: str = ""
    status: str = ""
    actions: list[Action] | None = None


def continue_() -> Verdict:
    return Verdict(kind="continue")


def terminate(reason: str, status: str) -> Verdict:
    return Verdict(kind="terminate", reason=reason, status=status)


def intercept(actions: list[Action]) -> Verdict:
    return Verdict(kind="intercept", actions=actions)


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

    LLM 是无状态的:同一帧必然产出同一决策,若该决策无效(如面对
    无可用信息的屏幕反复 read),不拦截就会空转到预算耗尽。

    判定:即将下发的动作与「同一帧上已下过的动作」相同,且这是第
    Config.LOOP_GUARD_TRIGGER 次(容忍 1 次点空重试)。
    处置:不下发该动作,改发 back 机械脱困(最多 LOOP_GUARD_MAX_BACKS 次);
    仍循环直接 terminate(stuck_loop) 留现场查原因。帧或决策任一变化即重置。
    """

    name = "loop_guard"

    def inspect(self, frame: Perception | None, ctx: TaskContext) -> Verdict:
        if frame is None or not ctx.decided_actions:
            return continue_()
        fsig = frame_signature(frame)
        dsig = decision_signature(ctx.decided_actions)
        if fsig == ctx.loop_frame_sig and dsig == ctx.loop_decision_sig:
            ctx.loop_repeats += 1
        else:
            ctx.loop_frame_sig = fsig
            ctx.loop_decision_sig = dsig
            ctx.loop_repeats = 1
            ctx.loop_backs = 0

        if ctx.loop_repeats < Config.LOOP_GUARD_TRIGGER:
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
        return intercept([Action(actionId=str(uuid.uuid4()), op="back", params={})])


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
            return verdict
    return continue_()
