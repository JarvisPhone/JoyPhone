from __future__ import annotations

from enum import Enum


class State(Enum):
    NAVIGATING = "NAVIGATING"
    IN_CHAT = "IN_CHAT"
    SENT = "SENT"
    WAITING_REPLY = "WAITING_REPLY"
    NEGOTIATING = "NEGOTIATING"
    DONE = "DONE"
    ABORT = "ABORT"


_ALLOWED: dict[State, set[State]] = {
    State.NAVIGATING: {State.IN_CHAT, State.ABORT},
    State.IN_CHAT: {State.SENT, State.ABORT},
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

    def transition(self, to: State) -> None:
        if to not in _ALLOWED[self.state]:
            raise ValueError(f"invalid transition: {self.state.value}->{to.value}")
        self.state = to

    def record_step(self) -> None:
        self.steps += 1

    def budget_exhausted(self) -> bool:
        return self.steps >= self.max_steps
