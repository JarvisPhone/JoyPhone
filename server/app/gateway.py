import json
import logging
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, WebSocket
from starlette.websockets import WebSocketDisconnect

from app.comm_log import log_up, log_down
from app.decision import DecisionEngine
from app.llm import FakeLLM, build_llm
from app.metrics import get_metrics_collector
from app.protocol import (
    Action,
    TaskAbort,
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

            if uplink.type == "heartbeat":
                _hb = Action(actionId=str(uuid.uuid4()), op="read_screen", params={}).to_json()
                log_down("action", _hb)
                await websocket.send_text(_hb)
                continue

            if uplink.type == "task.request":
                session.goal = uplink.goal
                session.state = State.NAVIGATING
                logger.info("task.request goal=%s", uplink.goal)
                _ts_msg = TaskStart(taskId=session.task_id, goal=session.goal, target=device_id).to_json()
                log_down("task.start", _ts_msg)
                await websocket.send_text(_ts_msg)
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

            skill_name = engine._select_skill(session.goal, uplink.pkg) if skill_name is None else None

            actions = engine.decide(
                goal=session.goal,
                perception=uplink,
                skill_name=skill_name,
                cursor=cursor,
                history=history,
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
