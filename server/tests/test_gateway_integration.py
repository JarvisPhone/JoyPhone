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


def test_persist_sample_writes_json_file(tmp_path):
    from app.gateway import _persist_sample
    from app.protocol import SampleCapture

    sample = SampleCapture(
        label="minus_one",
        nodeTree=[],
        pkg="com.android.launcher",
        activity="Launcher",
        ts=1784168979000,
        device="OPPO",
    )
    path = _persist_sample(sample, base_dir=tmp_path)

    assert path.exists()
    assert path.parent == tmp_path
    assert path.name.startswith("minus_one-")
    assert path.suffix == ".json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["label"] == "minus_one"
    assert data["pkg"] == "com.android.launcher"
    assert data["device"] == "OPPO"


def test_gateway_sample_capture_persists_file(tmp_path, monkeypatch):
    import app.gateway as gw
    monkeypatch.setattr(gw, "_SAMPLES_DIR", tmp_path)
    app = create_app()
    client = TestClient(app)
    sample_msg = json.dumps({
        "type": "sample.capture",
        "label": "home_first",
        "nodeTree": [{"id": "n1", "text": "相机"}],
        "pkg": "com.android.launcher",
        "activity": "Launcher",
        "ts": 1720000000,
        "device": "OPPO",
    })
    with client.websocket_connect("/ws/device-1") as ws:
        ws.send_text(sample_msg)
        ws.send_text(json.dumps({"type": "heartbeat","deviceId": "device-1", "ts": 1}))
        ws.receive_json()  # 采样不回消息,后发心跳确认连接仍活着且能拿到回复

    files = list(tmp_path.glob("home_first-*.json"))
    assert len(files) == 1