"""send_message 场景包:意图匹配、目标解析、技能模板与五道策略。

五道策略从旧 gateway.py(0d1ccbd)对应代码段原样抽取并管道化:
  - PostSendForceDonePolicy  <- :386-405(发送回执后强制 done)
  - PostSendPatrolPolicy     <- :409-426(发送后 LLM 继续操作,巡逻计数强 abort)
  - PreSendRevertPolicy      <- :437-484(AWAITING_CONFIRM 10s 反向操作观察窗)
  - ConfirmInterceptPolicy   <- :546-586(tap 发送按钮前拦截,转 task.confirm)
  - WrongChatInputPolicy     <- :592-638(错群输正文守卫,back / 阈值强 abort)

管道化差异(相对旧代码):策略不直接收发消息,返回 Verdict 由调用方
(T11)下发 TaskAbort/TaskDone/TaskConfirm/动作;状态迁移在策略内走
ctx.fsm.transition(..., reason=policy_name)。硬编码数字改读 Config。
后置策略(Confirm/WrongChat)经 ctx.decided_actions 读取本帧决策动作。
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field

from app.decision.skills import SkillStep, SkillTemplate
from app.decision.ui_inspect import detect_title
from app.infra.config import Config
from app.protocol import Action, Node, Perception
from app.scenario.base import AppProfile
from app.scenario.profiles import ALL_PROFILES, FEISHU_PROFILE, WECHAT_PROFILE
from app.scenario.ui import (
    extract_target,
    is_message_input,
    is_send_button,
    match_title,
    resolve_anchor_node,
    resolve_pkg,
)
from app.task.context import TaskContext
from app.task.fsm import TaskState
from app.task.policies import Verdict, continue_, intercept, terminate

logger = logging.getLogger(__name__)

_LAUNCHER_VIEW_KEYWORDS = ("launcher", "systemui", "inputmethod")
_SEND_INTENT_KEYWORDS = ("发", "发送", "发给", "message")


@dataclass(frozen=True)
class ResolvedTarget:
    """send_message 场景的目标解析结果;chat 为 None 时 bindings 为空。"""

    pkg: str
    chat: str | None
    bindings: dict[str, str] = field(default_factory=dict)


# ---- 帧内 UI 判定 helpers(移植旧 gateway.py 模块级私有函数,关键词走 AppProfile)----


def _detect_chat_title(nodes: list[Node], profile: AppProfile) -> str | None:
    return detect_title(nodes, tuple(profile.title_rid_keywords))


def _tap_hits_send_button(action: Action, nodes: list[Node], profile: AppProfile) -> bool:
    """判断 tap action 是否命中当前屏的「发送」按钮(语义锚点解析)。"""
    node = resolve_anchor_node(action.params, nodes)
    return node is not None and is_send_button(node, profile)


def _input_target_node(action: Action, nodes: list[Node]) -> Node | None:
    """把 input action 还原为被输入的目标 editable 节点(语义锚点解析)。"""
    node = resolve_anchor_node(action.params, nodes)
    return node if (node is not None and node.editable) else None


def _draft_text_in_frame(nodes: list[Node]) -> str:
    """输入框当前文本(残留草稿):第一个有文本的 editable 节点的 text。

    仅在「标题匹配的会话页 + 发送 tap」语境下调用,此时的 editable 即消息框。
    """
    for n in nodes:
        if n.editable and (n.text or "").strip():
            return (n.text or "").strip()
    return ""


def _extract_last_input_text(applied_steps: list[dict]) -> str:
    """从 applied_steps 里取最近一条 input 文本,作为 confirm 预览。"""
    for step in reversed(applied_steps):
        if step.get("op") == "input":
            text = step.get("params", {}).get("text", "")
            if text:
                return text
    return ""


def _profile_for(ctx: TaskContext) -> AppProfile | None:
    for profile in (FEISHU_PROFILE, WECHAT_PROFILE):
        if profile.pkg == ctx.target_pkg:
            return profile
    return None


# ---- 前置策略(决策前,perception 帧驱动)----


class PreSendRevertPolicy:
    """AWAITING_CONFIRM 反向操作观察窗(旧 :437-484)。

    confirm 发出后 PRE_SEND_REVERT_WINDOW_SEC 秒内,uplink.pkg 切到
    launcher/systemui/inputmethod 视作用户主动撤回 -> terminate(aborted);
    窗口外仍切走按 confirm_rejected:app_left_during_confirm 处理。
    """

    name = "pre_send_revert"

    def inspect(self, frame: Perception | None, ctx: TaskContext) -> Verdict:
        if frame is None:
            return continue_()
        if ctx.fsm.state != TaskState.AWAITING_CONFIRM:
            return continue_()
        if ctx.confirm.sent_ts is None or not ctx.target_pkg:
            return continue_()

        pkg = frame.pkg or ""
        within_window = (time.monotonic() - ctx.confirm.sent_ts) <= Config.PRE_SEND_REVERT_WINDOW_SEC
        pkg_left_app = bool(pkg) and pkg != ctx.target_pkg
        pkg_is_launcher_view = any(k in pkg.lower() for k in _LAUNCHER_VIEW_KEYWORDS)

        if within_window and pkg_left_app and pkg_is_launcher_view:
            elapsed = time.monotonic() - ctx.confirm.sent_ts
            logger.warning(
                "[PRE_SEND_USER_REVERTED] window=%.2fs pkg=%s -> target_pkg=%s, abort",
                elapsed, pkg, ctx.target_pkg,
            )
            ctx.confirm.reverted = True
            ctx.confirm.confirm_id = None
            ctx.confirm.pending_action = None
            ctx.fsm.transition(TaskState.ABORT, reason=self.name)
            return terminate("pre_send_user_reverted", "aborted")

        if not within_window and pkg_left_app:
            logger.info(
                "[CONFIRM_CANCELLED] pkg=%s != target=%s during AWAITING_CONFIRM -> auto reject",
                pkg, ctx.target_pkg,
            )
            ctx.confirm.confirm_id = None
            ctx.confirm.pending_action = None
            ctx.fsm.transition(TaskState.ABORT, reason=self.name)
            return terminate("confirm_rejected:app_left_during_confirm", "aborted")

        return continue_()


class PostSendForceDonePolicy:
    """发送回执后强制 done(旧 :386-405)。

    acked + 仍在目标 app + 标题匹配目标群 -> terminate(completed),
    无视 LLM 是否输出 done。
    """

    name = "post_send_force_done"

    def inspect(self, frame: Perception | None, ctx: TaskContext) -> Verdict:
        if frame is None:
            return continue_()
        if not (ctx.post_send.acked and ctx.target_pkg and ctx.target_chat):
            return continue_()
        if frame.pkg != ctx.target_pkg:
            return continue_()
        profile = _profile_for(ctx)
        if profile is None:
            return continue_()
        current_title = _detect_chat_title(frame.nodeTree, profile)
        if current_title and match_title(ctx.target_chat, current_title):
            logger.info(
                "[POST_SEND_FORCE_DONE] sent_acked=True pkg=%s title=%s match",
                frame.pkg, current_title,
            )
            ctx.fsm.transition(TaskState.DONE, reason=self.name)
            return terminate("post_send_auto_done", "completed")
        return continue_()


class PostSendPatrolPolicy:
    """发送后巡逻(旧 :409-426)。

    acked 后每帧 patrol_count += 1,达到 POST_SEND_PATROL_THRESHOLD
    说明 LLM 发送成功还在继续操作 -> terminate(aborted)。
    """

    name = "post_send_patrol"

    def inspect(self, frame: Perception | None, ctx: TaskContext) -> Verdict:
        if not ctx.post_send.acked:
            return continue_()
        ctx.post_send.patrol_count += 1
        if ctx.post_send.patrol_count >= Config.POST_SEND_PATROL_THRESHOLD:
            logger.warning(
                "[POST_SEND_PATROL_ABORT] sent_acked=True but LLM continued %d frames",
                ctx.post_send.patrol_count,
            )
            ctx.fsm.transition(TaskState.ABORT, reason=self.name)
            return terminate("post_send_patrol:llm_continued_after_send", "aborted")
        return continue_()


# ---- 后置策略(决策后,经 ctx.decided_actions 读取本帧动作)----


class SidebarDismissPolicy:
    """侧边栏抽屉消除(pre-policy,机械,不问 LLM 省一次决策延迟)。

    飞书个人主页左侧抽屉跨启动持久化,back 无效、重启复现,LLM 面对它
    会死循环(真机六轮 pkg_guard_stuck)。人类操作是点右侧空白消除——
    特征 rid 命中 ≥2 个即判定抽屉页,tap_at 特征节点右缘外 48px。
    连续消除上限 2 次(特征消失即重置),失败交还 LLM。
    """

    name = "sidebar_dismiss"
    MAX_DISMISS = 2
    _TAP_MARGIN_PX = 48

    def inspect(self, frame: Perception | None, ctx: TaskContext) -> Verdict:
        if frame is None or not ctx.target_pkg or frame.pkg != ctx.target_pkg:
            return continue_()
        profile = _profile_for(ctx)
        if profile is None or not profile.sidebar_rid_keywords:
            return continue_()
        keywords = tuple(profile.sidebar_rid_keywords)
        hits = [
            n for n in frame.nodeTree
            if any(kw in (n.viewIdResourceName or "") for kw in keywords)
        ]
        if len(hits) < 2:
            ctx.sidebar_dismiss_count = 0
            return continue_()
        if ctx.sidebar_dismiss_count >= self.MAX_DISMISS:
            logger.warning(
                "[SIDEBAR_DISMISS_CAP] task_id=%s 连续 %d 次消除未果,交还 LLM",
                ctx.task_id, ctx.sidebar_dismiss_count,
            )
            return continue_()
        rights = [n.bounds[2] for n in hits if n.bounds and len(n.bounds) == 4]
        bottoms = [n.bounds[3] for n in hits if n.bounds and len(n.bounds) == 4]
        if not rights or not bottoms:
            return continue_()
        ctx.sidebar_dismiss_count += 1
        x = max(rights) + self._TAP_MARGIN_PX
        y = max(bottoms) // 2
        logger.info(
            "[SIDEBAR_DISMISS] task_id=%s 抽屉特征 %d 个,tap_at (%d,%d)",
            ctx.task_id, len(hits), x, y,
        )
        return intercept([Action(
            actionId=str(uuid.uuid4()), op="tap_at",
            params={"x": str(x), "y": str(y)},
        )])


class SendGuardPolicy:
    """done 门槛:未真实发送(post_send.acked=False)时拦截 LLM 的幻觉 done。

    拦截后剥掉 done 改发 read_screen 让决策继续——若真的万事俱备,LLM 下一帧
    会 tap 发送按钮,由 ConfirmInterceptPolicy 接管确认流,正确闭环。
    连续拦截达 Config.SEND_GUARD_MAX 说明 LLM 陷入幻觉循环,强 abort。
    """

    name = "send_guard"

    def inspect(self, frame: Perception | None, ctx: TaskContext) -> Verdict:
        if frame is None:
            return continue_()
        if not (ctx.target_pkg and ctx.target_chat):
            return continue_()
        if frame.pkg != ctx.target_pkg:
            return continue_()
        if ctx.post_send.acked:
            return continue_()
        if not any(a.op == "done" for a in ctx.decided_actions):
            return continue_()
        ctx.send_guard_count += 1
        logger.warning(
            "[SEND_GUARD] 拦截幻觉 done(未检测到发送行为)task_id=%s count=%d",
            ctx.task_id, ctx.send_guard_count,
        )
        if ctx.send_guard_count >= Config.SEND_GUARD_MAX:
            logger.error(
                "[SEND_GUARD_ABORT] 连续 %d 次幻觉 done,强 abort", ctx.send_guard_count
            )
            ctx.fsm.transition(TaskState.ABORT, reason=self.name)
            return terminate("send_guard:premature_done_loop", "aborted")
        return intercept([Action(actionId=str(uuid.uuid4()), op="read_screen", params={})])


class TitleTapGuardPolicy:
    """标题栏点击守卫:目标 app 内,decided tap 锚点解析到标题栏节点一律拦截。

    点标题在任何会话页都没有任务价值(只会误入群设置),不靠 LLM 自觉。
    真机两轮事故:LLM 把 prompt「核对标题」误解为「点击标题」;
    以及 tap 66(btn send) 转录成 tap 46(标题栏)。
    """

    name = "title_tap_guard"

    def inspect(self, frame: Perception | None, ctx: TaskContext) -> Verdict:
        if frame is None or not ctx.target_pkg or frame.pkg != ctx.target_pkg:
            return continue_()
        profile = _profile_for(ctx)
        if profile is None:
            return continue_()
        keywords = tuple(kw.lower() for kw in profile.title_rid_keywords)
        for action in ctx.decided_actions:
            if action.op != "tap":
                continue
            node = resolve_anchor_node(action.params, frame.nodeTree)
            if node is None:
                continue
            rid = (node.viewIdResourceName or "").rsplit("/", 1)[-1].lower()
            if rid and any(kw in rid for kw in keywords):
                logger.info(
                    "[TITLE_TAP_GUARD] 拦截标题栏点击: task_id=%s rid=%s",
                    ctx.task_id, rid,
                )
                return intercept([
                    Action(actionId=str(uuid.uuid4()), op="read_screen", params={})
                ])
        return continue_()


class ConfirmInterceptPolicy:
    """tap 发送按钮拦截(旧 :546-586)。

    LLM 决策「tap 发送按钮」且当前在目标会话(标题匹配)时:不下发该 tap,
    把动作存入 ctx.confirm(pending_action/confirm_id/message_text/sent_ts),
    迁移 AWAITING_CONFIRM,返回 intercept([]) 由调用方改发 task.confirm。
    confirm.count 达到 MAX_CONFIRM_COUNT 后不再拦截(旧 confirm_count == 0 等价)。
    """

    name = "confirm_intercept"

    def inspect(self, frame: Perception | None, ctx: TaskContext) -> Verdict:
        if frame is None:
            return continue_()
        if not (ctx.target_pkg and ctx.target_chat):
            return continue_()
        if frame.pkg != ctx.target_pkg:
            return continue_()
        if ctx.confirm.count >= Config.MAX_CONFIRM_COUNT:
            return continue_()
        profile = _profile_for(ctx)
        if profile is None:
            return continue_()

        for action in ctx.decided_actions:
            if action.op != "tap":
                continue
            current_title = _detect_chat_title(frame.nodeTree, profile)
            if not (
                current_title
                and match_title(ctx.target_chat, current_title)
                and _tap_hits_send_button(action, frame.nodeTree, profile)
            ):
                continue
            message_text = _extract_last_input_text(ctx.applied_steps)
            if not message_text:
                # 本任务没有 input 记录时,取输入框当前文本(上次残留的草稿):
                # 草稿发送同样要过人审,不能因 text 非本任务所输就跳过确认。
                message_text = _draft_text_in_frame(frame.nodeTree)
            if not message_text:
                # 无 input 正文时点发送:不进确认流(message="" 的确认无意义,
                # 且空输入框点发送本就无效)。透传该 tap,让 LLM 看到屏幕
                # 未变化后意识到需要先输入(2026-07-22 真机:LLM 跳过 input
                # 直接点发送,确认弹窗 message 为空)。
                logger.info(
                    "[CONFIRM_SKIP_EMPTY] 无 input 正文,发送 tap 透传不拦截: task_id=%s",
                    ctx.task_id,
                )
                continue
            confirm_id = "%s-%s" % (
                Config.CONFIRM_ID_PREFIX,
                uuid.uuid4().hex[: Config.CONFIRM_ID_LENGTH],
            )
            ctx.confirm.confirm_id = confirm_id
            ctx.confirm.pending_action = action
            ctx.confirm.message_text = message_text
            ctx.confirm.sent_ts = time.monotonic()
            ctx.confirm.reverted = False
            ctx.fsm.transition(TaskState.AWAITING_CONFIRM, reason=self.name)
            ctx.confirm.count += 1
            logger.info(
                "[CONFIRM_SENT] target=%s current=%s msg=%r (send tap intercepted)",
                ctx.target_chat, current_title, ctx.confirm.message_text,
            )
            return intercept([])
        return continue_()


class WrongChatInputPolicy:
    """错群 input 正文守卫(旧 :592-638)。

    LLM 决策「往聊天正文输入框输正文」而标题不匹配(进错群)时:未达阈值
    拦截该 input 改下发 back;达到 WRONG_CHAT_INPUT_THRESHOLD 强 abort,
    防止「tap 不匹配项 -> back -> 下一项 -> input」循环死锁。
    搜索框输入(is_message_input=False)不进此分支。
    """

    name = "wrong_chat_input"

    def inspect(self, frame: Perception | None, ctx: TaskContext) -> Verdict:
        if frame is None:
            return continue_()
        if not (ctx.target_pkg and ctx.target_chat):
            return continue_()
        if frame.pkg != ctx.target_pkg:
            return continue_()
        profile = _profile_for(ctx)
        if profile is None:
            return continue_()

        for action in ctx.decided_actions:
            if action.op != "input":
                continue
            input_node = _input_target_node(action, frame.nodeTree)
            if input_node is None or not is_message_input(input_node, profile):
                continue
            current_title = _detect_chat_title(frame.nodeTree, profile)
            if current_title and match_title(ctx.target_chat, current_title):
                continue
            logger.warning(
                "[INPUT_GUARD] target=%s current=%s text=%r "
                "(message input in wrong chat intercepted, forcing back)",
                ctx.target_chat, current_title, action.params.get("text", ""),
            )
            ctx.wrong_chat_input_count += 1
            if ctx.wrong_chat_input_count >= Config.WRONG_CHAT_INPUT_THRESHOLD:
                logger.error(
                    "[INPUT_GUARD_ABORT] wrong_chat_input_count=%d, force abort",
                    ctx.wrong_chat_input_count,
                )
                ctx.fsm.transition(TaskState.ABORT, reason=self.name)
                return terminate(
                    "wrong_chat_repeated:%d" % ctx.wrong_chat_input_count, "aborted"
                )
            return intercept([Action(actionId=str(uuid.uuid4()), op="back", params={})])
        return continue_()


# ---- 场景包 ----


class SendMessagePack:
    """发消息场景:飞书/微信等聊天 app 的「给 X 发消息」。"""

    name = "send_message"

    def matches(self, goal: str) -> float:
        if not goal:
            return 0.0
        if resolve_pkg(goal, ALL_PROFILES) is None:
            return 0.0
        if any(k in goal for k in _SEND_INTENT_KEYWORDS):
            return 0.9
        return 0.0

    def resolve_target(self, goal: str) -> ResolvedTarget:
        pkg = resolve_pkg(goal, ALL_PROFILES) or ""
        chat = extract_target(goal)
        bindings = {"contact": chat, "query": chat} if chat else {}
        return ResolvedTarget(pkg=pkg, chat=chat, bindings=bindings)

    def skills(self) -> list[SkillTemplate]:
        return [
            SkillTemplate(
                name="feishu_send_message",
                params=["contact"],
                app=FEISHU_PROFILE.pkg,
                keywords=["飞书", "发送", "消息", "发给", "发给"],
                steps=[
                    SkillStep(op="tap", desc="搜索"),
                    SkillStep(op="tap", text="搜索"),
                    SkillStep(op="input", input_text="{contact}"),
                    # 强制先比对顶部标题再 tap,避免反复点进同一个非目标群。
                    SkillStep(op="verify_title", match_text="{contact}"),
                    SkillStep(op="tap", text="发送"),
                ],
            ),
            SkillTemplate(
                name="feishu_search_contact",
                params=["query"],
                app=FEISHU_PROFILE.pkg,
                keywords=["搜索", "找", "联系人", "找人"],
                steps=[
                    SkillStep(op="tap", desc="搜索"),
                    SkillStep(op="input", input_text="{query}"),
                ],
            ),
        ]

    def pre_policies(self) -> list:
        return [
            SidebarDismissPolicy(),
            PreSendRevertPolicy(),
            PostSendForceDonePolicy(),
            PostSendPatrolPolicy(),
        ]

    def post_policies(self) -> list:
        return [
            TitleTapGuardPolicy(),
            SendGuardPolicy(),
            ConfirmInterceptPolicy(),
            WrongChatInputPolicy(),
        ]

    def classify_entry(self, frame: Perception, ctx: TaskContext) -> str:
        """进入目标 app 的落地页分类:学习与回放按入口状态分开。

        保守策略:只识别「已在目标会话」这一种可行动状态(用于 skill cursor
        快进),其余一律 unknown——避免误判后在别人群里乱 back。
        """
        profile = _profile_for(ctx)
        if profile is None:
            return "unknown"
        title = _detect_chat_title(frame.nodeTree, profile)
        if title and ctx.target_chat and match_title(ctx.target_chat, title):
            return "target_chat"
        return "unknown"

    def ui_profile(self, pkg: str) -> AppProfile | None:
        if pkg == FEISHU_PROFILE.pkg:
            return FEISHU_PROFILE
        if pkg == WECHAT_PROFILE.pkg:
            return WECHAT_PROFILE
        return None
