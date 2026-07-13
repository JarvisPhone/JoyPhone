import json

from fastapi.testclient import TestClient

from app.gateway import _load_fixture_steps, create_app


def test_gateway_replay_heartbeat_returns_expected_message_type():
    app = create_app()
    client = TestClient(app)
    # 心跳文本内联构造，与回放夹具（动作数组）语义解耦
    heartbeat = json.dumps(
        {"type": "heartbeat", "deviceId": "device-1", "ts": 1720000000}
    )

    with client.websocket_connect("/ws/device-1") as ws:
        ws.send_text(heartbeat)
        msg = ws.receive_json()

    assert msg["type"] in {
        "task.start",
        "action",
        "task.done",
        "task.abort",
    }


def test_load_fixture_steps_returns_action_sequence():
    steps = _load_fixture_steps()

    assert isinstance(steps, list)
    assert len(steps) == 4
    assert steps[0]["op"] == "tap"
    assert steps[-1]["op"] == "tap"
    assert steps[-1]["params"]["match_text"] == "发送"