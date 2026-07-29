"""DaemonClient HTTP RPC 客户端契约:Fake + Error + Http(URL 构造)。"""
from __future__ import annotations

import pytest

from app.mcp.daemon_client import (
    DaemonError,
    ErrorDaemonClient,
    FakeDaemonClient,
    HttpDaemonClient,
)


async def test_fake_daemon_records_all_calls():
    fake = FakeDaemonClient()
    await fake.call("vivo", "force_stop", {"pkg": "com.x"})
    await fake.call("a11y", "tap", {"match_text": "发送"})
    assert fake.calls == [
        {"driver": "vivo", "tool_name": "force_stop", "arguments": {"pkg": "com.x"}},
        {"driver": "a11y", "tool_name": "tap", "arguments": {"match_text": "发送"}},
    ]


async def test_fake_daemon_returns_preset_response():
    fake = FakeDaemonClient(
        responses={
            ("vivo", "force_stop"): {"ok": True, "output": {"killed": True}},
        },
    )
    body = await fake.call("vivo", "force_stop", {"pkg": "com.x"})
    assert body == {"ok": True, "output": {"killed": True}}


async def test_fake_daemon_falls_back_to_default():
    fake = FakeDaemonClient(default={"ok": True, "output": {"mocked": True}})
    body = await fake.call("vivo", "anything", {})
    assert body == {"ok": True, "output": {"mocked": True}}


async def test_error_daemon_raises_daemon_error():
    err = ErrorDaemonClient(message="http 500", status_code=500)
    with pytest.raises(DaemonError) as exc:
        await err.call("vivo", "force_stop", {"pkg": "x"})
    assert exc.value.message == "http 500"
    assert exc.value.status_code == 500
    assert err.calls == [{"driver": "vivo", "tool_name": "force_stop", "arguments": {"pkg": "x"}}]


def test_http_daemon_client_rejects_empty_base_url():
    with pytest.raises(ValueError, match="base_url"):
        HttpDaemonClient(base_url="")


def test_http_daemon_client_strips_trailing_slash():
    """base_url 末尾 / 必须剥离,避免拼成 //mcp/vivo/force_stop。"""
    c = HttpDaemonClient(base_url="http://127.0.0.1:9999/")
    assert c._base_url == "http://127.0.0.1:9999"  # noqa: SLF001 — 单测访问内部字段


class _StubAsyncClient:
    """测试用:覆写 _open_client() 返回的 httpx.AsyncClient。

    通过 capture post 请求 + 返回预设响应,验证 URL/方法/载荷正确,无 pytest-httpx 依赖。
    """

    def __init__(self, response) -> None:
        self._response = response
        self.requests: list = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, json=None):
        # 用 httpx.Request 捕获;但避免从 httpx 实际发送,只 stub
        self.requests.append({"url": url, "json": json})
        return self._response


async def test_http_daemon_client_sends_post_to_correct_url():
    """验证 URL 拼接 + payload + 响应 JSON 解析 + ok 字段。"""
    import httpx

    resp = httpx.Response(200, json={"ok": True, "output": {"killed": "com.x"}})
    stub = _StubAsyncClient(resp)

    c = HttpDaemonClient(base_url="http://daemon.local:8080")
    c._open_client = lambda: stub  # type: ignore[assignment]

    body = await c.call("vivo", "force_stop", {"pkg": "com.x"})
    assert body == {"ok": True, "output": {"killed": "com.x"}}
    assert stub.requests[0]["url"] == "http://daemon.local:8080/mcp/vivo/force_stop"
    assert stub.requests[0]["json"] == {"arguments": {"pkg": "com.x"}}


async def test_http_daemon_client_raises_on_non_2xx():
    import httpx

    resp = httpx.Response(500, text="internal")
    stub = _StubAsyncClient(resp)

    c = HttpDaemonClient(base_url="http://daemon.local:8080")
    c._open_client = lambda: stub  # type: ignore[assignment]

    with pytest.raises(DaemonError) as exc:
        await c.call("vivo", "force_stop", {"pkg": "x"})
    assert exc.value.status_code == 500


async def test_http_daemon_client_raises_on_missing_ok_field():
    import httpx

    resp = httpx.Response(200, json={"output": "no ok field"})
    stub = _StubAsyncClient(resp)

    c = HttpDaemonClient(base_url="http://daemon.local:8080")
    c._open_client = lambda: stub  # type: ignore[assignment]

    with pytest.raises(DaemonError, match="missing 'ok'"):
        await c.call("vivo", "force_stop", {"pkg": "x"})