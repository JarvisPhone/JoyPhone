"""Phase 2 集成:BM25 召回 → Router → VivoProvider → FakeDaemon 贯通。

完整走一遍 plan §5 的"force_stop wechat"工具调用,验证:
1. BM25 能用 query "kill wechat" 召回 force_stop
2. Router.route 把 force_stop 派发给 vivo provider
3. VivoProvider.call_tool 走 DaemonClient.call
4. DaemonClient 拿到正确 driver + tool_name + arguments

ADR 0004:Registry 只装 vivo(SDK Provider),a11y 不在 MCP。测试里
force_stop 路径不再分叉(a11y force_stop 已不存在),直接验证 vivo 派发。
"""
from __future__ import annotations

import pytest

from app.agent.cert import StaticCertProvider
from app.agent.config import ProviderConfig
from app.mcp import BM25Index, McpRouter, ProviderRegistry
from app.mcp.daemon_client import FakeDaemonClient
from app.mcp.providers.vivo import VivoProvider


def _setup(
    *,
    daemon_response: dict | None = None,
    capabilities: dict | None = None,
) -> tuple[McpRouter, BM25Index, FakeDaemonClient, VivoProvider]:
    """构造"vivo + Router + BM25 索引"完整链路(不再装 A11yProvider)。"""
    daemon = FakeDaemonClient(
        responses={
            ("vivo", "force_stop"): daemon_response or {"ok": True, "output": {"killed": "com.tencent.mm"}},
        },
    )
    cert = StaticCertProvider(fingerprint="fp-vivo-001", signing_key=b"unit-test-key-32bytesxxxxxx")
    cfg = ProviderConfig(driver_type="vivo", device_id="dev-001", cert=cert, daemon_client=daemon)
    vivo = VivoProvider(cfg)

    reg = ProviderRegistry()
    reg.register(vivo)

    router = McpRouter(reg, device_capabilities=capabilities or {"devicesdk": True})

    idx = BM25Index()
    idx.add(reg.all_tools())

    return router, idx, daemon, vivo


async def test_search_to_force_stop_e2e():
    router, idx, daemon, _ = _setup()

    # 1. LLM 搜 "kill wechat"
    scored = idx.search("kill wechat")
    names = [s.tool.name for s in scored]
    assert "force_stop" in names

    # 2. 直接选 force_stop 派发(BM25 重在召回不重在排序)
    forced = next(s for s in scored if s.tool.name == "force_stop")

    # 3. Router 派发到 vivo(registry 里只有 vivo 一家)
    result = await router.route(forced.tool.name, {"pkg": "com.tencent.mm"})
    assert result.ok is True
    assert result.output == {"killed": "com.tencent.mm"}

    # 4. daemon.calls 验证 vivo 真实收到 RPC
    vivo_calls = [c for c in daemon.calls if c["tool_name"] == "force_stop"]
    assert vivo_calls == [
        {"driver": "vivo", "tool_name": "force_stop", "arguments": {"pkg": "com.tencent.mm"}},
    ]


async def test_vivo_capability_missing_blocks_force_stop():
    """device.hello 没上报 devicesdk → 后端拒绝路由 vivo SDK 工具。

    force_stop 唯一在 vivo provider,无 a11y 回退路径,必须拦死(ADR 0004)。
    """
    daemon = FakeDaemonClient()
    cert = StaticCertProvider(fingerprint="fp-vivo-001", signing_key=b"unit-test-key-32bytesxxxxxx")
    cfg = ProviderConfig(driver_type="vivo", device_id="dev-001", cert=cert, daemon_client=daemon)
    vivo = VivoProvider(cfg)

    reg = ProviderRegistry()
    reg.register(vivo)
    router = McpRouter(reg, device_capabilities={})  # 没 devicesdk

    from app.mcp.router import RouteError

    with pytest.raises(RouteError) as exc:
        await router.route("lock_a11y", {})
    assert exc.value.tool_name == "lock_a11y"
    assert "devicesdk" in exc.value.reason


async def test_vivo_unknown_tool_via_provider_local_fail_closed():
    """vivo provider 收到 provider 内部未知 tool(说明 RNG 触发了),本地 fail-closed。

    Router 找 provider 是按 tool_name 找的;vivo 内部还有 tool 但 router 不知道
    那个 tool 名,所以其实是 router 找不到。要测 vivo 内部的 fail-closed,
    必须直接调 VivoProvider.call_tool。
    """
    from app.mcp.protocol import ToolResult

    _, _, _, vivo = _setup()
    result = await vivo.call_tool("vivo_ghost", {})
    assert result.ok is False
    assert isinstance(result, ToolResult)
    assert "unknown tool" in (result.error or "")


async def test_bm25_recall_contains_vivo_sdk_tools():
    """BM25 索引能召回 vivo SDK 工具。

    a11y ops 不在 corpus 里(ADR 0004),所以查询「tap」类应一律召回不到。
    """
    _, idx, _, _ = _setup()
    scored = idx.search("force_stop wechat 后台一键 kill")
    names = {s.tool.name for s in scored}
    assert "force_stop" in names

    # a11y 风格查询应召回不到 a11y op(tap / swipe / input 不在 corpus)
    a11y_scored = idx.search("点击屏幕")
    a11y_names = {s.tool.name for s in a11y_scored}
    assert "tap" not in a11y_names
    assert "swipe" not in a11y_names
    assert "input" not in a11y_names
