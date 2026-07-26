"""Task phase 状态机:每个 scenario 自定义 phase 推进规则。"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Protocol


class TaskPhase(str, enum.Enum):
    """send_message 等场景的 phase 枚举。"""

    IDLE = "idle"
    SEARCH = "search"
    ENTER_CHAT = "enter_chat"
    INPUT_TEXT = "input_text"
    SEND = "send"
    VERIFY = "verify"
    DONE = "done"


@dataclass
class PhaseState:
    """per-task phase 状态。"""

    phase: TaskPhase = TaskPhase.IDLE
    current_step_index: int = 0
    completed_phases: list[tuple[TaskPhase, str]] = field(default_factory=list)

    def advance(self, to: TaskPhase, *, gate_met_for: str) -> None:
        """进入下一 phase;记录刚完成的 phase + 通过的 gate 描述。"""
        self.completed_phases.append((to, gate_met_for))
        self.phase = to
        self.current_step_index = 1

    def record_step(self, *, taken: str, reached_gate: bool) -> None:
        """phase 内每步一次决策触发;reached_gate=True 时调用方负责 advance。"""
        if reached_gate:
            return

    def to_payload_dict(self) -> dict:
        """喂给 build_user_payload 的稳定 dict。"""
        return {
            "phase": self.phase.value,
            "current_step_index": self.current_step_index,
            "completed_phases": list(self.completed_phases),
        }


class PhasePack(Protocol):
    """scenario 自定义 phase 列表 + gate 检测。"""

    def phases(self) -> list[TaskPhase]:
        """该 scenario 的 phase 顺序。"""
        ...

    def gate_for(self, phase: TaskPhase, frame, ctx) -> str | None:
        """当前 phase 是否达到 next_gate;达到返回 gate 描述(中文),否则 None。

        Task 9 完整化:看 (frame, ctx) 联合判定。
        """
        ...
