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


# ---- LoopGuardPolicy(停滞/循环守卫)----

from app.protocol import Action, Node, Perception
from app.task.policies import LoopGuardPolicy, decision_signature, frame_signature


def _loop_ctx():
    return TaskStore().new_task(goal="g", scenario=None)


def _same_frame():
    return Perception(pkg="com.x", nodeTree=[Node(id="n1", text="甲")])


def _read_action():
    return [Action(actionId="r1", op="read_screen", params={})]


def test_frame_signature_changes_with_content():
    f1 = _same_frame()
    f2 = Perception(pkg="com.x", nodeTree=[Node(id="n1", text="乙")])
    f3 = Perception(pkg="com.y", nodeTree=[Node(id="n1", text="甲")])
    assert frame_signature(f1) != frame_signature(f2)
    assert frame_signature(f1) != frame_signature(f3)
    assert frame_signature(f1) == frame_signature(_same_frame())


def test_decision_signature_prefers_semantic_anchor():
    a1 = [Action(actionId="1", op="tap", params={"match_text": "发送", "x": "1", "y": "2"})]
    a2 = [Action(actionId="2", op="tap", params={"match_text": "发送", "x": "9", "y": "9"})]
    a3 = [Action(actionId="3", op="tap", params={"x": "1", "y": "2"})]
    assert decision_signature(a1) == decision_signature(a2)  # 锚点相同即同决策
    assert decision_signature(a1) != decision_signature(a3)


def test_loop_guard_continues_before_threshold():
    ctx = _loop_ctx()
    p = LoopGuardPolicy()
    for _ in range(Config.LOOP_GUARD_TRIGGER - 1):
        ctx.decided_actions = _read_action()
        assert p.inspect(_same_frame(), ctx).kind == "continue"


def test_loop_guard_intercepts_with_back_at_threshold():
    ctx = _loop_ctx()
    p = LoopGuardPolicy()
    v = None
    for _ in range(Config.LOOP_GUARD_TRIGGER):
        ctx.decided_actions = _read_action()
        v = p.inspect(_same_frame(), ctx)
    assert v.kind == "intercept"
    assert v.actions[0].op == "back"
    assert ctx.loop_backs == 1


def test_loop_guard_aborts_after_max_backs():
    ctx = _loop_ctx()
    p = LoopGuardPolicy()
    v = None
    # back 后帧/决策不变(查看器吞掉 back),repeats 持续增长直至上限
    for _ in range(Config.LOOP_GUARD_TRIGGER + Config.LOOP_GUARD_MAX_BACKS):
        ctx.decided_actions = _read_action()
        v = p.inspect(_same_frame(), ctx)
    assert v.kind == "terminate"
    assert v.reason == "stuck_loop"
    assert ctx.fsm.state == TaskState.ABORT


def test_loop_guard_resets_on_frame_or_decision_change():
    ctx = _loop_ctx()
    p = LoopGuardPolicy()
    for _ in range(Config.LOOP_GUARD_TRIGGER - 1):
        ctx.decided_actions = _read_action()
        p.inspect(_same_frame(), ctx)
    # 帧变了 -> 计数重置
    ctx.decided_actions = _read_action()
    p.inspect(Perception(pkg="com.x", nodeTree=[Node(id="n1", text="新页面")]), ctx)
    assert ctx.loop_repeats == 1
    # 决策变了 -> 计数重置
    ctx.decided_actions = [Action(actionId="t", op="tap", params={"match_text": "甲"})]
    p.inspect(_same_frame(), ctx)
    assert ctx.loop_repeats == 1
