# server/app/task/handlers.py
"""任务层 uplink handlers(T11)。

handle_uplink 是协议上行(已 parse 的 Uplink 模型)的唯一入口,按类型分派:
task.request 装配场景并整体新建 TaskContext;perception 走 seq 闸门 ->
PRE 内核+场景策略 -> engine.decide -> POST 场景策略 -> 动作下发;
action.result 记 history 并按上帧决策来源推进 cursor;heartbeat 轻量回
ack;task.confirm_response 与 event.newMessage 沿用旧 gateway.py(0d1ccbd)
:234-310 / :312-359 语义,状态走 TaskFSM;sample.capture 落盘。

conn 仅需 async send(model)(模型有 to_json());deps 承载
engine/scenario_packs/metrics/max_steps 与可选 negotiation bot。
"""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

from app.decision import BoundSkill, DecideInput, DecisionEngine
from app.decision.llm import build_llm
from app.infra.config import Config
from app.infra.metrics import MetricsCollector
from app.negotiation import NegotiationBot
from app.protocol import (
    Action,
    ActionResult,
    ConfirmResponse,
    Heartbeat,
    HeartbeatAck,
    NewMessage,
    Perception,
    SampleCapture,
    TaskAbort,
    TaskConfirm,
    TaskDone,
    TaskRequest,
    TaskStart,
    Uplink,
)
from app.scenario.base import ScenarioPack, select_scenario
from app.task.context import TaskContext, TaskStore
from app.task.fsm import TaskState
from app.task.policies import (
    BudgetPolicy,
    ConfirmTimeoutPolicy,
    Verdict,
    run_pipeline,
)

logger = logging.getLogger(__name__)

_SAMPLES_DIR = Path(__file__).resolve().parents[2] / "data" / "samples"


class Conn(Protocol):
    """下行通道:仅需能把协议模型发出去。"""

    async def send(self, model) -> None: ...


@dataclass
class HandlerDeps:
    """handle_uplink 的依赖包;negotiation 缺省时按需 build_llm 懒构造。"""

    engine: DecisionEngine
    scenario_packs: Sequence[ScenarioPack]
    metrics: MetricsCollector
    max_steps: int = Config.MAX_STEPS_DEFAULT
    negotiation: NegotiationBot | None = None


def persist_sample(sample: SampleCapture, base_dir: Path | None = None) -> Path:
    """把一帧采样落盘为 <label>-<ts>.json,返回落盘路径。"""
    target_dir = base_dir if base_dir is not None else _SAMPLES_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / ("%s-%s.json" % (sample.label, sample.ts))
    path.write_text(sample.model_dump_json(indent=2), encoding="utf-8")
    return path


async def handle_uplink(
    uplink: Uplink,
    store: TaskStore,
    conn: Conn,
    deps: HandlerDeps,
) -> None:
    if isinstance(uplink, TaskRequest):
        await _on_task_request(uplink, store, conn, deps)
    elif isinstance(uplink, Perception):
        await _on_perception(uplink, store, conn, deps)
    elif isinstance(uplink, ActionResult):
        await _on_action_result(uplink, store, deps)
    elif isinstance(uplink, Heartbeat):
        await conn.send(HeartbeatAck(deviceId=uplink.deviceId, ts=int(time.time())))
    elif isinstance(uplink, ConfirmResponse):
        await _on_confirm_response(uplink, store, conn, deps)
    elif isinstance(uplink, NewMessage):
        await _on_new_message(uplink, store, conn, deps)
    elif isinstance(uplink, SampleCapture):
        _on_sample_capture(uplink)


# ---- task.request ----


