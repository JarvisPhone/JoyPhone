import json
import logging
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, WebSocket
from starlette.websockets import WebSocketDisconnect

from app.app_goal_resolver import extract_target, resolve_target_pkg
from app.chat_title_helpers import (
    detect_chat_title,
    is_send_button,
    match_chat_title,
)
from app.comm_log import log_up, log_down
from app.decision import DecisionEngine
from app.llm import FakeLLM, build_llm
from app.metrics import get_metrics_collector
from app.protocol import (
    Action,
    ConfirmResponse,
    SampleCapture,
    TaskAbort,
    TaskConfirm,
    TaskDone,
    TaskStart,
    parse_uplink,
)
from app.skill_cache import SkillCache
from app.skills import SkillLibrary

logger = logging.getLogger("phoneagent.gateway")
if not logger.handlers:
    _fmt = logging.Formatter("%(asctime)s [phoneagent] %(message)s")
    _h = logging.StreamHandler()
    _h.setFormatter(_fmt)
    logger.addHandler(_h)
    _log_dir = Path(__file__).resolve().parents[1] / "logs"
    _log_dir.mkdir(exist_ok=True)
    _fh = logging.FileHandler(_log_dir / "gateway.log", encoding="utf-8")
    _fh.setFormatter(_fmt)
    logger.addHandler(_fh)
    logger.setLevel(logging.INFO)
    logger.propagate = False

_FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "feishu_happy_path.json"

_DEFAULT_GOAL = "等待用户下发任务目标"


_SAMPLES_DIR = Path(__file__).resolve().parents[1] / "data" / "samples"


def _persist_sample(sample: "SampleCapture", base_dir: Path | None = None) -> Path:
    """把一帧采样落盘为 <label>-<ts>.json,返回落盘路径。"""
    target_dir = base_dir if base_dir is not None else _SAMPLES_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{sample.label}-{sample.ts}.json"
    path.write_text(sample.model_dump_json(indent=2), encoding="utf-8")
    return path


def _load_fixture_steps() -> list[dict]:
    if not _FIXTURE.exists():
        return []
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _build_engine() -> DecisionEngine:
    fake = os.getenv("PHONEAGENT_FAKE_LLM")
    llm = FakeLLM(json.loads(fake)) if fake else build_llm()
    cache = SkillCache(Path(os.getenv("SKILL_CACHE_PATH", "data/skill_cache.json")))
    return DecisionEngine(llm=llm, skills=SkillLibrary(), cache=cache)


