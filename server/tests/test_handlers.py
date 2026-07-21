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
            actions=[Action(actionId="a-tap", op="tap", params={"x": "50", "y": "50"})],
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
