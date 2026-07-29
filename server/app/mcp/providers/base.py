"""Provider SPI:每个厂商 SDK 适配(vivo / huawei / future)。

注册表只承载厂商 SDK Provider(走 MCP + BM25 + DaemonClient → 设备 daemon
HTTP-RPC);A11Y 是兜底通道,op 写在 system prompt 的 [TOOLS] 段,
LLM 决策时直接产 Action 下行,跟 Provider 抽象无关。详细边界见
docs/adr/0004-mcp-only-sdks.md。

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