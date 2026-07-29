"""Provider SPI:每个厂商 SDK / a11y / git / filesystem 都实现这个。

为什么 call_tool 是 async:
- 真 HTTP RPC 调设备 daemon 必须异步( httpx.AsyncClient )
- 项目其他模块已 async-first(FastAPI gateway),同步包 async 是 anti-pattern
- 同步 fake(如单测 in-memory)用 `async def` 关键字加 return 即可,无成本
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.mcp.protocol import ToolDefinition, ToolResult


class BaseProvider(ABC):
    """Provider 抽象基类。"""

    name: str = ""

    @abstractmethod
    def list_tools(self) -> list[ToolDefinition]:
        """返回该 Provider 暴露的所有 tool(同步,常驻内存)。"""

    @abstractmethod
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        """异步调用具体 tool。实现需校验参数 + 失败时返 ok=False + error。"""