import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.gateway import create_app


def test_gateway_replay_heartbeat_returns_expected_message_type():
    app = create_app()
    client = TestClient(app)
    fixture = Path(__file__).parent / "fixtures" / "feishu_happy_path.json"
    uplink = fixture.read_text(encoding="utf-8")

    with client.websocket_connect("/ws/device-1") as ws:
        ws.send_text(uplink)
        msg = ws.receive_json()

    assert msg["type"] in {
        "task.start",
        "action",
        "task.done",
        "task.abort",
    }