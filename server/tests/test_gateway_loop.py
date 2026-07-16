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


def test_gateway_idle_perception_yields_no_action(monkeypatch, tmp_path):
    """未收到 task.request 时(session 不活跃),perception 帧应被忽略,
    不产生任何 action 下发(修复空转轮询)。

    验证手法:发 perception 后紧接发 heartbeat。若 perception 被正确忽略,
    第一条收到的消息应是 heartbeat 的回复(read_screen),而不是 perception 的决策。
    """
    monkeypatch.setenv("SKILL_CACHE_PATH", str(tmp_path / "cache.json"))
    monkeypatch.setenv("PHONEAGENT_FAKE_LLM", json.dumps(["tap 0", "done"]))

    app = create_app()
    client = TestClient(app)
    nodes = [{"id": "n1", "text": "搜索", "clickable": True}]
    heartbeat = json.dumps({"type": "heartbeat", "deviceId": "device-1", "ts": 1})

    with client.websocket_connect("/ws/device-1") as ws:
        # 未发 task.request,直接推 perception
        ws.send_text(_perception(nodes, pkg="com.android.systemui"))
        ws.send_text(heartbeat)
        first = ws.receive_json()

    # perception 被忽略,第一条回复应是 heartbeat 的 read_screen
    assert first["type"] == "action"
    assert first["op"] == "read_screen"


def test_gateway_input_forwarded_when_in_target_chat(monkeypatch, tmp_path):
    """在目标群内,LLM 决策的 input 应正常下发(文字先填进输入框),
    而不是被拦截成 task.confirm(修复:拦截点移到 tap 发送前)。
    """
    monkeypatch.setenv("SKILL_CACHE_PATH", str(tmp_path / "cache.json"))
    monkeypatch.setenv("PHONEAGENT_FAKE_LLM", json.dumps(["input 1 你好"]))

    app = create_app()
    client = TestClient(app)
    # 目标群 + 输入框 + 发送按钮 都在当前屏
    nodes = [
        {"id": "t1", "text": "测试群", "viewIdResourceName": "com.ss.android.lark:id/toolbar_title"},
        {"id": "e1", "text": "", "editable": True, "bounds": [0, 800, 900, 900]},
        {"id": "s1", "text": "发送", "clickable": True, "viewIdResourceName": "com.ss.android.lark:id/btn_send", "bounds": [900, 800, 1000, 900]},
    ]

    with client.websocket_connect("/ws/device-1") as ws:
        ws.send_text(_task_request("打开飞书,给群「测试群」发一条消息"))
        ws.receive_json()  # task.start
        ws.send_text(_perception(nodes, pkg="com.ss.android.lark"))
        msg = ws.receive_json()

    # input 应被正常下发,而不是拦截成 task.confirm
    assert msg["type"] == "action"
    assert msg["op"] == "input"


def test_gateway_send_tap_intercepted_in_target_chat(monkeypatch, tmp_path):
    """在目标群内,LLM 决策 tap 发送按钮时应被拦截,
    发 task.confirm 停住(修复:拦截点在 tap 发送前)。
    """
    monkeypatch.setenv("SKILL_CACHE_PATH", str(tmp_path / "cache.json"))
    # 第 0 行是 title,第 1 行是输入框,第 2 行是发送按钮(tap 2)
    monkeypatch.setenv("PHONEAGENT_FAKE_LLM", json.dumps(["tap 2"]))

    app = create_app()
    client = TestClient(app)
    nodes = [
        {"id": "t1", "text": "测试群", "viewIdResourceName": "com.ss.android.lark:id/toolbar_title"},
        {"id": "e1", "text": "你好", "editable": True, "bounds": [0, 800, 900, 900]},
        {"id": "s1", "text": "发送", "clickable": True, "viewIdResourceName": "com.ss.android.lark:id/btn_send", "bounds": [900, 800, 1000, 900]},
    ]

    with client.websocket_connect("/ws/device-1") as ws:
        ws.send_text(_task_request("打开飞书,给群「测试群」发一条消息"))
        ws.receive_json()  # task.start
        ws.send_text(_perception(nodes, pkg="com.ss.android.lark"))
        msg = ws.receive_json()

    assert msg["type"] == "task.confirm"
    assert msg["target"] == "测试群"


def test_input_message_in_wrong_chat_is_intercepted(monkeypatch, tmp_path, caplog):
    """进错群时,LLM 决策的「往聊天正文输入正文」应被拦截,不下发 input,
    改下发一个 op=back 回上一级,并记 [INPUT_GUARD] 日志。
    """
    import logging

    monkeypatch.setenv("SKILL_CACHE_PATH", str(tmp_path / "cache.json"))
    # 第 0 行 title(错群),第 1 行聊天正文输入框(input 1)
    monkeypatch.setenv("PHONEAGENT_FAKE_LLM", json.dumps(["input 1 你好呀"]))

    app = create_app()
    client = TestClient(app)
    nodes = [
        {
            "id": "t1",
            "text": "奇瑞Robotaxi项目",
            "viewIdResourceName": "com.ss.android.lark:id/toolbar_title",
        },
        {
            "id": "e1",
            "text": "",
            "desc": "发消息",
            "editable": True,
            "bounds": [0, 800, 900, 900],
        },
    ]

    with caplog.at_level(logging.WARNING, logger="phoneagent.gateway"):
        with client.websocket_connect("/ws/device-1") as ws:
            ws.send_text(_task_request("打开飞书,给群「Android AI 开发组」发一条消息"))
            ws.receive_json()  # task.start
            ws.send_text(_perception(nodes, pkg="com.ss.android.lark"))
            msg = ws.receive_json()

    # input 未被下发,取而代之的是一个 back
    assert msg["type"] == "action"
    assert msg["op"] == "back"
    assert any("[INPUT_GUARD]" in rec.getMessage() for rec in caplog.records)


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