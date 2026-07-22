# server/tests/test_handlers.py
from __future__ import annotations

import uuid

import pytest

from app.decision import Decision
from app.infra.config import Config
from app.infra.metrics import MetricsCollector
from app.protocol import (
    Action,
    ActionResult,
    ConfirmResponse,
    Heartbeat,
    Node,
    Perception,
    TaskRequest,
)
from app.scenario.profiles import FEISHU_PROFILE
from app.scenario.send_message import SendMessagePack
from app.task.context import TaskStore
from app.task.fsm import TaskState
from app.task.handlers import HandlerDeps, handle_uplink

LARK = FEISHU_PROFILE.pkg


class FakeConn:
    def __init__(self):
        self.sent: list = []

    async def send(self, model) -> None:
        self.sent.append(model)


class SpyEngine:
    """记录 decide 调用并返回预设 Decision;cache 默认 None。"""

    def __init__(self, decision: Decision | None = None):
        self.calls: list = []
        self.decision = decision or Decision(
            actions=[Action(actionId="a-read", op="read_screen", params={})],
            source="llm",
        )
        self.cache = None

    def decide(self, d) -> Decision:
        self.calls.append(d)
        return self.decision


def _deps(engine, packs=(), tmp_path=None) -> HandlerDeps:
    return HandlerDeps(
        engine=engine,
        scenario_packs=list(packs),
        metrics=MetricsCollector(log_dir=tmp_path),
        max_steps=Config.MAX_STEPS_DEFAULT,
    )


def _req(goal="随便做点什么") -> TaskRequest:
    return TaskRequest(goal=goal)


def _perception(seq=1, pkg="", nodes=None) -> Perception:
    return Perception(pkg=pkg, seq=seq, nodeTree=nodes or [])


# ---- brief Step 1: 三个集成用例 ----


async def test_stale_perception_dropped(tmp_path):
    store = TaskStore()
    engine = SpyEngine()
    conn = FakeConn()
    deps = _deps(engine, tmp_path=tmp_path)
    await handle_uplink(_req(), store, conn, deps)
    store.current.last_consumed_seq = 5

    await handle_uplink(_perception(seq=5), store, conn, deps)
    assert engine.calls == []

    await handle_uplink(_perception(seq=6), store, conn, deps)
    assert len(engine.calls) == 1
    assert store.current.last_consumed_seq == 6


async def test_second_task_on_same_connection_starts_clean(tmp_path):
    store = TaskStore()
    engine = SpyEngine(
        Decision(actions=[Action(actionId="a-done", op="done", params={})], source="llm")
    )
    conn = FakeConn()
    deps = _deps(engine, tmp_path=tmp_path)

    await handle_uplink(_req("任务一"), store, conn, deps)
    ctx1 = store.current
    await handle_uplink(_perception(seq=1), store, conn, deps)
    assert store.current is None  # done 后清理

    await handle_uplink(_req("任务二"), store, conn, deps)
    ctx2 = store.current
    assert ctx2 is not ctx1
    assert ctx2.steps == 0
    assert ctx2.cursor.index == 0
    assert ctx2.cursor.state == "pending"
    assert ctx2.guard == {
        "scene_history": [],
        "stall_count": 0,
        "last_op": "",
        "escalation_level": 0,
    }
    assert ctx2.history == []
    assert ctx2.applied_steps == []
    assert ctx2.last_consumed_seq == 0
    assert ctx2.fsm.state == TaskState.RUNNING


async def test_heartbeat_receives_ack_not_action(tmp_path):
    store = TaskStore()
    engine = SpyEngine()
    conn = FakeConn()
    deps = _deps(engine, tmp_path=tmp_path)
    await handle_uplink(_req(), store, conn, deps)

    await handle_uplink(Heartbeat(deviceId="dev-1"), store, conn, deps)
    assert conn.sent[-1].type == "heartbeat.ack"
    assert conn.sent[-1].deviceId == "dev-1"
    assert not any(getattr(m, "type", "") == "action" for m in conn.sent)


# ---- confirm approved / rejected ----


