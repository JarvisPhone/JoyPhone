from datetime import datetime, timedelta

import pytest

from app.task.fsm import TaskFSM, TaskState


def test_exhaustive_legal_and_illegal_transitions():
    legal = {
        "IDLE": {"RUNNING", "ABORT"},
        "RUNNING": {"AWAITING_CONFIRM", "WAITING_EVENT", "DONE", "ABORT"},
        "AWAITING_CONFIRM": {"RUNNING", "DONE", "ABORT"},
        "WAITING_EVENT": {"RUNNING", "DONE", "ABORT"},
        "DONE": set(), "ABORT": set(),
    }
    for src in TaskState:
        for dst in TaskState:
            fsm = TaskFSM(); fsm.force(src)
            ok = fsm.transition(dst)
            assert ok == (dst.name in legal[src.name]), (src, dst)


def test_history_records_reason():
    fsm = TaskFSM(); fsm.force(TaskState.RUNNING)
    fsm.transition(TaskState.AWAITING_CONFIRM, reason="ConfirmInterceptPolicy")
    assert fsm.history[-1].reason == "ConfirmInterceptPolicy"


def test_awaiting_confirm_timeout():
    fsm = TaskFSM(); fsm.force(TaskState.RUNNING)
    fsm.transition(TaskState.AWAITING_CONFIRM)
    future = datetime.now() + timedelta(seconds=31)
    assert fsm.check_awaiting_confirm_timeout(future)


def test_initial_state_is_idle():
    # 新 FSM 初始必须为 IDLE
    assert TaskFSM().state == TaskState.IDLE


def test_illegal_transition_does_not_raise_and_keeps_state():
    # 非法迁移返回 False 不抛异常,状态不变
    fsm = TaskFSM()
    assert fsm.transition(TaskState.DONE) is False
    assert fsm.state == TaskState.IDLE


def test_force_records_history():
    # force 绕过迁移表,但必须记录 history(task.request 新任务重置依赖此)
    fsm = TaskFSM()
    fsm.force(TaskState.DONE, reason="reset")
    assert fsm.history[-1].frm == TaskState.IDLE
    assert fsm.history[-1].to == TaskState.DONE
    assert fsm.history[-1].reason == "reset"
    assert fsm.state == TaskState.DONE


def test_leaving_awaiting_confirm_clears_timer():
    # 离开 AWAITING_CONFIRM 后超时计时被清除
    fsm = TaskFSM(); fsm.force(TaskState.RUNNING)
    fsm.transition(TaskState.AWAITING_CONFIRM)
    fsm.transition(TaskState.RUNNING)
    future = datetime.now() + timedelta(seconds=999)
    assert fsm.check_awaiting_confirm_timeout(future) is False


def test_timeout_requires_awaiting_confirm_state():
    # 非 AWAITING_CONFIRM 状态永不超时
    fsm = TaskFSM(); fsm.force(TaskState.RUNNING)
    future = datetime.now() + timedelta(seconds=999)
    assert fsm.check_awaiting_confirm_timeout(future) is False


def test_not_timed_out_before_threshold():
    # 未达阈值不超时
    fsm = TaskFSM(); fsm.force(TaskState.RUNNING)
    fsm.transition(TaskState.AWAITING_CONFIRM)
    soon = datetime.now() + timedelta(seconds=1)
    assert fsm.check_awaiting_confirm_timeout(soon) is False
