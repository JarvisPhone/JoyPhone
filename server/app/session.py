from __future__ import annotations

from enum import Enum


class State(Enum):
    NAVIGATING = "NAVIGATING"
    IN_CHAT = "IN_CHAT"
    AWAITING_CONFIRM = "AWAITING_CONFIRM"  # 发送前 Toast 确认窗口(5 秒)
    SENT = "SENT"
    WAITING_REPLY = "WAITING_REPLY"
    NEGOTIATING = "NEGOTIATING"
    DONE = "DONE"
    ABORT = "ABORT"


_ALLOWED: dict[State, set[State]] = {
    State.NAVIGATING: {State.IN_CHAT, State.AWAITING_CONFIRM, State.DONE, State.ABORT},
    # IN_CHAT 自迁移用于 confirm reject 后回到原状态,让 LLM 重新决策。
    State.IN_CHAT: {State.AWAITING_CONFIRM, State.SENT, State.ABORT, State.IN_CHAT},
    State.AWAITING_CONFIRM: {State.SENT, State.ABORT, State.IN_CHAT},
    State.SENT: {State.WAITING_REPLY, State.ABORT},
    State.WAITING_REPLY: {State.NEGOTIATING, State.DONE, State.ABORT},
    State.NEGOTIATING: {State.SENT, State.DONE, State.ABORT},
    State.DONE: set(),
    State.ABORT: set(),
}


class Session:
    def __init__(self, task_id: str, goal: str, target: str, max_steps: int = 40):
        self.task_id = task_id
        self.goal = goal
        self.target = target
        self.max_steps = max_steps
        self.state = State.NAVIGATING
        self.steps = 0

    def transition(self, to: State) -> bool:
        """状态迁移,允许则返回 True,非法迁移返回 False(不抛异常)。

        非抛异常版:Gateway 调用方更易防御,避免 LLM 异常决策(echo `done`)或
        状态机不一致造成整个 WS 异常断开(根因:2026-07-15 LLM 在 idle 状态 echo `done`)。
        """
        if to not in _ALLOWED[self.state]:
            return False
        self.state = to
        return True

    def record_step(self) -> None:
        self.steps += 1

    def budget_exhausted(self) -> bool:
        return self.steps >= self.max_steps
