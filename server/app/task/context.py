# server/app/task/context.py
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from app.decision.skills import BoundSkill, SkillCursor
from app.infra.config import Config
from app.protocol import Action
from app.task.fsm import TaskFSM, TaskState

logger = logging.getLogger(__name__)


@dataclass
class ConfirmState:
    """确认拦截的 per-task 状态。

    pending_action 为待确认的下行 Action;count 用于配合
    Config.MAX_CONFIRM_COUNT 限制重复确认次数。
    """

    pending_action: Action | None = None
    confirm_id: str | None = None
    sent_ts: float | None = None
    reverted: bool = False
    count: int = 0
    message_text: str = ""


@dataclass
class PostSendState:
    """发送后巡逻状态:acked 表示已收到目标侧回执。"""

    acked: bool = False
    patrol_count: int = 0


@dataclass
class TaskContext:
    """唯一 per-task 状态载体(spec 3.2)。

    每个任务整体新建 TaskContext,不复用上一任务的任何字段(N3 回归)。
    fsm 由 TaskStore.new_task 负责从 IDLE force 到 RUNNING。
    """

    task_id: str
    goal: str
    fsm: TaskFSM
    steps: int = 0
    cursor: SkillCursor = field(default_factory=SkillCursor)
    history: list[dict] = field(default_factory=list)
    applied_steps: list[dict] = field(default_factory=list)
    target_pkg: str = ""
    target_chat: str | None = None
    bindings: dict[str, str] = field(default_factory=dict)
    bound_skill: BoundSkill | None = None
    confirm: ConfirmState = field(default_factory=ConfirmState)
    post_send: PostSendState = field(default_factory=PostSendState)
    # INPUT_GUARD 计数:错群输正文的次数,配合 Config.WRONG_CHAT_INPUT_THRESHOLD。
    wrong_chat_input_count: int = 0
    # SEND_GUARD 计数:未真实发送的幻觉 done 被拦截次数,配合 Config.SEND_GUARD_MAX。
    send_guard_count: int = 0
    # LOOP_GUARD 状态:最近一次的(帧签名,决策签名)与重复次数/已 back 次数。
    # 同一(帧,决策)重复达 Config.LOOP_GUARD_TRIGGER 判定停滞,机械 back 脱困;
    # 任一变化即重置。
    loop_frame_sig: str = ""
    loop_decision_sig: str = ""
    loop_repeats: int = 0
    loop_backs: int = 0
    # SIDEBAR_DISMISS 计数:连续侧边栏消除 tap_at 次数,特征消失即重置。
    # SIDEBAR_DISMISS 计数:连续侧边栏消除 tap_at 次数,特征消失即重置。
    sidebar_dismiss_count: int = 0
    # LLM 反馈通道(一次性):上一条指令的执行失败/策略拦截/expect 判定结果,
    # 随下一帧 decide 的 payload 送达 LLM 后清空。沉默=成功。
    llm_feedback: str = ""
    # 进入目标 app 的落地页分类(target_chat/unknown 等,由场景包 classify_entry)。
    # 每次进入 app 的落地页可能不同(冷启动在主页/热启动在上次聊天页),
    # 学习与回放都按入口状态分开进行。
    entry_state: str | None = None
    # cache 查询上下文:首次进入目标 app 时置为 "{pkg}|{entry_state}"。
    cache_context: str = ""
    # 回放熔断:cache 同一步连续 ack 失败达 Config.CACHE_STEP_MAX_FAILS 后本场禁用。
    cache_disabled: bool = False
    cache_step_fails: int = 0
    # 瞬态槽:调用方在 decide 之后、跑 post_policies 之前写入本帧决策动作,
    # 后置策略(confirm 拦截 / INPUT_GUARD)从这里读取,不在任务间留存。
    decided_actions: list[Action] = field(default_factory=list)
    # 按 actionId 对账的决策来源:下发动作时记录 pending_sources[action_id],
    # action.result 到达时 pop 取出,仅 cache/skill 且 ok 才推进 cursor(T11)。
    # 避免「下发后 ack 前插入新 decide」覆写瞬态槽的竞态。
    pending_sources: dict[str, str] = field(default_factory=dict)
    # 未 ack 的 UI 变更动作(tap/input/swipe/back/home)的 actionId 集合。
    # 非空期间到达的 perception 是「动作生效前的旧帧」,handlers 跳过 decide,
    # 待全部 ack 后由云端主动补 read_screen 抓动作后的新帧(F2 因果对账)。
    pending_mutating: set[str] = field(default_factory=set)
    guard: dict = field(
        default_factory=lambda: {
            "scene_history": [],
            "stall_count": 0,
            "last_op": "",
            "escalation_level": 0,
        }
    )
    negotiation: list[dict] = field(default_factory=list)
    last_consumed_seq: int = 0
    max_steps: int = Config.MAX_STEPS_DEFAULT
    scenario: str | None = None


@dataclass
class TaskStore:
    """持有当前任务的 TaskContext;同时至多一个任务在跑。"""

    current: TaskContext | None = None

    def new_task(
        self,
        goal: str,
        scenario: str | None = None,
        max_steps: int = Config.MAX_STEPS_DEFAULT,
    ) -> TaskContext:
        """整体新建 TaskContext 并置为 current。

        fsm 从 IDLE force 到 RUNNING(reason="task.request");
        scenario 暂存为属性,场景装配在后续任务接线。
        """
        fsm = TaskFSM()
        fsm.force(TaskState.RUNNING, reason="task.request")
        ctx = TaskContext(
            task_id=f"task-{uuid.uuid4().hex[:8]}",
            goal=goal,
            fsm=fsm,
            max_steps=max_steps,
            scenario=scenario,
        )
        logger.info("新任务创建: task_id=%s goal=%s", ctx.task_id, goal)
        self.current = ctx
        return ctx

    def clear(self) -> None:
        """清空当前任务上下文。"""
        if self.current is not None:
            logger.info("任务上下文清除: task_id=%s", self.current.task_id)
        self.current = None
