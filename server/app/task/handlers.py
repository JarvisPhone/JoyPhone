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
from app.decision.cache import generalize_steps
from app.decision.llm import build_llm
from app.gateway.connection import JsonModel
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
    LoopGuardPolicy,
    Verdict,
    run_pipeline,
)

logger = logging.getLogger(__name__)

_SAMPLES_DIR = Path(__file__).resolve().parents[2] / "data" / "samples"


class Conn(Protocol):
    """下行通道:仅需能把协议模型发出去。"""

    async def send(self, model: JsonModel) -> None: ...


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
        await _on_action_result(uplink, store, conn, deps)
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
    if verdict.kind == "intercept":
        # pre-policy 机械拦截(如侧边栏消除):不下发 decide,直接执行策略动作
        await _dispatch(ctx, verdict.actions or [], uplink, conn, deps, store,
                        source="policy")
        return

    if ctx.fsm.state == TaskState.AWAITING_CONFIRM:
        return

    # 【F2 因果对账】有 UI 变更动作未 ack 时,本帧是动作生效前的旧帧,
    # 跳过 decide,防止 LLM 拿旧帧做终态决策(如 back 未执行就 abort)。
    if ctx.pending_mutating:
        logger.info(
            "UI 动作未 ack,跳过 decide: task_id=%s pending=%d seq=%s",
            ctx.task_id, len(ctx.pending_mutating), uplink.seq,
        )
        return

    profile = scenario.ui_profile(ctx.target_pkg) if scenario is not None else None
    _maybe_classify_entry(uplink, ctx, scenario)
    # feedback 一次性消费:随本次 decide 送达 LLM 后清空
    feedback, ctx.llm_feedback = ctx.llm_feedback, ""
    decision = deps.engine.decide(
        DecideInput(
            goal=ctx.goal,
            frame=uplink,
            target_pkg=ctx.target_pkg,
            cursor=ctx.cursor,
            bound_skill=ctx.bound_skill,
            guard=ctx.guard,
            title_keywords=tuple(profile.title_rid_keywords) if profile else (),
            bindings=ctx.bindings,
            cache_context=ctx.cache_context if uplink.pkg == ctx.target_pkg else "",
            cache_disabled=ctx.cache_disabled,
            feedback=feedback,
        )
    )
    # expect 判定结果经 meta 返回,存回 feedback 通道随下一帧送达
    if decision.meta.get("feedback"):
        ctx.llm_feedback = str(decision.meta["feedback"])
    ctx.steps += 1
    source = decision.meta.get("source", decision.source)
    _record_decision_metrics(deps, ctx, source)
    ctx.decided_actions = decision.actions or []

    post = list(scenario.post_policies()) if scenario is not None else []
    # 内核循环守卫排在场景策略之后:场景的语义守卫(确认/错群/done 门槛)
    # 先按自己的语义处置,兜不住的停滞才轮到机械 back。
    post.append(LoopGuardPolicy())
    post_verdict = run_pipeline(post, uplink, ctx)
    if post_verdict.kind == "terminate":
        await _terminate(ctx, post_verdict, conn, deps, store)
        return
    if post_verdict.kind == "intercept":
        actions = post_verdict.actions or []
        if ctx.decided_actions:
            # LLM 反馈通道:决策被策略拦截(幻觉 done/标题栏点击等),告知原因
            ctx.llm_feedback = "上一条 %s 被策略 %s 拦截" % (
                ctx.decided_actions[0].op, post_verdict.policy,
            )
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
        await _dispatch(ctx, actions, uplink, conn, deps, store, source="policy")
        return
    await _dispatch(ctx, decision.actions, uplink, conn, deps, store, source=source)


