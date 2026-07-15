import pytest

from app.session import Session, State


def test_initial_state_is_navigating():
    session = Session(task_id="t1", goal="确认还款时间", target="张三")
    assert session.state == State.NAVIGATING


def test_valid_transition_to_in_chat():
    session = Session(task_id="t1", goal="确认还款时间", target="张三")
    session.transition(State.IN_CHAT)
    assert session.state == State.IN_CHAT


def test_invalid_transition_navigating_to_done_returns_false():
    # 修复 2026-07-15 LLM idle 状态 echo `done` 触发 ValueError 把 WS 整崩:
    # transition 改为返回 bool 而非抛异常,同时允许 NAVIGATING->DONE(idle 自然完成)。
    session = Session(task_id="t1", goal="确认还款时间", target="张三")
    assert session.transition(State.DONE) is True  # 新规则:idle 下 done 也合法
    assert session.state == State.DONE

    # 反例:DONE 是终态,不可再迁移到 IN_CHAT。
    assert session.transition(State.IN_CHAT) is False
    assert session.state == State.DONE


def test_budget_exhausted_with_max_steps_two():
    session = Session(task_id="t1", goal="确认还款时间", target="张三", max_steps=2)
    assert session.budget_exhausted() is False
    session.record_step()
    assert session.budget_exhausted() is False
    session.record_step()
    assert session.budget_exhausted() is True