def _ctx_awaiting_confirm(store: TaskStore):
    ctx = store.new_task(goal="给阿强发飞书消息", scenario="send_message")
    ctx.target_pkg = LARK
    ctx.target_chat = "阿强"
    ctx.fsm.force(TaskState.AWAITING_CONFIRM, reason="test")
    ctx.confirm.confirm_id = "cfm-12345678"
    ctx.confirm.pending_action = Action(
        actionId="a-tap", op="tap", params={"x": "50", "y": "50"}
    )
    ctx.confirm.message_text = "hello"
    return ctx


async def test_confirm_approved_sends_pending_tap(tmp_path):
    store = TaskStore()
    ctx = _ctx_awaiting_confirm(store)
    conn = FakeConn()
    deps = _deps(SpyEngine(), tmp_path=tmp_path)

    await handle_uplink(
        ConfirmResponse(taskId=ctx.task_id, confirmId="cfm-12345678", approved=True),
        store, conn, deps,
    )
    taps = [m for m in conn.sent if getattr(m, "type", "") == "action"]
    assert len(taps) == 1
    assert taps[0].op == "tap"
    assert taps[0].params == {"x": "50", "y": "50"}
    assert ctx.post_send.acked is True
    assert ctx.fsm.state == TaskState.RUNNING
    assert ctx.confirm.pending_action is None


async def test_confirm_approved_but_reverted_aborts(tmp_path):
    store = TaskStore()
    ctx = _ctx_awaiting_confirm(store)
    ctx.confirm.reverted = True
    conn = FakeConn()
    deps = _deps(SpyEngine(), tmp_path=tmp_path)

    await handle_uplink(
        ConfirmResponse(taskId=ctx.task_id, confirmId="cfm-12345678", approved=True),
        store, conn, deps,
    )
    assert conn.sent[-1].type == "task.abort"
    assert conn.sent[-1].reason == "approve_but_pre_send_reverted"
    assert store.current is None


async def test_confirm_rejected_clears_pending_back_to_running(tmp_path):
    store = TaskStore()
    ctx = _ctx_awaiting_confirm(store)
    conn = FakeConn()
    deps = _deps(SpyEngine(), tmp_path=tmp_path)

    await handle_uplink(
        ConfirmResponse(
            taskId=ctx.task_id, confirmId="cfm-12345678", approved=False, reason="改文案"
        ),
        store, conn, deps,
    )
    assert conn.sent == []
    assert ctx.confirm.pending_action is None
    assert ctx.confirm.confirm_id is None
    assert ctx.fsm.state == TaskState.RUNNING
    assert store.current is ctx


async def test_confirm_response_id_mismatch_ignored(tmp_path):
    store = TaskStore()
    ctx = _ctx_awaiting_confirm(store)
    conn = FakeConn()
    deps = _deps(SpyEngine(), tmp_path=tmp_path)

    await handle_uplink(
        ConfirmResponse(taskId=ctx.task_id, confirmId="cfm-00000000", approved=True),
        store, conn, deps,
    )
    assert conn.sent == []
    assert ctx.confirm.confirm_id == "cfm-12345678"
    assert ctx.fsm.state == TaskState.AWAITING_CONFIRM


async def test_confirm_response_wrong_state_ignored(tmp_path):
    store = TaskStore()
    ctx = store.new_task(goal="g", scenario=None)
    ctx.confirm.confirm_id = "cfm-12345678"
    conn = FakeConn()
    deps = _deps(SpyEngine(), tmp_path=tmp_path)

    await handle_uplink(
        ConfirmResponse(taskId=ctx.task_id, confirmId="cfm-12345678", approved=True),
        store, conn, deps,
    )
    assert conn.sent == []
    assert ctx.fsm.state == TaskState.RUNNING


# ---- done 迁移与收尾 ----


async def test_done_action_finishes_task_and_clears_store(tmp_path):
    store = TaskStore()
    engine = SpyEngine(
        Decision(actions=[Action(actionId="a-done", op="done", params={})], source="llm")
    )
    conn = FakeConn()
    deps = _deps(engine, tmp_path=tmp_path)
    await handle_uplink(_req(), store, conn, deps)
    ctx = store.current

    await handle_uplink(_perception(seq=1), store, conn, deps)
    assert conn.sent[-1].type == "task.done"
    assert conn.sent[-1].taskId == ctx.task_id
    assert ctx.fsm.state == TaskState.DONE
    assert store.current is None