def create_app() -> FastAPI:
    app = FastAPI()
    max_steps = int(os.getenv("PHONEAGENT_MAX_STEPS", "40"))
    metrics = get_metrics_collector()

    @app.websocket("/ws/{device_id}")
    async def ws_gateway(websocket: WebSocket, device_id: str) -> None:
        await websocket.accept()
        logger.info("WS connected device=%s", device_id)
        from app.session import Session, State
        from app.negotiation import NegotiationBot

        engine = _build_engine()
        llm = build_llm()
        negotiation_bot = NegotiationBot(llm=llm)

        session = Session(
            task_id=f"task-{uuid.uuid4().hex[:8]}",
            goal=_DEFAULT_GOAL,
            target=device_id,
            max_steps=max_steps,
        )
        metrics.start_task(session.task_id, session.goal, device_id)

        cursor = 0
        history: list[dict] = []
        applied_steps: list[dict] = []
        last_pkg = ""
        negotiation_history: list[dict] = []
        skill_name: str | None = None

        # Toast 确认相关状态
        target_chat_name: str | None = extract_target(session.goal)
        target_app_pkg: str | None = resolve_target_pkg(session.goal)
        pending_send_action: Action | None = None  # 被拦截的 input action
        pending_send_button_node: Node | None = None  # 当前屏的「发送」按钮节点
        pending_confirm_id: str | None = None
        pending_message_text: str = ""
        confirm_count = 0  # 全程只确认一次,避免循环

        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                logger.info("WS disconnected device=%s", device_id)
                break

            try:
                uplink = parse_uplink(raw)
                log_up(uplink.type, raw)
            except ValueError:
                _abort = TaskAbort(taskId=session.task_id, reason="invalid_uplink").to_json()
                log_down("task.abort", _abort)
                await websocket.send_text(_abort)
                metrics.finish_task(session.task_id, "aborted", "invalid_uplink")
                break

            if uplink.type == "action.result":
                history.append({"actionId": uplink.actionId, "ok": uplink.ok, "atEnd": uplink.atEnd})
                if uplink.ok:
                    cursor += 1
                    metrics.record_step(session.task_id)
                continue

            if uplink.type == "sample.capture":
                try:
                    saved = _persist_sample(uplink)
                    logger.info("sample.capture label=%s nodes=%d saved=%s",
                                uplink.label, len(uplink.nodeTree), saved.name)
                except OSError as exc:
                    logger.error("sample.capture persist failed label=%s err=%s",
                                 uplink.label, exc)
                continue

            if uplink.type == "heartbeat":
                _hb = Action(actionId=str(uuid.uuid4()), op="read_screen", params={}).to_json()
                log_down("action", _hb)
                await websocket.send_text(_hb)
                continue

            if uplink.type == "task.request":
                session.goal = uplink.goal
                session.state = State.NAVIGATING
                target_chat_name = extract_target(session.goal)
                target_app_pkg = resolve_target_pkg(session.goal)
                pending_send_action = None
                pending_send_button_node = None
                pending_confirm_id = None
                pending_message_text = ""
                confirm_count = 0
                logger.info("task.request goal=%s target_chat=%s pkg=%s", uplink.goal, target_chat_name, target_app_pkg)
                _ts_msg = TaskStart(taskId=session.task_id, goal=session.goal, target=device_id).to_json()
                log_down("task.start", _ts_msg)
                await websocket.send_text(_ts_msg)
                continue

            if uplink.type == "task.confirm_response":
                if session.state != State.AWAITING_CONFIRM:
                    logger.warning(
                        "confirm_response in wrong state=%s (ignoring)",
                        session.state.value,
                    )
                    continue
                if uplink.confirmId != pending_confirm_id:
                    logger.warning(
                        "confirm_response id mismatch: got=%s expected=%s",
                        uplink.confirmId, pending_confirm_id,
                    )
                    continue
                logger.info(
                    "task.confirm_response approved=%s reason=%s",
                    uplink.approved, uplink.reason,
                )
                pending_confirm_id = None
                if uplink.approved:
                    # 用户确认(Toast 5 秒到点 / App 主动)
                    session.transition(State.SENT)
                    if pending_send_action is not None and pending_send_button_node is not None:
                        msg_text = pending_send_action.params.get("text", "")
                        input_id = pending_send_action.params.get("id", "")
                        # 1) 下发 input（让 App 把文案填进编辑框;如果编辑框已经有内容则效果等同 noop）
                        input_act = Action(
                            actionId=str(uuid.uuid4()),
                            op="input",
                            params={
                                **pending_send_action.params,
                            },
                        )
                        _ia = input_act.to_json()
                        log_down("action", _ia)
                        await websocket.send_text(_ia)
                        # 2) 下发 tap 发送按钮（坐标从 send_node.bounds 中心算出来）
                        center = _bounds_center(pending_send_button_node.bounds)
                        if center is None:
                            logger.error("approved but send_button has no bounds → abort")
                            _ab = TaskAbort(taskId=session.task_id, reason="approved_but_no_send_bounds").to_json()
                            log_down("task.abort", _ab)
                            await websocket.send_text(_ab)
                            metrics.finish_task(session.task_id, "aborted", "approved_but_no_send_bounds")
                            break
                        send_act = Action(
                            actionId=str(uuid.uuid4()),
                            op="tap",
                            params={"id": "", "x": str(center[0]), "y": str(center[1])},
                        )
                        _sa = send_act.to_json()
                        log_down("action", _sa)
                        await websocket.send_text(_sa)
                        applied_steps.append({"op": "input", "params": pending_send_action.params})
                        applied_steps.append({"op": "tap", "params": send_act.params})
                        pending_send_action = None
                        pending_send_button_node = None
                    else:
                        logger.error("approved but no pending action/button → abort")
                        _ab = TaskAbort(taskId=session.task_id, reason="no_pending_after_approve").to_json()
                        log_down("task.abort", _ab)
                        await websocket.send_text(_ab)
                        metrics.finish_task(session.task_id, "aborted", "no_pending_after_approve")
                        break
                else:
                    # 取消:把 input 撤回不发,转入 IN_CHAT 让 LLM 重新决策(可改文案/重试)。
                    # SENT<-IN_CHAT 不在 _ALLOWED,改用更宽松的处理:不转换状态但清掉 pending,
                    # 让下一帧上行时由正常决策路径继续。
                    pending_send_action = None
                    pending_send_button_node = None
                    session.transition(State.IN_CHAT)
                    logger.info("[CONFIRM_REJECTED] reason=%s → back to IN_CHAT for re-decide", uplink.reason)
                    continue
                continue

            if uplink.type == "event.newMessage":
                sender = getattr(uplink, "sender", "unknown")
                text = getattr(uplink, "text", "")
                logger.info("event.newMessage from=%s text=%s", sender, text)

                negotiation_history.append({"role": "user", "content": text})

                try:
                    result = negotiation_bot.respond(
                        goal=session.goal,
                        incoming=text,
                        history=negotiation_history[:-1],
                    )
                    action = result.get("action", "continue")
                    reply = result.get("reply", "")

                    if action == "done":
                        session.transition(State.DONE)
                        _done = TaskDone(
                            taskId=session.task_id, result="ok", summary="negotiation completed"
                        ).to_json()
                        log_down("task.done", _done)
                        await websocket.send_text(_done)
                        metrics.finish_task(session.task_id, "completed")
                        break

                    if action == "escalate":
                        session.transition(State.ABORT)
                        _ab = TaskAbort(taskId=session.task_id, reason="escalated_to_human").to_json()
                        log_down("task.abort", _ab)
                        await websocket.send_text(_ab)
                        metrics.finish_task(session.task_id, "escalated")
                        break

                    if reply:
                        negotiation_history.append({"role": "agent", "content": reply})

                    session.transition(State.NEGOTIATING)

                except Exception as e:
                    logger.error(f"Negotiation error: {e}")
                    session.transition(State.ABORT)
                    _ab = TaskAbort(taskId=session.task_id, reason=f"negotiation_error: {e}").to_json()
                    log_down("task.abort", _ab)
                    await websocket.send_text(_ab)
                    metrics.finish_task(session.task_id, "error", str(e))
                    break
                continue

            if uplink.type != "perception":
                continue

            if session.budget_exhausted():
                session.transition(State.ABORT)
                _be = TaskAbort(taskId=session.task_id, reason="budget_exhausted").to_json()
                log_down("task.abort", _be)
                await websocket.send_text(_be)
                metrics.finish_task(session.task_id, "aborted", "budget_exhausted")
                break

            last_pkg = uplink.pkg or last_pkg
            logger.info(
                "perception pkg=%s nodes=%d cursor=%d state=%s",
                uplink.pkg, len(uplink.nodeTree), cursor, session.state.value,
            )

            # 【AWAITING_CONFIRM 期间】飞书/微信被切走 -> 自动取消
            if session.state == State.AWAITING_CONFIRM:
                if target_app_pkg and uplink.pkg and uplink.pkg != target_app_pkg:
                    logger.info(
                        "[CONFIRM_CANCELLED] pkg=%s != target=%s during AWAITING_CONFIRM -> auto reject",
                        uplink.pkg, target_app_pkg,
                    )
                    pending_confirm_id = None
                    session.transition(State.ABORT)
                    pending_send_action = None
                    pending_send_button_node = None
                    _ab = TaskAbort(taskId=session.task_id, reason="confirm_rejected:app_left_during_confirm").to_json()
                    log_down("task.abort", _ab)
                    await websocket.send_text(_ab)
                    metrics.finish_task(session.task_id, "aborted", "confirm_rejected:app_left_during_confirm")
                    break
                continue

            skill_name = engine._select_skill(session.goal, uplink.pkg) if skill_name is None else None

            target_pkg = resolve_target_pkg(session.goal) or ""
            actions = engine.decide(
                goal=session.goal,
                perception=uplink,
                skill_name=skill_name,
                cursor=cursor,
                history=history,
                target_pkg=target_pkg,
                guard=session.guard,
            )

            if skill_name:
                metrics.record_skill_hit(session.task_id)
            else:
                metrics.record_llm_call(session.task_id)

            terminate = False
            for action in actions:
                logger.info("decided op=%s params=%s", action.op, action.params)

                if action.op == "done":
                    session.transition(State.DONE)
                    if applied_steps:
                        engine._cache.learn(session.goal, last_pkg, applied_steps)
                    _done = TaskDone(
                        taskId=session.task_id, result="ok", summary="task completed"
                    ).to_json()
                    log_down("task.done", _done)
                    await websocket.send_text(_done)
                    metrics.finish_task(session.task_id, "completed")
                    terminate = True
                    break

                if action.op == "abort":
                    session.transition(State.ABORT)
                    _ab = TaskAbort(taskId=session.task_id, reason="llm_abort").to_json()
                    log_down("task.abort", _ab)
                    await websocket.send_text(_ab)
                    metrics.finish_task(session.task_id, "aborted", "llm_abort")
                    terminate = True
                    break

                # 【发送前确认】LLM 做完 input 之后,先不发给 App,改发 task.confirm 让用户确认。
                # 收到 confirm_response 后再由 gateway 把 input 和「tap 发送按钮」两条动作一起发下去。
                if (
                    action.op == "input"
                    and confirm_count == 0
                    and target_app_pkg
                    and uplink.pkg == target_app_pkg
                    and target_chat_name
                ):
                    current_title = detect_chat_title(uplink.nodeTree)
                    if current_title and match_chat_title(target_chat_name, current_title):
                        # 群名匹配 -> 拦截 input,下发 confirm
                        send_node = _find_send_button(uplink.nodeTree)
                        if send_node is None:
                            # 屏幕上没发送按钮 -> LLM 还在打字阶段,正常下发 input,等发送按钮出现
                            logger.info("[CONFIRM_SKIP] no send_button in view yet → forward input as-is")
                        else:
                            confirm_id = f"cfm-{uuid.uuid4().hex[:8]}"
                            pending_confirm_id = confirm_id
                            pending_send_action = action
                            pending_send_button_node = send_node
                            pending_message_text = action.params.get("text", "")
                            _confirm = TaskConfirm(
                                taskId=session.task_id,
                                confirmId=confirm_id,
                                target=current_title,
                                message=pending_message_text,
                                timeoutMs=5000,
                            )
                            log_down("task.confirm", _confirm.to_json())
                            await websocket.send_text(_confirm.to_json())
                            session.transition(State.AWAITING_CONFIRM)
                            confirm_count += 1
                            logger.info(
                                "[CONFIRM_SENT] target=%s current=%s msg=%r",
                                target_chat_name, current_title, pending_message_text,
                            )
                            break

                if action.op in ("tap", "input"):
                    if session.state == State.NAVIGATING:
                        session.transition(State.IN_CHAT)

                applied_steps.append({"op": action.op, "params": action.params})
                _act = action.to_json()
                log_down("action", _act)
                await websocket.send_text(_act)

            if terminate:
                break

    return app


def _find_send_button(nodes) -> "Node | None":
    """从当前屏节点树里找出「发送」按钮节点。
    多个候选时取最靠右下、面积最小的(按钮通常比输入框小)。
    """
    from app.chat_title_helpers import is_send_button  # 局部 import

    candidates = []
    for n in nodes:
        if is_send_button(n):
            if not n.bounds or len(n.bounds) != 4:
                continue
            l, t, r, b = n.bounds
            candidates.append((n, (r - l) * (b - t), l + r))
    if not candidates:
        return None
    # 优先选面积小的(精准按钮),并列时取靠右
    candidates.sort(key=lambda c: (c[1], -c[2]))
    return candidates[0][0]


def _bounds_center(bounds) -> tuple[int, int] | None:
    if not bounds or len(bounds) != 4:
        return None
    left, top, right, bottom = bounds
    return (left + right) // 2, (top + bottom) // 2


def _extract_last_input_text(applied_steps: list[dict]) -> str:
    """从 applied_steps 里取出最近一条 input 操作的文本,作为 Toast 预览用。"""
    for step in reversed(applied_steps):
        if step.get("op") == "input":
            text = step.get("params", {}).get("text", "")
            if text:
                return text
    return ""