async def _on_task_request(
    uplink: TaskRequest, store: TaskStore, conn: Conn, deps: HandlerDeps
) -> None:
    scenario = select_scenario(deps.scenario_packs, uplink.goal)
    ctx = store.new_task(
        uplink.goal,
        scenario=scenario.name if scenario is not None else None,
        max_steps=deps.max_steps,
    )
    if scenario is not None:
        resolved = scenario.resolve_target(uplink.goal)
        ctx.target_pkg = getattr(resolved, "pkg", "") or ""
        ctx.target_chat = getattr(resolved, "chat", None)
        ctx.bindings = dict(getattr(resolved, "bindings", None) or {})
        for tpl in scenario.skills() or []:
            bound = BoundSkill.bind(tpl, ctx.bindings)
            if bound is not None:
                ctx.bound_skill = bound
                break
    logger.info(
        "task.request: task_id=%s goal=%s scenario=%s pkg=%s chat=%s",
        ctx.task_id, ctx.goal, ctx.scenario, ctx.target_pkg, ctx.target_chat,
    )
    await conn.send(TaskStart(taskId=ctx.task_id, goal=ctx.goal, target=ctx.target_pkg))
    deps.metrics.start_task(ctx.task_id, ctx.goal, ctx.target_pkg or "")


# ---- perception ----


async def _on_perception(
    uplink: Perception, store: TaskStore, conn: Conn, deps: HandlerDeps
) -> None:
    ctx = store.current
    if ctx is None:
        return
    if uplink.seq <= ctx.last_consumed_seq:
        logger.info(
            "丢弃乱序/重复帧: task_id=%s seq=%s last_consumed_seq=%s",
            ctx.task_id, uplink.seq, ctx.last_consumed_seq,
        )
        return
    ctx.last_consumed_seq = uplink.seq

    scenario = _scenario_for(deps, ctx)
    pre = [BudgetPolicy(), ConfirmTimeoutPolicy()]
    if scenario is not None:
        pre = pre + list(scenario.pre_policies())
    verdict = run_pipeline(pre, uplink, ctx)
    if verdict.kind == "terminate":
        await _terminate(ctx, verdict, conn, deps, store)
        return

    if ctx.fsm.state == TaskState.AWAITING_CONFIRM:
        return

    profile = scenario.ui_profile(ctx.target_pkg) if scenario is not None else None
    decision = deps.engine.decide(
        DecideInput(
            goal=ctx.goal,
            frame=uplink,
            target_pkg=ctx.target_pkg,
            cursor=ctx.cursor,
            bound_skill=ctx.bound_skill,
            guard=ctx.guard,
            title_keywords=tuple(profile.title_rid_keywords) if profile else (),
        )
    )
    ctx.steps += 1
    ctx.last_decision_source = decision.meta.get("source", decision.source)
    _record_decision_metrics(deps, ctx)
    ctx.decided_actions = decision.actions or []

    post = list(scenario.post_policies()) if scenario is not None else []
    post_verdict = run_pipeline(post, uplink, ctx)
    if post_verdict.kind == "terminate":
        await _terminate(ctx, post_verdict, conn, deps, store)
        return
    if post_verdict.kind == "intercept":
        actions = post_verdict.actions or []
        if not actions and ctx.confirm.confirm_id:
            await conn.send(
                TaskConfirm(
                    taskId=ctx.task_id,
                    confirmId=ctx.confirm.confirm_id,
                    target=ctx.target_chat or "",
                    message=ctx.confirm.message_text,
                    timeoutMs=Config.CONFIRM_TIMEOUT_MS,
                )
            )
            return
        await _dispatch(ctx, actions, uplink, conn, deps, store)
        return
    await _dispatch(ctx, decision.actions, uplink, conn, deps, store)


async def _dispatch(
    ctx: TaskContext,
    actions,
    frame: Perception,
    conn: Conn,
    deps: HandlerDeps,
    store: TaskStore,
) -> None:
    for action in actions:
        if action.op == "done":
            _ensure_state(ctx, TaskState.DONE, "action_done")
            _learn_cache(deps, ctx)
            await conn.send(
                TaskDone(taskId=ctx.task_id, result="ok", summary="task completed")
            )
            deps.metrics.finish_task(ctx.task_id, "completed")
            store.clear()
            return
        if action.op == "abort":
            _ensure_state(ctx, TaskState.ABORT, "action_abort")
            reason = action.params.get("reason") or "llm_abort"
            await conn.send(TaskAbort(taskId=ctx.task_id, reason=reason))
            deps.metrics.finish_task(ctx.task_id, "aborted", reason)
            store.clear()
            return
        logger.info("下发动作: task_id=%s op=%s params=%s", ctx.task_id, action.op, action.params)
        ctx.applied_steps.append({"op": action.op, "params": action.params})
        await conn.send(action)