async def test_abort_action_finishes_task(tmp_path):
    store = TaskStore()
    engine = SpyEngine(
        Decision(
            actions=[Action(actionId="a-ab", op="abort", params={"reason": "找不到"})],
            source="llm",
        )
    )
    conn = FakeConn()
    deps = _deps(engine, tmp_path=tmp_path)
    await handle_uplink(_req(), store, conn, deps)

    await handle_uplink(_perception(seq=1), store, conn, deps)
    assert conn.sent[-1].type == "task.abort"
    assert conn.sent[-1].reason == "找不到"
    assert store.current is None


async def test_perception_without_ctx_dropped(tmp_path):
    engine = SpyEngine()
    conn = FakeConn()
    deps = _deps(engine, tmp_path=tmp_path)
    await handle_uplink(_perception(seq=1), TaskStore(), conn, deps)
    assert engine.calls == []
    assert conn.sent == []


async def test_budget_terminate_via_pre_pipeline(tmp_path):
    store = TaskStore()
    engine = SpyEngine()
    conn = FakeConn()
    deps = _deps(engine, tmp_path=tmp_path)
    await handle_uplink(_req(), store, conn, deps)
    store.current.steps = Config.MAX_STEPS_DEFAULT

    await handle_uplink(_perception(seq=1), store, conn, deps)
    assert engine.calls == []
    assert conn.sent[-1].type == "task.abort"
    assert conn.sent[-1].reason == "budget_exhausted"
    assert store.current is None


# ---- cursor.advance 条件 ----


async def test_cursor_advances_on_ok_from_skill_or_cache(tmp_path):
    for source in ("skill", "cache"):
        store = TaskStore()
        ctx = store.new_task(goal="g", scenario=None)
        ctx.pending_sources["a1"] = source
        deps = _deps(SpyEngine(), tmp_path=tmp_path)
        await handle_uplink(
            ActionResult(actionId="a1", ok=True), store, FakeConn(), deps
        )
        assert ctx.cursor.index == 1, source


async def test_cursor_not_advanced_on_llm_source_or_failure(tmp_path):
    for source, ok in (("llm", True), ("pkg_guard", True), ("skill", False)):
        store = TaskStore()
        ctx = store.new_task(goal="g", scenario=None)
        ctx.pending_sources["a1"] = source
        deps = _deps(SpyEngine(), tmp_path=tmp_path)
        await handle_uplink(
            ActionResult(actionId="a1", ok=ok), store, FakeConn(), deps
        )
        assert ctx.cursor.index == 0, (source, ok)


async def test_cursor_reconciles_by_action_id_across_interleaved_decide(tmp_path):
    """竞态回归:skill 动作下发后、ack 前插入新 perception 触发 llm decide,
    旧瞬态槽会被覆写导致 cursor 不推进;按 actionId 对账后仍应推进。"""
    store = TaskStore()
    engine = SpyEngine(
        Decision(
            actions=[Action(actionId="a-skill", op="tap", params={"x": "1"})],
            source="skill",
        )
    )
    conn = FakeConn()
    deps = _deps(engine, tmp_path=tmp_path)
    await handle_uplink(_req(), store, conn, deps)
    ctx = store.current

    await handle_uplink(_perception(seq=1), store, conn, deps)
    assert ctx.pending_sources == {"a-skill": "skill"}

    engine.decision = Decision(
        actions=[Action(actionId="a-llm", op="read_screen", params={})],
        source="llm",
    )
    await handle_uplink(_perception(seq=2), store, conn, deps)
    assert ctx.cursor.index == 0

    await handle_uplink(
        ActionResult(actionId="a-skill", ok=True), store, FakeConn(), deps
    )
    assert ctx.cursor.index == 1
    assert "a-skill" not in ctx.pending_sources

    await handle_uplink(
        ActionResult(actionId="a-llm", ok=True), store, FakeConn(), deps
    )
    assert ctx.cursor.index == 1


