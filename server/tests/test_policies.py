# server/tests/test_policies.py
from __future__ import annotations

from datetime import datetime, timedelta

from app.infra.config import Config
from app.task.context import TaskStore
from app.task.fsm import TaskState
from app.task.policies import (
    BudgetPolicy,
    ConfirmTimeoutPolicy,
    continue_,
    intercept,
    run_pipeline,
    terminate,
)


def _ctx_with_steps(steps: int):
    ctx = TaskStore().new_task(goal="g", scenario=None)
    ctx.steps = steps
    return ctx


def test_verdict_factories():
    v = continue_()
    assert v.kind == "continue" and v.reason == "" and v.status == "" and v.actions is None
    v = terminate("r", "aborted")
    assert v.kind == "terminate" and v.reason == "r" and v.status == "aborted"
    v = intercept([])
    assert v.kind == "intercept" and v.actions == []


def test_budget_policy_terminates_when_exhausted():
    ctx = _ctx_with_steps(40)
    v = run_pipeline([BudgetPolicy()], None, ctx)
    assert v.kind == "terminate" and v.reason == "budget_exhausted"


def test_budget_policy_continues_below_limit():
    ctx = _ctx_with_steps(1)
    v = run_pipeline([BudgetPolicy()], None, ctx)
    assert v.kind == "continue"


def test_confirm_timeout_policy_terminates_on_timeout():
    ctx = _ctx_with_steps(0)
    ctx.fsm.force(TaskState.AWAITING_CONFIRM, reason="test")
    ctx.fsm._awaiting_confirm_since = datetime.now() - timedelta(
        seconds=Config.AWAITING_CONFIRM_TIMEOUT_SEC + 1
    )
    v = run_pipeline([ConfirmTimeoutPolicy()], None, ctx)
    assert v.kind == "terminate" and v.reason == "confirm_timeout" and v.status == "aborted"


def test_confirm_timeout_policy_continues_when_not_awaiting():
    ctx = _ctx_with_steps(0)
    v = run_pipeline([ConfirmTimeoutPolicy()], None, ctx)
    assert v.kind == "continue"


def test_pipeline_short_circuits():
    class Noop:
        name = "noop"

        def inspect(self, f, c):
            return continue_()

    ctx = _ctx_with_steps(40)
    v = run_pipeline([Noop(), BudgetPolicy()], None, ctx)
    assert v.kind == "terminate"


def test_pipeline_skips_after_terminate():
    calls = []

    class First:
        name = "first"

        def inspect(self, f, c):
            calls.append("first")
            return terminate("stop", "aborted")

    class Second:
        name = "second"

        def inspect(self, f, c):
            calls.append("second")
            return continue_()

    ctx = _ctx_with_steps(0)
    v = run_pipeline([First(), Second()], None, ctx)
    assert v.kind == "terminate" and v.reason == "stop"
    assert calls == ["first"]


def test_pipeline_all_continue():
    class Noop:
        name = "noop"

        def inspect(self, f, c):
            return continue_()

    ctx = _ctx_with_steps(0)
    v = run_pipeline([Noop(), Noop()], None, ctx)
    assert v.kind == "continue"