async def _terminate(
    ctx: TaskContext,
    verdict: Verdict,
    conn: Conn,
    deps: HandlerDeps,
    store: TaskStore,
) -> None:
    if verdict.status == "completed":
        _ensure_state(ctx, TaskState.DONE, verdict.reason)
        _learn_cache(deps, ctx)
        await conn.send(TaskDone(taskId=ctx.task_id, result="ok", summary=verdict.reason))
        deps.metrics.finish_task(ctx.task_id, "completed")
    else:
        _ensure_state(ctx, TaskState.ABORT, verdict.reason)
        await conn.send(TaskAbort(taskId=ctx.task_id, reason=verdict.reason))
        deps.metrics.finish_task(ctx.task_id, verdict.status or "aborted", verdict.reason)
    store.clear()


# ---- action.result ----


async def _on_action_result(
    uplink: ActionResult, store: TaskStore, deps: HandlerDeps
) -> None:
    ctx = store.current
    if ctx is None:
        return
    ctx.history.append({"actionId": uplink.actionId, "ok": uplink.ok})
    if uplink.ok:
        deps.metrics.record_step(ctx.task_id)
        if ctx.last_decision_source in ("cache", "skill"):
            ctx.cursor.advance()


# ---- task.confirm_response ----


async def _on_confirm_response(
    uplink: ConfirmResponse, store: TaskStore, conn: Conn, deps: HandlerDeps
) -> None:
    ctx = store.current
    if ctx is None:
        return
    if ctx.fsm.state != TaskState.AWAITING_CONFIRM:
        logger.warning(
            "confirm_response 状态非法,忽略: task_id=%s state=%s",
            ctx.task_id, ctx.fsm.state.value,
        )
        return
    if uplink.confirmId != ctx.confirm.confirm_id:
        logger.warning(
            "confirm_response id 不符,忽略: got=%s expected=%s",
            uplink.confirmId, ctx.confirm.confirm_id,
        )
        return
    logger.info(
        "task.confirm_response: task_id=%s approved=%s reason=%s",
        ctx.task_id, uplink.approved, uplink.reason,
    )
    ctx.confirm.confirm_id = None
    if uplink.approved:
        if ctx.confirm.reverted:
            logger.warning(
                "[APPROVE_BUT_REVERTED] task_id=%s 观察窗内已撤回,拒绝下发 tap",
                ctx.task_id,
            )
            ctx.confirm.pending_action = None
            _ensure_state(ctx, TaskState.ABORT, "approve_but_pre_send_reverted")
            await conn.send(
                TaskAbort(taskId=ctx.task_id, reason="approve_but_pre_send_reverted")
            )
            deps.metrics.finish_task(
                ctx.task_id, "aborted", "approve_but_pre_send_reverted"
            )
            store.clear()
            return
        pending = ctx.confirm.pending_action
        ctx.confirm.pending_action = None
        ctx.fsm.force(TaskState.RUNNING, "confirm_approved")
        if pending is None:
            logger.error("approved 但无 pending action,abort: task_id=%s", ctx.task_id)
            _ensure_state(ctx, TaskState.ABORT, "no_pending_after_approve")
            await conn.send(
                TaskAbort(taskId=ctx.task_id, reason="no_pending_after_approve")
            )
            deps.metrics.finish_task(ctx.task_id, "aborted", "no_pending_after_approve")
            store.clear()
            return
        send_act = Action(
            actionId=str(uuid.uuid4()), op="tap", params={**pending.params}
        )
        ctx.applied_steps.append({"op": "tap", "params": send_act.params})
        ctx.post_send.acked = True
        await conn.send(send_act)
    else:
        ctx.confirm.pending_action = None
        ctx.fsm.force(TaskState.RUNNING, "confirm_rejected")
        logger.info(
            "[CONFIRM_REJECTED] task_id=%s reason=%s", ctx.task_id, uplink.reason
        )