async def test_action_result_appends_history(tmp_path):
    store = TaskStore()
    ctx = store.new_task(goal="g", scenario=None)
    deps = _deps(SpyEngine(), tmp_path=tmp_path)
    await handle_uplink(ActionResult(actionId="a1", ok=True), store, FakeConn(), deps)
    await handle_uplink(ActionResult(actionId="a2", ok=False), store, FakeConn(), deps)
    assert ctx.history == [
        {"actionId": "a1", "ok": True},
        {"actionId": "a2", "ok": False},
    ]


# ---- scenario 集成:confirm 拦截 -> TaskConfirm ----


def _chat_frame():
    title = Node(id="t1", text="阿强", viewIdResourceName=f"{LARK}:id/tv_title")
    send_btn = Node(
        id="b1", viewIdResourceName=f"{LARK}:id/btn_send", bounds=(0, 0, 100, 100)
    )
    return _perception(seq=1, pkg=LARK, nodes=[title, send_btn])


async def test_send_message_scenario_intercepts_send_tap(tmp_path):
    store = TaskStore()
    engine = SpyEngine(
        Decision(
            actions=[Action(actionId="a-tap", op="tap", params={"match_rid": "btn_send"})],
            source="llm",
        )
    )
    conn = FakeConn()
    deps = _deps(engine, packs=[SendMessagePack()], tmp_path=tmp_path)

    await handle_uplink(_req("给阿强发飞书消息"), store, conn, deps)
    ctx = store.current
    assert ctx.scenario == "send_message"
    assert ctx.target_pkg == LARK
    assert ctx.target_chat == "阿强"
    assert ctx.bound_skill is not None
    assert conn.sent[-1].type == "task.start"
    # 确认拦截以「已有 input 正文」为前提(无正文的发送 tap 直接透传)
    ctx.applied_steps.append({"op": "input", "params": {"text": "晚上好"}})

    await handle_uplink(_chat_frame(), store, conn, deps)
    confirms = [m for m in conn.sent if m.type == "task.confirm"]
    assert len(confirms) == 1
    assert confirms[0].taskId == ctx.task_id
    assert confirms[0].confirmId == ctx.confirm.confirm_id
    assert confirms[0].timeoutMs == Config.CONFIRM_TIMEOUT_MS
    assert ctx.fsm.state == TaskState.AWAITING_CONFIRM
    assert ctx.confirm.pending_action is not None
    # 被拦截的 tap 不应直接下发
    assert not any(getattr(m, "type", "") == "action" for m in conn.sent)


async def test_no_scenario_match_runs_generic(tmp_path):
    store = TaskStore()
    engine = SpyEngine()
    conn = FakeConn()
    deps = _deps(engine, packs=[SendMessagePack()], tmp_path=tmp_path)

    await handle_uplink(_req("今天天气怎么样"), store, conn, deps)
    ctx = store.current
    assert ctx.scenario is None
    assert ctx.bound_skill is None

    await handle_uplink(_perception(seq=1), store, conn, deps)
    assert conn.sent[-1].type == "action"
    assert conn.sent[-1].op == "read_screen"
    assert ctx.steps == 1


# ---- F2: 动作↔帧因果对账(UI 动作未 ack 期间跳过 decide)----


def _tap_decision(action_id="a-tap"):
    return Decision(
        actions=[Action(actionId=action_id, op="tap", params={"x": "1", "y": "2"})],
        source="llm",
    )


async def test_perception_skipped_while_mutating_action_pending(tmp_path):
    """tap 下发后、ack 前的 perception(动作前的旧帧)不得再触发 decide。"""
    store = TaskStore()
    engine = SpyEngine(_tap_decision())
    conn = FakeConn()
    deps = _deps(engine, tmp_path=tmp_path)
    await handle_uplink(_req(), store, conn, deps)
    await handle_uplink(_perception(seq=1), store, conn, deps)  # decide#1 → tap
    assert len(engine.calls) == 1

    await handle_uplink(_perception(seq=2), store, conn, deps)  # tap 未 ack → 跳过
    assert len(engine.calls) == 1


