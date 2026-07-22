# server/tests/test_gateway_integration.py
"""端到端回放:create_app + TestClient websocket 驱动 fixtures/feishu_happy_path.json。

fixture 是「send/expect 帧序」格式:send 帧里 {goal}/{taskId}/{confirmId}/{actionId}
为动态占位符,expect 帧逐字段断言下行消息;末帧后再发一次 heartbeat 验证
task.done 之后连接未异常断开。goal 为「给研发部群发飞书消息」,同时回归
extract_target 剥「群」字(T11 遗留 concern):task.confirm.target 必须是不带
「群」的「研发部」。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app

FIXTURE = Path(__file__).parent / "fixtures" / "feishu_happy_path.json"


def _substitute(value, ctx: dict):
    if isinstance(value, str):
        for key, val in ctx.items():
            value = value.replace("{%s}" % key, str(val))
        return value
    if isinstance(value, dict):
        return {k: _substitute(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute(v, ctx) for v in value]
    return value


def _capture(ctx: dict, received: dict) -> None:
    for key in ("taskId", "confirmId", "actionId"):
        if received.get(key):
            ctx[key] = received[key]


def _check_expect(expected: dict, received: dict, ctx: dict, idx: int) -> None:
    for key, val in expected.items():
        if key == "ts_positive":
            assert received.get("ts", 0) > 0, "step %d: ts 未填当前时间戳" % idx
            continue
        if key == "text":
            got = received.get("params", {}).get("text")
            assert got == val, "step %d: params.text=%r != %r" % (idx, got, val)
            continue
        want = _substitute(val, ctx)
        assert received.get(key) == want, (
            "step %d: %s=%r != %r (full=%r)" % (idx, key, received.get(key), want, received)
        )


@pytest.fixture
def replay_env(tmp_path, monkeypatch):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    monkeypatch.setenv(
        "PHONEAGENT_FAKE_LLM", json.dumps(fixture["llm_responses"], ensure_ascii=False)
    )
    monkeypatch.setenv("SKILL_CACHE_PATH", str(tmp_path / "skill_cache.json"))
    monkeypatch.setenv("PHONEAGENT_LOG_DIR", str(tmp_path))
    return fixture


def test_feishu_happy_path_replay(replay_env):
    ctx = {"goal": replay_env["goal"]}
    client = TestClient(create_app())
    with client.websocket_connect("/ws/dev-1?v=2") as ws:
        for idx, step in enumerate(replay_env["script"]):
            if "send" in step:
                payload = _substitute(step["send"], ctx)
                ws.send_text(json.dumps(payload, ensure_ascii=False))
            if "expect" in step:
                received = json.loads(ws.receive_text())
                _capture(ctx, received)
                _check_expect(step["expect"], received, ctx, idx)


def test_invalid_uplink_aborts_and_closes(replay_env):
    client = TestClient(create_app())
    with client.websocket_connect("/ws/dev-1?v=2") as ws:
        ws.send_text("this is not json")
        received = json.loads(ws.receive_text())
        assert received["type"] == "task.abort"
        assert received["reason"] == "invalid_uplink"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_text()


# ---- 协议版本握手(F1)----


def test_handshake_rejects_missing_or_mismatched_version(replay_env):
    client = TestClient(create_app())
    for url in ("/ws/dev-1", "/ws/dev-1?v=1", "/ws/dev-1?v=abc"):
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(url):
                pass
        assert exc_info.value.code == 4402, url


def test_handshake_accepts_current_version(replay_env):
    client = TestClient(create_app())
    with client.websocket_connect("/ws/dev-1?v=2") as ws:
        ws.send_text(json.dumps({"type": "heartbeat", "deviceId": "dev-1"}))
        received = json.loads(ws.receive_text())
        assert received["type"] == "heartbeat.ack"


def test_task_state_survives_reconnect(replay_env):
    # 真机事故回归:confirm 等待中 WS 断连重连,confirm_response 落到新连接
    # 时必须仍能找到任务现场(TaskStore 按 device_id 共享,不随连接生死)。
    fixture = replay_env
    goal = fixture["goal"]
    client = TestClient(create_app())
    script = fixture["script"]

    # 第一段:跑到 task.confirm 出现为止,然后断连
    ctx = {"goal": goal}
    confirm_msg = None
    with client.websocket_connect("/ws/dev-re?v=2") as ws:
        for idx, step in enumerate(script):
            if "send" in step:
                ws.send_text(json.dumps(_substitute(step["send"], ctx), ensure_ascii=False))
            if "expect" in step:
                received = json.loads(ws.receive_text())
                _capture(ctx, received)
                if received.get("type") == "task.confirm":
                    confirm_msg = received
                    break
    assert confirm_msg is not None, "脚本未跑到 task.confirm"

    # 第二段:同一 device_id 重连,confirm_response 在新连接上送达
    with client.websocket_connect("/ws/dev-re?v=2") as ws:
        ws.send_text(json.dumps({
            "type": "task.confirm_response",
            "taskId": ctx["taskId"],
            "confirmId": confirm_msg["confirmId"],
            "approved": True,
        }))
        received = json.loads(ws.receive_text())
        # 断连前被拦截的发送 tap 必须在新连接上补发
        assert received["type"] == "action", received
        assert received["op"] == "tap"
