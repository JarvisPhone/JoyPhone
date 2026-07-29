"""Router 路由正确性:Provider 查找 + capability 裁剪 + 异步调用落地。

Phase 2 改造:BaseProvider.call_tool 改成 async,Router.route 改成 async,
所有 Route 都 await。同步 fake 用 `async def` 仍是无副作用的。
"""
from __future__ import annotations

import pytest

from app.mcp.protocol import ToolArgument, ToolDefinition, ToolResult
from app.mcp.providers.base import BaseProvider
from app.mcp.providers.a11y import A11yProvider
from app.mcp.registry import ProviderRegistry
from app.mcp.router import McpRouter, RouteError


class _FakeProvider(BaseProvider):
    """带 capability requires 的假 provider,用于测裁剪。"""

    name = "fake"

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def list_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="fancy_op",
                description="需要 screenshot 能力的操作",
                arguments=[ToolArgument(name="x", type="string")],
                provider=self.name,
                requires={"screenshot": True},
            ),
            ToolDefinition(
                name="plain_op",
                description="不需要任何能力",
                arguments=[],
                provider=self.name,
            ),
        ]

    async def call_tool(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        return ToolResult(ok=True, output={"echo": arguments})


def _registry_with_a11y() -> tuple[ProviderRegistry, A11yProvider]:
    reg = ProviderRegistry()
    a11y = A11yProvider()
    reg.register(a11y)
    return reg, a11y


async def test_route_unknown_tool_raises_route_error():
    reg, _ = _registry_with_a11y()
    router = McpRouter(reg)
    with pytest.raises(RouteError) as exc:
        await router.route("no_such_tool", {})
    assert exc.value.tool_name == "no_such_tool"
    assert "no provider" in exc.value.reason


async def test_route_known_tool_calls_provider_and_returns_result():
    reg, a11y = _registry_with_a11y()
    router = McpRouter(reg)
    result = await router.route("force_stop", {"pkg": "com.tencent.mm"})
    assert result.ok is True
    assert result.output == {"mocked": True, "name": "force_stop"}
    assert a11y.calls == [{"name": "force_stop", "arguments": {"pkg": "com.tencent.mm"}}]


async def test_route_a11y_arg_validation_returns_error_result():
    reg, _ = _registry_with_a11y()
    router = McpRouter(reg)
    result = await router.route("force_stop", {})  # 缺 pkg
    assert result.ok is False
    assert "pkg" in (result.error or "")


async def test_route_capability_required_blocks_when_caps_unknown():
    reg = ProviderRegistry()
    reg.register(_FakeProvider())
    # device.hello 还没来,_caps=None,requires 必现
    router = McpRouter(reg, device_capabilities=None)
    with pytest.raises(RouteError) as exc:
        await router.route("fancy_op", {"x": "y"})
    assert exc.value.tool_name == "fancy_op"
    assert "device.hello not yet received" in exc.value.reason


async def test_route_capability_required_blocks_when_mismatch():
    reg = ProviderRegistry()
    reg.register(_FakeProvider())
    router = McpRouter(reg, device_capabilities={"screenshot": False})
    with pytest.raises(RouteError) as exc:
        await router.route("fancy_op", {"x": "y"})
    assert "screenshot" in exc.value.reason


async def test_route_capability_required_passes_when_match():
    reg = ProviderRegistry()
    fake = _FakeProvider()
    reg.register(fake)
    router = McpRouter(reg, device_capabilities={"screenshot": True})
    result = await router.route("fancy_op", {"x": "y"})
    assert result.ok is True
    assert fake.calls == [("fancy_op", {"x": "y"})]


async def test_route_no_capability_declared_passes_even_without_hello():
    """plain_op 不声明 requires,即使 device.hello 还没来也能调。"""
    reg = ProviderRegistry()
    fake = _FakeProvider()
    reg.register(fake)
    router = McpRouter(reg, device_capabilities=None)
    result = await router.route("plain_op", {})
    assert result.ok is True


async def test_set_capabilities_updates_router_runtime():
    reg = ProviderRegistry()
    fake = _FakeProvider()
    reg.register(fake)
    router = McpRouter(reg, device_capabilities=None)
    # 初始无 caps,fancy_op 应被拦
    with pytest.raises(RouteError):
        await router.route("fancy_op", {"x": "y"})
    # 上报 caps 后,放行
    router.set_capabilities({"screenshot": True})
    result = await router.route("fancy_op", {"x": "y"})
    assert result.ok is True


def test_registry_rejects_duplicate_provider():
    reg = ProviderRegistry()
    reg.register(A11yProvider())
    with pytest.raises(ValueError, match="already registered"):
        reg.register(A11yProvider())


def test_registry_rejects_empty_provider_name():
    reg = ProviderRegistry()

    class _Nameless(BaseProvider):
        name = ""

        def list_tools(self):
            return []

        async def call_tool(self, name, arguments):
            return ToolResult(ok=True)

    with pytest.raises(ValueError, match="non-empty"):
        reg.register(_Nameless())


def test_registry_unregister_missing_raises():
    reg = ProviderRegistry()
    with pytest.raises(KeyError):
        reg.unregister("ghost")


def test_registry_all_tools_aggregates_across_providers():
    reg = ProviderRegistry()
    reg.register(A11yProvider())
    reg.register(_FakeProvider())
    names = {t.name for t in reg.all_tools()}
    assert {"force_stop", "tap", "fancy_op", "plain_op"} <= names


def test_registry_find_provider_for_tool():
    reg = ProviderRegistry()
    reg.register(A11yProvider())
    reg.register(_FakeProvider())
    p = reg.find_provider_for_tool("force_stop")
    assert p is not None and p.name == "a11y"
    p = reg.find_provider_for_tool("fancy_op")
    assert p is not None and p.name == "fake"
    assert reg.find_provider_for_tool("nope") is None