async def test_ack_of_mutating_action_triggers_read_screen_then_resume(tmp_path):
    """mutating 动作 ack 后云端主动补 read_screen 抓新帧;之后 perception 恢复 decide。"""
    store = TaskStore()
    engine = SpyEngine(_tap_decision())
    conn = FakeConn()
    deps = _deps(engine, tmp_path=tmp_path)
    await handle_uplink(_req(), store, conn, deps)
    await handle_uplink(_perception(seq=1), store, conn, deps)
    sent_before = len(conn.sent)

    await handle_uplink(
        ActionResult(actionId="a-tap", ok=True, seq=2), store, conn, deps
    )
    new_sent = conn.sent[sent_before:]
    assert any(getattr(m, "op", None) == "read_screen" for m in new_sent)

    await handle_uplink(_perception(seq=3), store, conn, deps)
    assert len(engine.calls) == 2


async def test_batch_mutating_acks_trigger_read_screen_only_when_drained(tmp_path):
    """一批多个 mutating 动作,只有最后一个 ack(清空 pending)才补 read_screen。"""
    store = TaskStore()
    engine = SpyEngine(
        Decision(
            actions=[
                Action(actionId="a-back", op="back", params={}),
                Action(actionId="a-tap", op="tap", params={"x": "1", "y": "2"}),
            ],
            source="llm",
        )
    )
    conn = FakeConn()
    deps = _deps(engine, tmp_path=tmp_path)
    await handle_uplink(_req(), store, conn, deps)
    await handle_uplink(_perception(seq=1), store, conn, deps)

    sent_before = len(conn.sent)
    await handle_uplink(
        ActionResult(actionId="a-back", ok=True, seq=2), store, conn, deps
    )
    assert not any(
        getattr(m, "op", None) == "read_screen" for m in conn.sent[sent_before:]
    )

    await handle_uplink(
        ActionResult(actionId="a-tap", ok=True, seq=3), store, conn, deps
    )
    assert any(
        getattr(m, "op", None) == "read_screen" for m in conn.sent[sent_before:]
    )


async def test_read_screen_ack_does_not_gate_or_trigger(tmp_path):
    """read_screen 非 mutating:其 ack 不补帧,期间 perception 正常 decide。"""
    store = TaskStore()
    engine = SpyEngine()  # 默认 read_screen
    conn = FakeConn()
    deps = _deps(engine, tmp_path=tmp_path)
    await handle_uplink(_req(), store, conn, deps)
    await handle_uplink(_perception(seq=1), store, conn, deps)  # decide#1
    sent_before = len(conn.sent)
    await handle_uplink(
        ActionResult(actionId="a-read", ok=True, seq=2), store, conn, deps
    )
    assert len(conn.sent) == sent_before  # 不补帧
    await handle_uplink(_perception(seq=3), store, conn, deps)
    assert len(engine.calls) == 2  # 未被 gate


# ---- ack 对账回写 applied_steps ----


async def test_ack_result_recorded_into_applied_steps(tmp_path):
    store = TaskStore()
    engine = SpyEngine(
        Decision(actions=[Action(actionId="a-tap", op="tap", params={"x": "1"})], source="llm")
    )
    conn = FakeConn()
    deps = _deps(engine, tmp_path=tmp_path)
    await handle_uplink(_req(), store, conn, deps)
    await handle_uplink(_perception(seq=1, pkg="com.x"), store, conn, deps)
    ctx = store.current
    assert ctx.applied_steps[-1]["ok"] is None
    assert ctx.applied_steps[-1]["pkg"] == "com.x"
    assert ctx.applied_steps[-1]["actionId"] == "a-tap"

    await handle_uplink(ActionResult(actionId="a-tap", ok=True), store, conn, deps)
    assert ctx.applied_steps[-1]["ok"] is True


# ---- cache 回放熔断 ----


class _FakeCache:
    def __init__(self):
        self.missed: list = []

    def mark_miss(self, goal, context, cursor):
        self.missed.append((goal, context, cursor))


async def test_cache_fuse_after_consecutive_failures(tmp_path):
    store = TaskStore()
    ctx = store.new_task(goal="g", scenario=None)
    ctx.target_pkg = "com.x"
    ctx.cache_context = "com.x|unknown"
    cache = _FakeCache()
    engine = SpyEngine()
    engine.cache = cache
    deps = _deps(engine, tmp_path=tmp_path)

    for i in range(Config.CACHE_STEP_MAX_FAILS):
        ctx.pending_sources[f"a-fail-{i}"] = "cache"
        await handle_uplink(
            ActionResult(actionId=f"a-fail-{i}", ok=False), store, FakeConn(), deps
        )
    assert cache.missed == [("g", "com.x|unknown", 0)]
    assert ctx.cache_disabled is True


