"""VivoProvider 单测:HTTP RPC 载荷正确 + 错误路径覆盖。"""
from __future__ import annotations

import pytest

from app.agent.cert import StaticCertProvider
from app.agent.config import ProviderConfig
from app.mcp.daemon_client import DaemonError, ErrorDaemonClient, FakeDaemonClient
from app.mcp.providers.vivo import VivoProvider


def _vivo(
    *,
    daemon: FakeDaemonClient | ErrorDaemonClient | None = None,
    fingerprint: str = "fp-vivo-001",
) -> tuple[VivoProvider, FakeDaemonClient | ErrorDaemonClient]:
    daemon = daemon or FakeDaemonClient()
    cert = StaticCertProvider(fingerprint=fingerprint, signing_key=b"unit-test-key-32bytesxxxxxx")
    cfg = ProviderConfig(
        driver_type="vivo",
        device_id="dev-001",
        cert=cert,
        daemon_client=daemon,
    )
    return VivoProvider(cfg), daemon


def test_list_tools_returns_seven_system_tools():
    p, _ = _vivo()
    names = {t.name for t in p.list_tools()}
    assert names == {
        "force_stop",
        "install_silent",
        "lock_a11y",
        "unlock_a11y",
        "reboot_device",
        "kill_background",
        "query_running_packages",
    }
    for t in p.list_tools():
        assert t.provider == "vivo"


async def test_force_stop_calls_daemon_with_correct_payload():
    daemon = FakeDaemonClient(
        responses={
            ("vivo", "force_stop"): {"ok": True, "output": {"killed": "com.tencent.mm"}},
        },
    )
    p, _ = _vivo(daemon=daemon)
    result = await p.call_tool("force_stop", {"pkg": "com.tencent.mm"})
    assert result.ok is True
    assert result.output == {"killed": "com.tencent.mm"}
    assert daemon.calls == [
        {"driver": "vivo", "tool_name": "force_stop", "arguments": {"pkg": "com.tencent.mm"}},
    ]


async def test_force_stop_missing_pkg_returns_error_result():
    p, daemon = _vivo()
    result = await p.call_tool("force_stop", {})
    assert result.ok is False
    assert "pkg" in (result.error or "")
    # 没走到 daemon
    assert daemon.calls == []


async def test_force_stop_non_string_pkg_returns_error_result():
    p, daemon = _vivo()
    result = await p.call_tool("force_stop", {"pkg": 123})
    assert result.ok is False
    assert "pkg" in (result.error or "")
    assert daemon.calls == []


async def test_install_silent_calls_daemon():
    daemon = FakeDaemonClient(
        responses={("vivo", "install_silent"): {"ok": True, "output": {"installed": "/data/app/foo.apk"}}},
    )
    p, _ = _vivo(daemon=daemon)
    result = await p.call_tool("install_silent", {"apk_path": "/data/app/foo.apk"})
    assert result.ok is True
    assert daemon.calls[0]["tool_name"] == "install_silent"


async def test_lock_a11y_calls_daemon_no_args():
    daemon = FakeDaemonClient(
        responses={("vivo", "lock_a11y"): {"ok": True, "output": {"locked": True}}},
    )
    p, _ = _vivo(daemon=daemon)
    result = await p.call_tool("lock_a11y", {})
    assert result.ok is True
    assert daemon.calls == [{"driver": "vivo", "tool_name": "lock_a11y", "arguments": {}}]


async def test_kill_background_pkg_optional():
    """kill_background 的 pkg 是 optional,空 args 也要能走通。"""
    daemon = FakeDaemonClient(
        responses={("vivo", "kill_background"): {"ok": True, "output": {"killed_count": 3}}},
    )
    p, _ = _vivo(daemon=daemon)
    result = await p.call_tool("kill_background", {})
    assert result.ok is True
    assert result.output == {"killed_count": 3}


async def test_unknown_tool_local_validation():
    p, daemon = _vivo()
    result = await p.call_tool("ghost_tool", {})
    assert result.ok is False
    assert "unknown tool" in (result.error or "")
    assert daemon.calls == []


async def test_daemon_error_returns_error_result():
    daemon = ErrorDaemonClient(message="vivo cert missing", status_code=401)
    p, _ = _vivo(daemon=daemon)
    result = await p.call_tool("force_stop", {"pkg": "com.x"})
    assert result.ok is False
    assert "daemon error" in (result.error or "")
    assert daemon.calls == [{"driver": "vivo", "tool_name": "force_stop", "arguments": {"pkg": "com.x"}}]


async def test_daemon_ok_false_returns_error_result_with_output():
    """daemon 本身 ok=False(SDK 失败)透传到 ToolResult.error,但 output 保留。"""
    daemon = FakeDaemonClient(
        responses={
            ("vivo", "force_stop"): {
                "ok": False,
                "error": "permission denied",
                "output": {"detail": "need admin role"},
            },
        },
    )
    p, _ = _vivo(daemon=daemon)
    result = await p.call_tool("force_stop", {"pkg": "com.x"})
    assert result.ok is False
    assert result.error == "permission denied"
    assert result.output == {"detail": "need admin role"}


async def test_daemon_invalid_response_shape_returns_error_result():
    """daemon 响应里缺 ok 字段,Provider 把它当错。"""
    daemon = FakeDaemonClient(
        responses={("vivo", "force_stop"): {"foo": "bar"}},
    )
    p, _ = _vivo(daemon=daemon)
    result = await p.call_tool("force_stop", {"pkg": "com.x"})
    assert result.ok is False
    assert "invalid response" in (result.error or "")


def test_provider_config_rejects_empty_device_id():
    from app.mcp.daemon_client import FakeDaemonClient

    cert = StaticCertProvider(fingerprint="fp", signing_key=b"k")
    with pytest.raises(ValueError, match="device_id"):
        ProviderConfig(driver_type="vivo", device_id="", cert=cert, daemon_client=FakeDaemonClient())


def test_provider_config_rejects_empty_driver_type():
    from app.mcp.daemon_client import FakeDaemonClient

    cert = StaticCertProvider(fingerprint="fp", signing_key=b"k")
    with pytest.raises(ValueError, match="driver_type"):
        ProviderConfig(driver_type="", device_id="dev", cert=cert, daemon_client=FakeDaemonClient())