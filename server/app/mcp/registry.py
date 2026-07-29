"""Provider Registry:进程内 MCP server 注册表。

设计:
- 内存 dict:provider_name -> Provider 实例
- tool 全集 = 所有 Provider.list_tools() 之并(BM25 索引基于此构建)
- 同名 Provider 重复 register 抛错(防 ghost override)
"""
from __future__ import annotations

import logging

from app.mcp.protocol import ToolDefinition
from app.mcp.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, BaseProvider] = {}

    def register(self, provider: BaseProvider) -> None:
        if not provider.name:
            raise ValueError("provider.name must be non-empty")
        if provider.name in self._providers:
            raise ValueError(f"provider already registered: {provider.name}")
        self._providers[provider.name] = provider
        logger.info("mcp provider registered name=%s tools=%d", provider.name, len(provider.list_tools()))

    def unregister(self, name: str) -> None:
        removed = self._providers.pop(name, None)
        if removed is None:
            raise KeyError(f"provider not registered: {name}")
        logger.info("mcp provider unregistered name=%s", name)

    def get(self, name: str) -> BaseProvider | None:
        return self._providers.get(name)

    def names(self) -> list[str]:
        return list(self._providers.keys())

    def all_tools(self) -> list[ToolDefinition]:
        """所有 Provider 暴露的 tool 列表(并集)。

        同名 tool 由调用方负责去重(理论上 Provider SPI 不允许重名)。
        """
        tools: list[ToolDefinition] = []
        for p in self._providers.values():
            tools.extend(p.list_tools())
        return tools

    def find_provider_for_tool(self, tool_name: str) -> BaseProvider | None:
        """按 tool 名查 Provider(首个匹配)。"""
        for p in self._providers.values():
            for t in p.list_tools():
                if t.name == tool_name:
                    return p
        return None