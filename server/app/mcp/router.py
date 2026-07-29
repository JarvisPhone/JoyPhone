"""MCP Router:call_tool 的中央分发。

职责:
1. 按 tool_name 找 Provider
2. 按 device.hello 上报的 capabilities 过滤(Phase 1 仅按 Provider 声明的 requires)
3. 调 Provider.call_tool 返回 ToolResult
4. 错误统一包成 RouteError(tool_name, reason)
"""
from __future__ import annotations

import logging
from typing import Any

from app.mcp.protocol import ToolResult
from app.mcp.registry import ProviderRegistry

logger = logging.getLogger(__name__)


class RouteError(Exception):
    """路由失败(tool 不存在 / capability 不满足 / provider 拒绝)。

    Router 总是 fail-closed:异常或 ToolResult(ok=False) 都向上抛。
    """

    def __init__(self, tool_name: str, reason: str) -> None:
        super().__init__(f"route failed for '{tool_name}': {reason}")
        self.tool_name = tool_name
        self.reason = reason


class McpRouter:
    """call_tool 路由。

    device_capabilities 是 device.hello 上报的 capabilities dict,
    为空 dict 表示"暂未知"(Phase 1 默认放行所有 tool,Phase 4 加严格裁剪)。
    """

    def __init__(
        self,
        registry: ProviderRegistry,
        device_capabilities: dict[str, Any] | None = None,
    ) -> None:
        self._registry = registry
        # None 表示尚未收到 device.hello,所有 capability-required tool 不放行
        self._caps = device_capabilities

    def set_capabilities(self, caps: dict[str, Any]) -> None:
        self._caps = dict(caps)

    async def route(self, tool_name: str, arguments: dict[str, Any]) -> ToolResult:
        provider = self._registry.find_provider_for_tool(tool_name)
        if provider is None:
            raise RouteError(tool_name, f"no provider for tool '{tool_name}'")

        # capability 裁剪:tool.requires 必须全部满足
        tool = next(
            (t for t in provider.list_tools() if t.name == tool_name),
            None,
        )
        if tool is None:
            # 理论上 find_provider_for_tool 已保证能找到,防御性兜底
            raise RouteError(tool_name, "tool disappeared after lookup")
        if tool.requires:
            if self._caps is None:
                raise RouteError(
                    tool_name,
                    f"tool requires {tool.requires} but device.hello not yet received",
                )
            for k, v in tool.requires.items():
                if self._caps.get(k) != v:
                    raise RouteError(
                        tool_name,
                        f"capability '{k}' required={v} but device reports {self._caps.get(k)!r}",
                    )

        logger.info("mcp route name=%s provider=%s", tool_name, provider.name)
        return await provider.call_tool(tool_name, arguments)