# ---- event.newMessage ----


async def _on_new_message(
    uplink: NewMessage, store: TaskStore, conn: Conn, deps: HandlerDeps
) -> None:
    ctx = store.current
    if ctx is None:
        return
    logger.info("event.newMessage: task_id=%s from=%s text=%s",
                ctx.task_id, uplink.sender, uplink.text)
    bot = deps.negotiation
    if bot is None:
        bot = NegotiationBot(llm=build_llm())
        deps.negotiation = bot
    ctx.negotiation.append({"role": "user", "content": uplink.text})
    try:
        result = bot.respond(
            goal=ctx.goal, incoming=uplink.text, history=ctx.negotiation[:-1]
        )
    except Exception as exc:
        logger.error("协商异常: task_id=%s err=%s", ctx.task_id, exc)
        reason = "negotiation_error: %s" % exc
        _ensure_state(ctx, TaskState.ABORT, reason)
        await conn.send(TaskAbort(taskId=ctx.task_id, reason=reason))
        deps.metrics.finish_task(ctx.task_id, "error", str(exc))
        store.clear()
        return

    action = result.get("action", "continue")
    reply = result.get("reply", "")
    if action == "done":
        _ensure_state(ctx, TaskState.DONE, "negotiation_done")
        await conn.send(
            TaskDone(taskId=ctx.task_id, result="ok", summary="negotiation completed")
        )
        deps.metrics.finish_task(ctx.task_id, "completed")
        store.clear()
        return
    if action == "escalate":
        _ensure_state(ctx, TaskState.ABORT, "escalated_to_human")
        await conn.send(TaskAbort(taskId=ctx.task_id, reason="escalated_to_human"))
        deps.metrics.finish_task(ctx.task_id, "escalated")
        store.clear()
        return
    if reply:
        ctx.negotiation.append({"role": "agent", "content": reply})
    ctx.fsm.transition(TaskState.WAITING_EVENT, reason="negotiation_continue")


# ---- sample.capture ----


def _on_sample_capture(uplink: SampleCapture) -> None:
    try:
        saved = persist_sample(uplink)
        logger.info(
            "sample.capture 落盘: label=%s nodes=%d saved=%s",
            uplink.label, len(uplink.nodeTree), saved.name,
        )
    except OSError as exc:
        logger.error("sample.capture 落盘失败: label=%s err=%s", uplink.label, exc)


# ---- helpers ----


def _scenario_for(deps: HandlerDeps, ctx: TaskContext) -> ScenarioPack | None:
    if ctx.scenario is None:
        return None
    for pack in deps.scenario_packs:
        if pack.name == ctx.scenario:
            return pack
    return None


def _ensure_state(ctx: TaskContext, to: TaskState, reason: str) -> None:
    if ctx.fsm.state == to:
        return
    if not ctx.fsm.transition(to, reason=reason):
        ctx.fsm.force(to, reason=reason)


def _learn_cache(deps: HandlerDeps, ctx: TaskContext) -> None:
    cache = deps.engine.cache
    if cache is not None and ctx.applied_steps:
        cache.learn(ctx.goal, ctx.target_pkg, ctx.applied_steps)


def _record_decision_metrics(deps: HandlerDeps, ctx: TaskContext) -> None:
    if ctx.last_decision_source == "skill":
        deps.metrics.record_skill_hit(ctx.task_id)
    elif ctx.last_decision_source == "cache":
        deps.metrics.record_cache_hit(ctx.task_id)
    else:
        deps.metrics.record_llm_call(ctx.task_id)