async def test_cache_fuse_reset_on_ok(tmp_path):
    store = TaskStore()
    ctx = store.new_task(goal="g", scenario=None)
    cache = _FakeCache()
    engine = SpyEngine()
    engine.cache = cache
    deps = _deps(engine, tmp_path=tmp_path)

    ctx.pending_sources["f1"] = "cache"
    await handle_uplink(ActionResult(actionId="f1", ok=False), store, FakeConn(), deps)
    ctx.pending_sources["ok1"] = "cache"
    await handle_uplink(ActionResult(actionId="ok1", ok=True), store, FakeConn(), deps)
    assert ctx.cache_step_fails == 0
    ctx.pending_sources["f2"] = "cache"
    await handle_uplink(ActionResult(actionId="f2", ok=False), store, FakeConn(), deps)
    assert cache.missed == [] and ctx.cache_disabled is False


# ---- 入口分类 + skill cursor 快进 ----


def _title_frame(seq, title, pkg=LARK):
    return _perception(
        seq=seq, pkg=pkg,
        nodes=[Node(id="t1", text=title, viewIdResourceName=f"{LARK}:id/tv_title")],
    )


async def test_entry_classification_and_cursor_fast_forward(tmp_path):
    """热启动直接落在目标群:entry=target_chat,cursor 快进至 verify_title。"""
    store = TaskStore()
    engine = SpyEngine()
    conn = FakeConn()
    deps = _deps(engine, packs=[SendMessagePack()], tmp_path=tmp_path)
    await handle_uplink(_req("给群「测试群」发飞书消息"), store, conn, deps)
    ctx = store.current
    assert ctx.bound_skill is not None

    await handle_uplink(_title_frame(seq=1, title="测试群"), store, conn, deps)
    assert ctx.entry_state == "target_chat"
    assert ctx.cache_context == f"{LARK}|target_chat"
    verify_idx = next(
        i for i, s in enumerate(ctx.bound_skill.steps) if s.op == "verify_title"
    )
    assert ctx.cursor.index == verify_idx


async def test_entry_unknown_keeps_cursor_at_zero(tmp_path):
    store = TaskStore()
    engine = SpyEngine()
    conn = FakeConn()
    deps = _deps(engine, packs=[SendMessagePack()], tmp_path=tmp_path)
    await handle_uplink(_req("给群「测试群」发飞书消息"), store, conn, deps)
    ctx = store.current

    await handle_uplink(_title_frame(seq=1, title="别的群"), store, conn, deps)
    assert ctx.entry_state == "unknown"
    assert ctx.cursor.index == 0


# ---- learn:泛化 + 候选计数 ----


async def test_done_records_generalized_candidate(tmp_path):
    from app.decision.cache import SkillCache
    store = TaskStore()
    cache = SkillCache(tmp_path / "c.json")
    engine = SpyEngine(
        Decision(actions=[Action(actionId="a-done", op="done", params={})], source="llm")
    )
    engine.cache = cache
    conn = FakeConn()
    deps = _deps(engine, packs=[SendMessagePack()], tmp_path=tmp_path)
    await handle_uplink(_req("给群「测试群」发飞书消息"), store, conn, deps)
    ctx = store.current
    ctx.applied_steps = [
        {"op": "home", "params": {}, "pkg": "com.android.launcher", "actionId": "h", "ok": True},
        {"op": "tap", "params": {"match_text": "搜索", "x": "1", "y": "2"}, "pkg": LARK, "actionId": "t1", "ok": True},
        {"op": "input", "params": {"text": "测试群"}, "pkg": LARK, "actionId": "i1", "ok": True},
        {"op": "tap", "params": {"match_text": "发送"}, "pkg": LARK, "actionId": "t2", "ok": True},
    ]
    ctx.cache_context = f"{LARK}|unknown"
    ctx.post_send.acked = True  # 真实发送过,SendGuard 才放行 done
    await handle_uplink(_perception(seq=1, pkg=LARK), store, conn, deps)
    assert store.current is None  # done
    key = f"给群「测试群」发飞书消息|{LARK}|unknown"
    raw = cache._data[key]
    assert raw["status"] == "candidate" and raw["count"] == 1
    assert raw["steps"] == [
        {"op": "tap", "params": {"match_text": "搜索"}},
        {"op": "input", "params": {"text": "{contact}"}},
        {"op": "tap", "params": {"match_text": "发送"}},
    ]


