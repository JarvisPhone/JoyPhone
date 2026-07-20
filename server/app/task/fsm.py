# server/app/task/fsm.py
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from app.infra.config import Config

logger = logging.getLogger(__name__)


class TaskState(Enum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    AWAITING_CONFIRM = "AWAITING_CONFIRM"
    WAITING_EVENT = "WAITING_EVENT"
    DONE = "DONE"
    ABORT = "ABORT"


@dataclass(frozen=True)
class TransitionRecord:
    """单次状态迁移记录,frm/to/reason/at 全程留痕。"""

    frm: TaskState
    to: TaskState
    reason: str
    at: datetime


# 合法迁移表;DONE/ABORT 为终态
_ALLOWED: dict[TaskState, set[TaskState]] = {
    TaskState.IDLE: {TaskState.RUNNING, TaskState.ABORT},
    TaskState.RUNNING: {
        TaskState.AWAITING_CONFIRM,
        TaskState.WAITING_EVENT,
        TaskState.DONE,
        TaskState.ABORT,
    },
    TaskState.AWAITING_CONFIRM: {TaskState.RUNNING, TaskState.DONE, TaskState.ABORT},
    TaskState.WAITING_EVENT: {TaskState.RUNNING, TaskState.DONE, TaskState.ABORT},
    TaskState.DONE: set(),
    TaskState.ABORT: set(),
}


@dataclass
class TaskFSM:
    """通用任务状态机。

    transition 非法迁移返回 False 不抛异常;force 绕过迁移表但记录 history
    (task.request 新任务重置依赖此语义)。进入 AWAITING_CONFIRM 记录时间,离开清除。
    """

    state: TaskState = TaskState.IDLE
    history: list[TransitionRecord] = field(default_factory=list)
    _awaiting_confirm_since: datetime | None = field(default=None, repr=False)

    def transition(self, to: TaskState, reason: str = "") -> bool:
        """按迁移表迁移;非法返回 False 不抛异常。"""
        if to not in _ALLOWED[self.state]:
            logger.warning(
                "非法状态迁移被拒绝: %s -> %s, reason=%s", self.state.value, to.value, reason
            )
            return False
        self._apply(to, reason)
        return True

    def force(self, to: TaskState, reason: str = "") -> None:
        """绕过迁移表强制迁移,仍记录 history。"""
        self._apply(to, reason)

    def check_awaiting_confirm_timeout(self, now: datetime) -> bool:
        """检查 AWAITING_CONFIRM 是否超过 Config.AWAITING_CONFIRM_TIMEOUT_SEC。"""
        if self.state != TaskState.AWAITING_CONFIRM:
            return False
        if self._awaiting_confirm_since is None:
            return False
        elapsed = (now - self._awaiting_confirm_since).total_seconds()
        return elapsed >= Config.AWAITING_CONFIRM_TIMEOUT_SEC

    def _apply(self, to: TaskState, reason: str) -> None:
        self.history.append(
            TransitionRecord(frm=self.state, to=to, reason=reason, at=datetime.now())
        )
        self.state = to
        if to == TaskState.AWAITING_CONFIRM:
            self._awaiting_confirm_since = datetime.now()
        else:
            self._awaiting_confirm_since = None
