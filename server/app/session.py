from __future__ import annotations

from datetime import datetime
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


# ==== Session 配置常量 ====
class SessionConfig:
    """Session 相关配置常量，统一管理魔法数字。"""
    AWAITING_CONFIRM_TIMEOUT_SEC = 30  # AWAITING_CONFIRM 状态超时时间（秒）
    MAX_STEPS_DEFAULT = 40             # 默认最大步数


class Session:
    def __init__(self, task_id: str, goal: str, target: str, max_steps: int = 40):
        self.task_id = task_id
        self.goal = goal
        self.target = target
        self.max_steps = max_steps
        self.state = State.NAVIGATING
        self.steps = 0

        # 活跃闸门:仅收到 task.request 后置 True;DONE/ABORT/发送流程结束置回 False。
        # 不活跃时 gateway 忽略一切 perception 帧,杜绝空转轮询(端侧无障碍持续推帧
        # 却每帧都 decide 出 wait/home 的问题)。
        self.active = False

        # 状态历史记录：用于排查「为什么会进入这个状态」
        self._state_history: list[tuple[State, State, datetime]] = []

        # per-task 收敛守卫状态；task 生命周期内原地更新，随 Session 销毁。
        self.guard: dict = {
            "scene_history": [],   # 最近 WINDOW 帧 scene 值（str）
            "stall_count": 0,
            "last_op": "",
            "escalation_level": 0,  # 0=正常 / 1=已问 LLM 脱困 / 2=已机械降级
        }

        # AWAITING_CONFIRM 超时守卫
        self._awaiting_confirm_started_at: datetime | None = None

    def transition(self, to: State) -> bool:
        """状态迁移,允许则返回 True,非法迁移返回 False(不抛异常)。

        非抛异常版:Gateway 调用方更易防御,避免 LLM 异常决策(echo `done`)或
        状态机不一致造成整个 WS 异常断开(根因:2026-07-15 LLM 在 idle 状态 echo `done`)。
        """
        if to not in _ALLOWED[self.state]:
            return False
        # 记录状态历史
        self._state_history.append((self.state, to, datetime.now()))
        self.state = to

        # 更新超时守卫时间
        if to == State.AWAITING_CONFIRM:
            self._awaiting_confirm_started_at = datetime.now()
        elif self._awaiting_confirm_started_at is not None:
            # 离开 AWAITING_CONFIRM 状态时清除超时计时
            self._awaiting_confirm_started_at = None

        return True

    def get_state_history(self) -> list[tuple[State, State, datetime]]:
        """获取状态转移历史。"""
        return self._state_history.copy()

    def check_awaiting_confirm_timeout(self) -> bool:
        """检查 AWAITING_CONFIRM 状态是否超时。"""
        if self.state != State.AWAITING_CONFIRM:
            return False
        if self._awaiting_confirm_started_at is None:
            return False
        elapsed = (datetime.now() - self._awaiting_confirm_started_at).total_seconds()
        return elapsed >= SessionConfig.AWAITING_CONFIRM_TIMEOUT_SEC

    def record_step(self) -> None:
        self.steps += 1

    def budget_exhausted(self) -> bool:
        return self.steps >= self.max_steps
