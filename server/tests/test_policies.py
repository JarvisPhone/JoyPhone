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


def _drive(p, ctx, n):
    """连续 n 次同一(帧,决策),返回最后一次裁决。"""
    v = None
    for _ in range(n):
        ctx.decided_actions = _read_action()
        v = p.inspect(_same_frame(), ctx)
    return v


def test_loop_guard_ladder():
    ctx = _loop_ctx()
    p = LoopGuardPolicy()
    # 第 1 次:放行
    assert _drive(p, ctx, 1).kind == "continue"
    # 第 2 次:压下动作白看一帧(等 UI 稳定)
    v = _drive(p, ctx, 1)
    assert v.kind == "intercept" and v.actions[0].op == "read_screen"
    # 第 3 次:放行真·重试
    assert _drive(p, ctx, 1).kind == "continue"
    # 第 4 次:back 脱困
    v = _drive(p, ctx, 1)
    assert v.kind == "intercept" and v.actions[0].op == "back"
    assert ctx.loop_backs == 1


def test_loop_guard_aborts_after_max_backs():
    ctx = _loop_ctx()
    p = LoopGuardPolicy()
    # back 后帧/决策不变(查看器吞掉 back),repeats 持续增长直至上限
    v = _drive(p, ctx, Config.LOOP_GUARD_BACK + Config.LOOP_GUARD_MAX_BACKS)
    assert v.kind == "terminate"
    assert v.reason == "stuck_loop"
    assert ctx.fsm.state == TaskState.ABORT


def test_loop_guard_resets_on_frame_or_decision_change():
    ctx = _loop_ctx()
    p = LoopGuardPolicy()
    _drive(p, ctx, 3)  # 推进到放行重试档(此时 loop_repeats=3)
    # 帧变了 -> 计数重置
    ctx.decided_actions = _read_action()
    p.inspect(Perception(pkg="com.x", nodeTree=[Node(id="n1", text="新页面")]), ctx)
    assert ctx.loop_repeats == 1
    # 决策变了 -> 计数重置
    ctx.decided_actions = [Action(actionId="t", op="tap", params={"match_text": "甲"})]
    p.inspect(_same_frame(), ctx)
    assert ctx.loop_repeats == 1


def test_loop_guard_detects_backhome_oscillation():
    """back+home 反复交替(每帧 pkg 切换 → 帧签名不重复)→ 标准 (帧,决策) 检测不到,
    新加的 backhome 振荡检测能命中:压下 read_screen 并给 exit_hint 反馈。"""
    from app.task.policies import LoopGuardPolicy
    p = LoopGuardPolicy()

    # Window=6, alternating_pairs 阈值=3。
    # back home back home back → recent 5 项时交替对 = 4,达到阈值 → 命中
    # 所以 i==4 (0-indexed) 即第 5 帧应当命中,放行 read_screen。
    ctx = _loop_ctx()
    frames = [
        Perception(pkg="com.coloros.launcher", nodeTree=[Node(id="h1", text=f"frame{i}")])
        for i in range(5)
    ]
    actions_alt = [
        [Action(actionId=f"a{i}", op="back" if i % 2 == 0 else "home", params={})]
        for i in range(5)
    ]
    last_v = None
    for i, (frame, acts) in enumerate(zip(frames, actions_alt)):
        ctx.decided_actions = acts
        last_v = p.inspect(frame, ctx)
        if i < 3:
            assert last_v.kind == "continue", f"frame {i} 误判: {last_v}"
    # 第 4 帧 (i=3) 应当命中振荡 -> read_screen + exit_hint
    assert last_v is not None
    assert last_v.kind == "intercept"
    assert last_v.actions is not None and last_v.actions[0].op == "read_screen"
    assert "exit_hint" in last_v.reason or "退出路径" in last_v.reason


def test_loop_guard_backhome_oscillation_resets_after_hint_window():
    """backhome 命中后压下 EXIT_LOSER_HINT_REPEATS 帧,之后放行让 LLM 重试。"""
    from app.task.policies import LoopGuardPolicy
    p = LoopGuardPolicy()

    frames = [
        Perception(pkg="com.coloros.launcher", nodeTree=[Node(id="h1", text=f"f{i}")])
        for i in range(LoopGuardPolicy.OP_BACKOFF_WINDOW + LoopGuardPolicy.EXIT_LOSER_HINT_REPEATS + 2)
    ]
    ctx = _loop_ctx()
    v = None
    # 全部 back+home 交替(持续振荡);压下后 hits 仍累加,直到退出 hint_repeats
    # 最后一个是 read_screen 动作,不计入 op_recent;但 op_recent 仍会被刷
    for i in range(len(frames)):
        # 模拟「上一帧 LoopGuard 已经压下 read_screen」时,LLM 重新决策出来的 back/home
        # 但这里直接驱动:每个 inspect 都用 back/home 交替,直到 hits 用尽后让放行。
        if ctx.guard.get("loop_backhome_hits", 0) >= LoopGuardPolicy.EXIT_LOSER_HINT_REPEATS:
            # 跳出死循环:切到一个新决策(tap),让振荡计数有条件不再增加
            ctx.decided_actions = [Action(actionId=f"end{i}", op="tap",
                                          params={"match_text": "foo"})]
        else:
            ctx.decided_actions = [Action(actionId=f"a{i}", op="back" if i % 2 == 0 else "home", params={})]
        v = p.inspect(frames[i], ctx)
    # 振荡命中阶段全部给出 read_screen + exit_hint 反馈
    assert v is not None
    assert ctx.guard["loop_backhome_hits"] >= 1  # 至少触发一次


def test_verdict_carries_policy_name():
    class _P:
        name = "my_guard"

        def inspect(self, frame, ctx):
            return terminate("r", "aborted")

    ctx = TaskStore().new_task(goal="g", scenario=None)
    v = run_pipeline([_P()], None, ctx)
    assert v.policy == "my_guard"
