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
    # 瞬态槽:调用方在 decide 之后、跑 post_policies 之前写入本帧决策动作,
    # 后置策略(confirm 拦截 / INPUT_GUARD)从这里读取,不在任务间留存。
    decided_actions: list[Action] = field(default_factory=list)
    # 上帧 Decision 的来源(cache/skill/pkg_guard/llm);action.result ok
    # 且来源为 cache/skill 时 handler 据此推进 cursor(T11)。
    last_decision_source: str = ""
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