async def _dispatch(
    ctx: TaskContext,
    actions,
    frame: Perception,
    conn: Conn,
    deps: HandlerDeps,
    store: TaskStore,
    source: str = "",
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
        ctx.applied_steps.append({
            "op": action.op,
            "params": action.params,
            "pkg": frame.pkg,
            "actionId": action.actionId,
            "ok": None,
        })
        ctx.pending_sources[action.actionId] = source
        if action.op in _MUTATING_OPS:
            ctx.pending_mutating.add(action.actionId)
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

# 会改变 UI 的动作:ack 前到达的帧视为「动作前旧帧」(见 _on_perception 的 F2 闸门)。
_MUTATING_OPS = frozenset({"tap", "input", "swipe", "back", "home"})


async def _on_action_result(
    uplink: ActionResult, store: TaskStore, conn: Conn, deps: HandlerDeps
) -> None:
    ctx = store.current
    if ctx is None:
        return
    ctx.history.append({"actionId": uplink.actionId, "ok": uplink.ok})
    source = ctx.pending_sources.pop(uplink.actionId, "")
    was_mutating = uplink.actionId in ctx.pending_mutating
    ctx.pending_mutating.discard(uplink.actionId)
    # 动作↔步骤对账:ack 结果回写到 applied_steps,供 learn 时过滤失败步骤
    failed_op = ""
    for step in reversed(ctx.applied_steps):
        if step.get("actionId") == uplink.actionId:
            step["ok"] = uplink.ok
            failed_op = str(step.get("op", ""))
            break
    if not uplink.ok and uplink.error and failed_op:
        # LLM 反馈通道:执行失败须让 LLM 知道原因(否则它只能从屏幕猜)
        ctx.llm_feedback = "上一条 %s 执行失败:%s" % (failed_op, uplink.error)
    if uplink.ok:
        deps.metrics.record_step(ctx.task_id)
        if source in ("cache", "skill"):
            ctx.cursor.advance()
        ctx.cache_step_fails = 0
        if uplink.actionId == ctx.confirm.resend_action_id:
            # confirm 补发的发送 tap ack ok = 真实发送完成
            ctx.post_send.acked = True
            ctx.confirm.resend_action_id = None
    elif source == "cache":
        # 回放熔断:同一步连续 ack 失败达阈值,整条作废并本场禁用,
        # 回落 skill/LLM(旧行为是不推进 cursor 无限重放同一必败步骤)
        ctx.cache_step_fails += 1
        if ctx.cache_step_fails >= Config.CACHE_STEP_MAX_FAILS:
            cache = deps.engine.cache
            if cache is not None:
                cache.mark_miss(ctx.goal, ctx.cache_context or ctx.target_pkg, ctx.cursor.index)
            ctx.cache_disabled = True
            logger.warning(
                "[CACHE_FUSE] task_id=%s cursor=%d 连续 %d 次 ack 失败,整条作废并禁用",
                ctx.task_id, ctx.cursor.index, ctx.cache_step_fails,
            )
    # 【F2】mutating 动作全部 ack 后,主动补一帧 read_screen:端侧此时已完成
    # 动作,抓到的才是「动作后的新帧」,驱动下一轮 decide,也避免动作无事件
    # (如 tap 落空)时云端停摆。ok=False 同样补帧观察现场。
    if was_mutating and not ctx.pending_mutating:
        await conn.send(Action(actionId=str(uuid.uuid4()), op="read_screen", params={}))


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
        ctx.applied_steps.append({
            "op": "tap",
            "params": send_act.params,
            "pkg": ctx.target_pkg,
            "actionId": send_act.actionId,
            "ok": None,
        })
        # post_send.acked 只在补发 tap「ack ok」后才置位(见 _on_action_result):
        # 派发≠发送成功——补发可能 anchor_not_found(页面已变),提前置位会让
        # 巡逻策略误判已发送而 abort(真机八轮任务3)。
        ctx.confirm.resend_action_id = send_act.actionId
        ctx.pending_mutating.add(send_act.actionId)
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


def _maybe_classify_entry(
    frame: Perception, ctx: TaskContext, scenario: ScenarioPack | None
) -> None:
    """首次进入目标 app 时做落地页分类,并设置 cache_context。

    每次进入 app 的落地页可能不同(冷启动在主页/热启动在上次聊天页):
    - 分类结果写入 ctx.entry_state,cache 学习与回放都按入口状态分开;
    - 若已在目标会话且 skill 未起步(cursor=0),cursor 快进至 verify_title 步,
      跳过搜索段(热启动直接恢复在目标群里的常见场景)。
    """
    if scenario is None or ctx.entry_state is not None:
        return
    if not ctx.target_pkg or frame.pkg != ctx.target_pkg:
        return
    classify = getattr(scenario, "classify_entry", None)
    if classify is None:
        return
    state = classify(frame, ctx)
    ctx.entry_state = state
    ctx.cache_context = "%s|%s" % (frame.pkg, state)
    logger.info(
        "[ENTRY_STATE] task_id=%s pkg=%s entry=%s", ctx.task_id, frame.pkg, state
    )
    if state == "target_chat" and ctx.cursor.index == 0 and ctx.bound_skill is not None:
        for i, s in enumerate(ctx.bound_skill.steps):
            if s.op == "verify_title":
                ctx.cursor.index = i
                logger.info(
                    "[ENTRY_ALIGN] 已在目标会话,skill cursor 快进至 verify_title index=%d",
                    i,
                )
                break


def _learn_cache(deps: HandlerDeps, ctx: TaskContext) -> None:
    """多次验证 + 泛化沉淀:清洗成功轨迹,交 record_success 计数,达标才转正。"""
    cache = deps.engine.cache
    if cache is None or not ctx.applied_steps:
        return
    steps = generalize_steps(ctx.applied_steps, ctx.target_pkg, ctx.bindings)
    if not steps:
        logger.info("[CACHE_SKIP] task_id=%s 泛化后无可沉淀步骤", ctx.task_id)
        return
    if not any(s["op"] == "tap" for s in steps):
        # 无 tap 的轨迹说明连发送类动作都没发生,不是完整成功路径
        logger.info("[CACHE_SKIP] task_id=%s 轨迹无 tap 步骤,拒绝沉淀", ctx.task_id)
        return
    context = ctx.cache_context or ctx.target_pkg
    cache.record_success(ctx.goal, context, steps)


def _record_decision_metrics(deps: HandlerDeps, ctx: TaskContext, source: str) -> None:
    # pkg_guard 未消耗 LLM,不计 llm_call(F4:避免虚增)。
    if source == "skill":
        deps.metrics.record_skill_hit(ctx.task_id)
    elif source == "cache":
        deps.metrics.record_cache_hit(ctx.task_id)
    elif source == "llm":
        deps.metrics.record_llm_call(ctx.task_id)
