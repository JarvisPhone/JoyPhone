import json
from pathlib import Path

from fastapi import FastAPI, WebSocket
from starlette.websockets import WebSocketDisconnect

from app.protocol import Action, TaskAbort, TaskDone, TaskStart, parse_uplink

_FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "feishu_happy_path.json"


def _load_fixture_steps() -> list[dict]:
    if not _FIXTURE.exists():
        return []
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def create_app() -> FastAPI:
    app = FastAPI()

    @app.websocket("/ws/{device_id}")
    async def ws_gateway(websocket: WebSocket, device_id: str) -> None:
        await websocket.accept()
        task_id = "task-1"
        await websocket.send_text(
            TaskStart(taskId=task_id, goal="确认还款时间", target=device_id).to_json()
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
                    TaskAbort(taskId=task_id, reason="invalid_uplink").to_json()
                )
                break

            if uplink.type == "heartbeat":
                await websocket.send_text(
                    Action(actionId="action-1", op="read_screen", params={}).to_json()
                )
                continue

            await websocket.send_text(
                TaskDone(taskId=task_id, result="ok", summary="done").to_json()
            )
            break

    return app