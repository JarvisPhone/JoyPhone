"""MCP 协议层:tool schema + 调用结果的数据契约。

设计上独立于具体 Provider:Provider 自己产出 ToolDefinition,
LLM 侧只看到 search_tools/call_tool 两个根工具,具体 tool 形态由
本模块统一约束(精简 schema:name + description + arg hint)。

Phase 1 只在内存层定义,不暴露 JSON-RPC wire 协议(后续阶段再接)。
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ToolArgument(BaseModel):
    """单个参数描述。LLM 看到的是精简版(只给 name + hint)。"""

    name: str
    type: str = "string"
    description: str = ""
    required: bool = True


class ToolDefinition(BaseModel):
    """Provider 暴露的一个 tool。

    `provider` 在 ProviderRegistry 注册时注入,LLM 看不到此字段。
    """

    name: str
    description: str
    arguments: list[ToolArgument] = Field(default_factory=list)
    provider: str = ""
    # 声明该 tool 需要的设备能力(如 {"screenshot": True}),
    # Router 会按 device.hello 上报的 capabilities 过滤。
    requires: dict[str, Any] = Field(default_factory=dict)


class ToolSchema(BaseModel):
    """LLM 看到的精简 schema(去掉 provider 字段)。"""

    name: str
    description: str
    arguments: list[ToolArgument]


class ToolResult(BaseModel):
    """call_tool 的标准结果。ok=False 时 error 必有,设备侧可读。"""

    ok: bool = True
    output: Any = None
    error: Optional[str] = None