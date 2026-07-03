import pytest

from app.session import Session, State


def test_initial_state_is_navigating():
    session = Session(task_id="t1", goal="确认还款时间", target="张三")
    assert session.state == State.NAVIGATING


def test_valid_transition_to_in_chat():
    session = Session(task_id="t1", goal="确认还款时间", target="张三")
    session.transition(State.IN_CHAT)
    assert session.state == State.IN_CHAT


def test_invalid_transition_navigating_to_done_raises_value_error():
    session = Session(task_id="t1", goal="确认还款时间", target="张三")
    with pytest.raises(ValueError):
        session.transition(State.DONE)


def test_budget_exhausted_with_max_steps_two():
    session = Session(task_id="t1", goal="确认还款时间", target="张三", max_steps=2)
    assert session.budget_exhausted() is False
    session.record_step()
    assert session.budget_exhausted() is False
    session.record_step()
    assert session.budget_exhausted() is True