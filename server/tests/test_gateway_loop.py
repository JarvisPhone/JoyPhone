import json

from fastapi.testclient import TestClient

from app.gateway import create_app


def _perception(nodes, pkg="", activity="", ts=1):
    return json.dumps(
        {
            "type": "perception",
            "nodeTree": nodes,
            "pkg": pkg,
            "activity": activity,
            "ts": ts,
        }
    )


def _result(action_id, ok=True):
    return json.dumps(
        {"type": "action.result", "actionId": action_id, "ok": ok, "ts": 1}
    )


def _task_request(goal="帮我完成一件事"):
    return json.dumps({"type": "task.request", "goal": goal})


def test_gateway_starts_task_on_request(monkeypatch, tmp_path):
    monkeypatch.setenv("SKILL_CACHE_PATH", str(tmp_path / "cache.json"))
    monkeypatch.setenv("PHONEAGENT_FAKE_LLM", json.dumps(["done"]))

    app = create_app()
    client = TestClient(app)
    with client.websocket_connect("/ws/device-1") as ws:
        ws.send_text(_task_request("帮我完成一件事"))
        first = ws.receive_json()

    assert first["type"] == "task.start"
    assert first["taskId"]
    assert first["goal"] == "帮我完成一件事"


def test_gateway_stays_idle_until_task_request(monkeypatch, tmp_path):
    monkeypatch.setenv("SKILL_CACHE_PATH", str(tmp_path / "cache.json"))
    monkeypatch.setenv("PHONEAGENT_FAKE_LLM", json.dumps(["done"]))

    app = create_app()
    client = TestClient(app)
    with client.websocket_connect("/ws/device-1") as ws:
        # connect 后服务器不自动下发任何消息；只有收到 task.request 后
        # 第一条收到的消息才是 task.start。
        ws.send_text(_task_request("处理一个事项"))
        first = ws.receive_json()

    assert first["type"] == "task.start"
    assert first["goal"] == "处理一个事项"


def test_gateway_task_request_drives_goal(monkeypatch, tmp_path):
    monkeypatch.setenv("SKILL_CACHE_PATH", str(tmp_path / "cache.json"))
    monkeypatch.setenv("PHONEAGENT_FAKE_LLM", json.dumps(["done"]))

    app = create_app()
    client = TestClient(app)
    with client.websocket_connect("/ws/device-1") as ws:
        ws.send_text(_task_request("帮我完成一件事"))
        start = ws.receive_json()

    assert start["type"] == "task.start"
    assert start["goal"] == "帮我完成一件事"


def test_gateway_perception_yields_action_then_done(monkeypatch, tmp_path):
    monkeypatch.setenv("SKILL_CACHE_PATH", str(tmp_path / "cache.json"))
    monkeypatch.setenv(
        "PHONEAGENT_FAKE_LLM",
        json.dumps(
            [
                "tap 0",
                "done",
            ]
        ),
    )

    app = create_app()
    client = TestClient(app)
    nodes = [{"id": "n1", "text": "搜索", "clickable": True}]

    with client.websocket_connect("/ws/device-1") as ws:
        ws.send_text(_task_request())
        ws.receive_json()  # task.start
        ws.send_text(_perception(nodes, pkg="com.ss.android.lark"))
        action = ws.receive_json()
        assert action["type"] == "action"
        assert action["op"] == "tap"

        ws.send_text(_result(action["actionId"], ok=True))
        ws.send_text(_perception(nodes, pkg="com.ss.android.lark"))
        done = ws.receive_json()
        assert done["type"] == "task.done"


def test_gateway_budget_exhausted_aborts(monkeypatch, tmp_path):
    monkeypatch.setenv("SKILL_CACHE_PATH", str(tmp_path / "cache.json"))
    monkeypatch.setenv("PHONEAGENT_FAKE_LLM", json.dumps(["wait 500"]))
    monkeypatch.setenv("PHONEAGENT_MAX_STEPS", "2")

    app = create_app()
    client = TestClient(app)
    nodes = [{"id": "n1", "text": "x", "clickable": True}]

    with client.websocket_connect("/ws/device-1") as ws:
        ws.send_text(_task_request())
        ws.receive_json()  # task.start
        seen_abort = False
        for _ in range(5):
            ws.send_text(_perception(nodes))
            msg = ws.receive_json()
            if msg["type"] == "task.abort":
                seen_abort = True
                break
        assert seen_abort


def test_gateway_heartbeat_still_returns_action(monkeypatch, tmp_path):
    monkeypatch.setenv("SKILL_CACHE_PATH", str(tmp_path / "cache.json"))
    monkeypatch.setenv("PHONEAGENT_FAKE_LLM", json.dumps(["read_screen"]))

    app = create_app()
    client = TestClient(app)
    heartbeat = json.dumps({"type": "heartbeat", "deviceId": "device-1", "ts": 1})
    with client.websocket_connect("/ws/device-1") as ws:
        ws.send_text(_task_request())
        ws.receive_json()  # task.start
        ws.send_text(heartbeat)
        msg = ws.receive_json()
        assert msg["type"] in {"action", "task.done", "task.abort"}