"""A11y Provider:Phase 1 MiniMock,内存模拟。

暴露 4 个最常用 tool(force_stop/tap/swipe/input),均不打真设备,
只把调用记录到内存并返回 ok=True。Phase 2 接入真 a11y 通路。
"""
from __future__ import annotations

import logging
from typing import Any

from app.mcp.protocol import ToolArgument, ToolDefinition, ToolResult
from app.mcp.providers.base import BaseProvider

logger = logging.getLogger(__name__)


class A11yProvider(BaseProvider):
    name = "a11y"

    def __init__(self) -> None:
        # MiniMock:记录每次调用,便于单测断言
        self.calls: list[dict[str, Any]] = []

    def list_tools(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name="force_stop",
                description="强制停止某个应用(按包名),后台一键 kill",
                arguments=[ToolArgument(name="pkg", type="string", description="包名,如 com.tencent.mm")],
                provider=self.name,
            ),
            ToolDefinition(
                name="tap",
                description="按语义锚点点击屏幕上的一个节点",
                arguments=[
                    ToolArgument(name="match_text", type="string", description="目标节点文本"),
                    ToolArgument(name="occurrence", type="string", description="同名匹配第几次出现,从 1 起", required=False),
                ],
                provider=self.name,
            ),
            ToolDefinition(
                name="swipe",
                description="从一个点到另一个点滑动",
                arguments=[
                    ToolArgument(name="x1", type="number", description="起点 x"),
                    ToolArgument(name="y1", type="number", description="起点 y"),
                    ToolArgument(name="x2", type="number", description="终点 x"),
                    ToolArgument(name="y2", type="number", description="终点 y"),
                ],
                provider=self.name,
            ),
            ToolDefinition(
                name="input",
                description="在当前聚焦输入框输入文本",
                arguments=[ToolArgument(name="text", type="string", description="要输入的文本")],
                provider=self.name,
            ),
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        # 校验:必填参数缺失就返 ok=False,而不是抛异常(Router 上层会拿到 ToolResult)
        if name == "force_stop":
            pkg = arguments.get("pkg")
            if not pkg or not isinstance(pkg, str):
                return ToolResult(ok=False, error="force_stop requires string arg 'pkg'")
        elif name == "tap":
            mt = arguments.get("match_text")
            if not mt or not isinstance(mt, str):
                return ToolResult(ok=False, error="tap requires string arg 'match_text'")
        elif name == "swipe":
            for k in ("x1", "y1", "x2", "y2"):
                if k not in arguments:
                    return ToolResult(ok=False, error=f"swipe requires arg '{k}'")
        elif name == "input":
            txt = arguments.get("text")
            if txt is None or not isinstance(txt, str):
                return ToolResult(ok=False, error="input requires string arg 'text'")
        else:
            return ToolResult(ok=False, error=f"a11y provider: unknown tool '{name}'")

        self.calls.append({"name": name, "arguments": dict(arguments)})
        logger.info("a11y mock call name=%s args=%s", name, arguments)
        return ToolResult(ok=True, output={"mocked": True, "name": name})