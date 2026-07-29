"""VivoProvider:vivo SDK 工具集(系统级 + 后台管理)。

工具来源(per plan §4.2):
- force_stop: 强制停止 app(对应 vivo SDK stopApp)
- install_silent: 静默安装 APK
- lock_a11y: 锁定无障碍(企业管控)
- reboot_device: 重启设备
- kill_background: 杀后台进程(等效 force_stop to all)
- query_running_packages: 列出运行中的包(用于审计)

call_tool 流程:
  1. 工具自带必填参数校验(本地 quick-fail)
  2. 走 DaemonClient.call("vivo", tool_name, args)
  3. daemon 拿 fingerprint → 找 cert → sign → 调 vivo SDK
  4. 响应包装成 ToolResult

注意:Provider SPI 在 MCP 协议层定义.tool.name 是 LLM 看的 key,
driver 名 "vivo" 在 ProviderConfig 里,与 tool 解耦
(LLM 看到的 LLM ToolSchema 里没有 driver 字段)。
"""
from __future__ import annotations

import logging
from typing import Any

from app.agent.cert import CertProvider
from app.agent.config import ProviderConfig
from app.mcp.daemon_client import DaemonClient, DaemonError
from app.mcp.protocol import ToolArgument, ToolDefinition, ToolResult
from app.mcp.providers.base import BaseProvider

logger = logging.getLogger(__name__)


# 工具定义集中维护,方便后续 BM25 索引 + 单测校对
def _build_tool_definitions(driver: str) -> list[ToolDefinition]:
    return [
        ToolDefinition(
            name="force_stop",
            description="强制停止某个应用(按包名),后台一键 kill",
            arguments=[ToolArgument(name="pkg", type="string", description="包名,如 com.tencent.mm")],
            provider=driver,
            # 后台管控必需设备被企业 SDK 持有
            requires={"devicesdk": True},
        ),
        ToolDefinition(
            name="install_silent",
            description="静默安装 APK,不需要用户确认",
            arguments=[ToolArgument(name="apk_path", type="string", description="设备本地 APK 路径")],
            provider=driver,
            requires={"devicesdk": True},
        ),
        ToolDefinition(
            name="lock_a11y",
            description="锁定无障碍设置入口,防止用户关闭 a11y 服务",
            arguments=[],
            provider=driver,
            requires={"devicesdk": True},
        ),
        ToolDefinition(
            name="unlock_a11y",
            description="解锁无障碍设置入口",
            arguments=[],
            provider=driver,
            requires={"devicesdk": True},
        ),
        ToolDefinition(
            name="reboot_device",
            description="重启设备(企业管控场景慎用)",
            arguments=[],
            provider=driver,
            requires={"devicesdk": True},
        ),
        ToolDefinition(
            name="kill_background",
            description="清理所有后台进程,常用于批量杀后台",
            arguments=[ToolArgument(name="pkg", type="string", description="包名,空字符串表示全部", required=False)],
            provider=driver,
            requires={"devicesdk": True},
        ),
        ToolDefinition(
            name="query_running_packages",
            description="列出当前运行中的包,用于审计和状态检查",
            arguments=[],
            provider=driver,
            requires={"devicesdk": True},
        ),
    ]


# 工具必填参数规约(本地校验,fail-closed)
_REQUIRED_STRING_ARGS: dict[str, str] = {
    "force_stop": "pkg",
    "install_silent": "apk_path",
}


class VivoProvider(BaseProvider):
    """vivo SDK Provider:经 DaemonClient 走 HTTP RPC 调设备 daemon。

    证书完全在 daemon 端,本类只持 CertProvider 抽象,
    fingerprint 经 DaemonClient 调用一并送过去做路由。
    """

    name = "vivo"

    def __init__(self, config: ProviderConfig) -> None:
        self._config = config
        self._cert: CertProvider = config.cert
        self._daemon: DaemonClient = config.daemon_client
        self._tools = _build_tool_definitions(self.name)

    def list_tools(self) -> list[ToolDefinition]:
        return list(self._tools)

    def _validate_args(self, name: str, arguments: dict[str, Any]) -> str | None:
        """本地校验;返 None 表示通过,返字符串表示错误。"""
        if name not in {t.name for t in self._tools}:
            return f"unknown tool '{name}'"
        required = _REQUIRED_STRING_ARGS.get(name)
        if required is not None:
            val = arguments.get(required)
            if not val or not isinstance(val, str):
                return f"{name} requires string arg '{required}'"
        return None

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        err = self._validate_args(name, arguments)
        if err is not None:
            return ToolResult(ok=False, error=err)

        # 经 DaemonClient 走 HTTP RPC;后端不直接拿证书原文
        try:
            fp = await self._cert.fingerprint()
            response = await self._daemon.call(
                driver=self._config.driver_type,
                tool_name=name,
                arguments=arguments,
            )
        except DaemonError as exc:
            logger.warning(
                "vivo daemon call failed device=%s tool=%s err=%s",
                self._config.device_id,
                name,
                exc,
            )
            return ToolResult(ok=False, error=f"daemon error: {exc.message}")

        # 校验 daemon 响应体形
        if not isinstance(response, dict) or "ok" not in response:
            return ToolResult(ok=False, error=f"daemon invalid response: {response!r}")

        if response.get("ok") is True:
            logger.info(
                "vivo call ok device=%s tool=%s fp=%s",
                self._config.device_id,
                name,
                fp,
            )
            return ToolResult(ok=True, output=response.get("output"))

        # daemon 报 ok=False(SDK 失败、权限缺失等)
        return ToolResult(
            ok=False,
            error=str(response.get("error", "unknown daemon error")),
            output=response.get("output"),
        )