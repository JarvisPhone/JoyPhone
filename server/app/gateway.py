import json
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, WebSocket
from starlette.websockets import WebSocketDisconnect

from app.decision import DecisionEngine
from app.llm import FakeLLM, build_llm
from app.protocol import (
    Action,
    TaskAbort,
    TaskDone,
    TaskStart,
    parse_uplink,
)
from app.skill_cache import SkillCache
from app.skills import SkillLibrary

_FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "feishu_happy_path.json"

_DEFAULT_GOAL = "在飞书里给指定联系人发送消息"


def _load_fixture_steps() -> list[dict]:
    """保留：供 test_gateway_integration 使用。"""
    if not _FIXTURE.exists():
        return []
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _build_engine() -> DecisionEngine:
    """构造决策引擎；测试可用 PHONEAGENT_FAKE_LLM 注入 FakeLLM 响应序列。"""
    fake = os.getenv("PHONEAGENT_FAKE_LLM")
    llm = FakeLLM(json.loads(fake)) if fake else build_llm()
    cache = SkillCache(Path(os.getenv("SKILL_CACHE_PATH", "data/skill_cache.json")))
    return DecisionEngine(llm=llm, skills=SkillLibrary(), cache=cache)


def create_app() -> FastAPI:
    app = FastAPI()
    max_steps = int(os.getenv("PHONEAGENT_MAX_STEPS", "40"))

    @app.websocket("/ws/{device_id}")
    async def ws_gateway(websocket: WebSocket, device_id: str) -> None:
        await websocket.accept()
        from app.session import Session

        engine = _build_engine()
        session = Session(
            task_id=f"task-{uuid.uuid4().hex[:8]}",
            goal=_DEFAULT_GOAL,
            target=device_id,
            max_steps=max_steps,
        )
        cursor = 0
        history: list[dict] = []
        applied_steps: list[dict] = []
        last_pkg = ""

        await websocket.send_text(
            TaskStart(taskId=session.task_id, goal=session.goal, target=device_id).to_json()
        )

        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                break

            try:
                uplink = parse_uplink(raw)
            except ValueError:
                await websocket.send_text(
                    TaskAbort(taskId=session.task_id, reason="invalid_uplink").to_json()
                )
                break

            if uplink.type == "action.result":
                history.append({"actionId": uplink.actionId, "ok": uplink.ok})
                if uplink.ok:
                    cursor += 1
                continue

            if uplink.type == "heartbeat":
                await websocket.send_text(
                    Action(actionId=str(uuid.uuid4()), op="read_screen", params={}).to_json()
                )
                continue

            if uplink.type != "perception":
                continue

            if session.budget_exhausted():
                await websocket.send_text(
                    TaskAbort(taskId=session.task_id, reason="budget_exhausted").to_json()
                )
                break

            last_pkg = uplink.pkg or last_pkg
            action = engine.decide(
                goal=session.goal,
                perception=uplink,
                skill_name=None,
                cursor=cursor,
                history=history,
            )
            session.record_step()

            if action.op == "done":
                if applied_steps:
                    engine._cache.learn(session.goal, last_pkg, applied_steps)
                await websocket.send_text(
                    TaskDone(taskId=session.task_id, result="ok", summary="task completed").to_json()
                )
                break

            if action.op == "abort":
                await websocket.send_text(
                    TaskAbort(taskId=session.task_id, reason="llm_abort").to_json()
                )
                break

            applied_steps.append({"op": action.op, "params": action.params})
            await websocket.send_text(action.to_json())

    return app