async def test_done_without_tap_steps_skips_learning(tmp_path):
    from app.decision.cache import SkillCache
    store = TaskStore()
    cache = SkillCache(tmp_path / "c.json")
    engine = SpyEngine(
        Decision(actions=[Action(actionId="a-done", op="done", params={})], source="llm")
    )
    engine.cache = cache
    conn = FakeConn()
    deps = _deps(engine, tmp_path=tmp_path)
    await handle_uplink(_req(), store, conn, deps)
    ctx = store.current
    ctx.applied_steps = [
        {"op": "input", "params": {"text": "幻觉消息"}, "pkg": "com.x", "actionId": "i", "ok": True},
    ]
    await handle_uplink(_perception(seq=1, pkg="com.x"), store, conn, deps)
    assert cache._data == {}


# ---- LoopGuard 集成:同一帧反复 read → back 脱困 → 仍循环 abort ----


async def test_loop_guard_escalates_back_then_aborts(tmp_path):
    store = TaskStore()
    engine = SpyEngine()  # 恒定决策 read_screen
    conn = FakeConn()
    deps = _deps(engine, tmp_path=tmp_path)
    await handle_uplink(_req(), store, conn, deps)

    frame = lambda seq: _perception(seq=seq, pkg="com.x", nodes=[Node(id="n", text="不变")])

    # 第 1、2 帧:正常放行 read_screen
    await handle_uplink(frame(1), store, conn, deps)
    await handle_uplink(frame(2), store, conn, deps)
    assert not any(getattr(m, "op", None) == "back" for m in conn.sent)

    # 第 3 帧:触发停滞,改发 back#1
    await handle_uplink(frame(3), store, conn, deps)
    backs = [m for m in conn.sent if getattr(m, "op", None) == "back"]
    assert len(backs) == 1

    # back 未 ack 期间的帧被 F2 闸门跳过
    await handle_uplink(frame(4), store, conn, deps)
    assert len([m for m in conn.sent if getattr(m, "op", None) == "back"]) == 1

    # ack back#1 -> 自动补 read_screen;同帧再来 -> back#2
    await handle_uplink(ActionResult(actionId=backs[0].actionId, ok=True), store, conn, deps)
    await handle_uplink(frame(5), store, conn, deps)
    backs = [m for m in conn.sent if getattr(m, "op", None) == "back"]
    assert len(backs) == 2

    # ack back#2;同帧再来 -> 仍循环,直接 abort(stuck_loop)
    await handle_uplink(ActionResult(actionId=backs[1].actionId, ok=True), store, conn, deps)
    await handle_uplink(frame(6), store, conn, deps)
    assert conn.sent[-1].type == "task.abort"
    assert conn.sent[-1].reason == "stuck_loop"
    assert store.current is None


# ---- LLM 反馈通道(P1 Task 2):拦截/失败写入 ctx.llm_feedback ----


async def test_ack_error_writes_llm_feedback(tmp_path):
    store = TaskStore()
    engine = SpyEngine()  # 恒定决策 read_screen... 改为 tap 才能产出失败 ack
    engine.decision = Decision(
        actions=[Action(actionId="a-tap", op="tap", params={"match_text": "X"})],
        source="llm",
    )
    conn = FakeConn()
    deps = _deps(engine, tmp_path=tmp_path)
    await handle_uplink(_req(), store, conn, deps)
    await handle_uplink(_perception(), store, conn, deps)
    ctx = store.current
    assert ctx.llm_feedback == ""
    await handle_uplink(
        ActionResult(actionId="a-tap", ok=False, error="anchor_not_found"),
        store, conn, deps,
    )
    assert "anchor_not_found" in ctx.llm_feedback
    assert "tap" in ctx.llm_feedback


async def test_ack_ok_no_feedback(tmp_path):
    store = TaskStore()
    engine = SpyEngine()
    engine.decision = Decision(
        actions=[Action(actionId="a-tap", op="tap", params={"match_text": "X"})],
        source="llm",
    )
    conn = FakeConn()
    deps = _deps(engine, tmp_path=tmp_path)
    await handle_uplink(_req(), store, conn, deps)
    await handle_uplink(_perception(), store, conn, deps)
    ctx = store.current
    await handle_uplink(ActionResult(actionId="a-tap", ok=True), store, conn, deps)
    assert ctx.llm_feedback == ""


async def test_policy_interception_writes_llm_feedback(tmp_path):
    # SendGuard 拦截幻觉 done -> feedback 含策略名
    store = TaskStore()
    engine = SpyEngine(
        Decision(actions=[Action(actionId="d1", op="done", params={})], source="llm")
    )
    conn = FakeConn()
    deps = _deps(engine, packs=[SendMessagePack()], tmp_path=tmp_path)
    await handle_uplink(_req("给阿强发飞书消息"), store, conn, deps)
    title = Node(id="t1", text="阿强", viewIdResourceName=f"{LARK}:id/tv_title")
    send_btn = Node(id="b1", viewIdResourceName=f"{LARK}:id/btn_send", bounds=(0, 0, 100, 100))
    await handle_uplink(
        _perception(seq=1, pkg=LARK, nodes=[title, send_btn]), store, conn, deps,
    )
    ctx = store.current
    assert "send_guard" in ctx.llm_feedback


async def test_feedback_consumed_once_by_decide(tmp_path):
    # feedback 一次性:decide 消费后清空,后续帧 payload 不再携带
    store = TaskStore()
    engine = SpyEngine()
    engine.decision = Decision(
        actions=[Action(actionId="a-tap", op="tap", params={"match_text": "X"})],
        source="llm",
    )
    conn = FakeConn()
    deps = _deps(engine, tmp_path=tmp_path)
    await handle_uplink(_req(), store, conn, deps)
    await handle_uplink(_perception(seq=1), store, conn, deps)
    ctx = store.current
    await handle_uplink(
        ActionResult(actionId="a-tap", ok=False, error="anchor_not_found"),
        store, conn, deps,
    )
    assert ctx.llm_feedback != ""
    # ack 后自动补 read_screen;下一帧触发 decide,feedback 被消费
    engine.decision = Decision(actions=[Action(actionId="r", op="read_screen", params={})], source="llm")
    captured = {}

    class _SpyInput:
        def __init__(self, inner):
            self._inner = inner

        def decide(self, d):
            captured["feedback"] = d.feedback
            return self._inner.decide(d)

    deps.engine = _SpyInput(engine)
    await handle_uplink(_perception(seq=2), store, conn, deps)
    assert captured["feedback"].startswith("上一条 tap 执行失败")
    assert ctx.llm_feedback == ""


async def test_end_to_end_expect_feedback_loop(tmp_path):
    # 全链路:LLM 输出 expect title(判定 FAIL)-> read_screen -> 下一帧
    # LLM-REQ payload 的 feedback 携带实际标题
    import json as _json

    from app.decision import DecisionEngine

    class _RecLLM:
        def __init__(self):
            self.resps = iter(['expect title "阿强"', "read"])
            self.calls: list[dict] = []

        def complete(self, system, user, image_b64=None):
            self.calls.append(_json.loads(user))
            return next(self.resps, "read")

    llm = _RecLLM()
    engine = DecisionEngine(llm=llm, cache=None, replay_enabled=False)
    store = TaskStore()
    conn = FakeConn()
    deps = _deps(engine, packs=[SendMessagePack()], tmp_path=tmp_path)
    await handle_uplink(_req("给阿强发飞书消息"), store, conn, deps)
    title = Node(id="t1", text="别的群", viewIdResourceName=f"{LARK}:id/tv_title")
    await handle_uplink(_perception(seq=1, pkg=LARK, nodes=[title]), store, conn, deps)
    # 第一次 decide 输出 expect -> 下发 read_screen;端侧重抓帧上行
    await handle_uplink(_perception(seq=2, pkg=LARK, nodes=[title]), store, conn, deps)
    assert len(llm.calls) >= 2
    fb = llm.calls[1].get("feedback", "")
    assert "FAIL" in fb and "别的群" in fb
