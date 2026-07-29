"""DaemonClient:后端 ↔ 设备 daemon 的 HTTP RPC 客户端。

设计:
- 抽象为接口是为了单测可注入 Fake(不依赖真 daemon)
- 真实现用 httpx.AsyncClient,daemon 暴露 `/mcp/{driver}/{tool_name}` 端点
- 请求体:`{device_id, fingerprint, arguments}`,签名由 daemon 端 cert 做
- 响应体:`{ok, output?, error?}`(与 ToolResult 契约对齐)

Phase 2 实装 HttpDaemonClient + FakeDaemonClient;Phase 4 多设备时
DaemonClient 持有 device_id 维度的路由表(同一进程多 device)。

注:鉴权链路:
  1. 后端 DaemonClient 收到请求 → 注入 device_id + fingerprint
  2. daemon 收到 → 拿 fingerprint 找本地 cert → sign + 调 SDK
  3. SDK 响应回 daemon → daemon 包装成 ToolResult → 后端
  后端永远不见证书原文,fingerprint 仅是逻辑 ID。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class DaemonClient(ABC):
    """后端 → 设备 daemon 的 HTTP RPC 客户端接口。"""

    @abstractmethod
    async def call(self, driver: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """驱发 daemon 上的 tool。

        Args:
            driver: 驱动族名,如 "vivo" / "oppo" / "a11y"
            tool_name: MCP tool 名
            arguments: tool 参数

        Returns:
            daemon 返回的 JSON 对象,需含 `ok` 字段(bool)。
            实际负载在 `output` 字段,失败时含 `error` 字段。

        Raises:
            DaemonError: 网络/超时/HTTP 状态非 2xx。
        """


class DaemonError(Exception):
    """daemon 通讯失败:网络 / 超时 / 5xx / 响应格式错。"""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class HttpDaemonClient(DaemonClient):
    """httpx 实现的真 client,daemon URL 由 device_id → url 路由表给出(Phase 4 接入)。

    Phase 2 单测不直接用 HttpDaemonClient,统一走 FakeDaemonClient。
    Phase 4 把 device_id → daemon_url 路由表实装后再用。

    设计:client 抽成 `_open_client()` 方法,单测可 override 注入 mock transport,
    不依赖 pytest-httpx / respx 等额外包。
    """

    def __init__(self, base_url: str, timeout_sec: float = 5.0) -> None:
        if not base_url:
            raise ValueError("base_url must be non-empty")
        self._base_url = base_url.rstrip("/")
        self._timeout_sec = timeout_sec

    def _open_client(self) -> Any:
        """开一个 httpx async client;单测可 override 注入 mock transport。"""
        import httpx

        return httpx.AsyncClient(timeout=self._timeout_sec)

    async def call(self, driver: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        import httpx

        url = f"{self._base_url}/mcp/{driver}/{tool_name}"
        try:
            async with self._open_client() as client:
                resp = await client.post(url, json={"arguments": arguments})
        except httpx.TimeoutException as exc:
            raise DaemonError(f"daemon timeout: {url}", status_code=None) from exc
        except httpx.HTTPError as exc:
            raise DaemonError(f"daemon http error: {exc}", status_code=None) from exc

        if resp.status_code < 200 or resp.status_code >= 300:
            raise DaemonError(
                f"daemon returned {resp.status_code}: {resp.text}",
                status_code=resp.status_code,
            )

        try:
            body = resp.json()
        except Exception as exc:
            raise DaemonError(f"daemon response not JSON: {resp.text}", status_code=resp.status_code) from exc

        if not isinstance(body, dict) or "ok" not in body:
            raise DaemonError(
                f"daemon response missing 'ok': {body!r}",
                status_code=resp.status_code,
            )
        return body


class FakeDaemonClient(DaemonClient):
    """单测 in-memory 实现:模拟 daemon,支持预设响应 + 录所有调用。"""

    def __init__(
        self,
        responses: dict[tuple[str, str], dict[str, Any]] | None = None,
        default: dict[str, Any] | None = None,
    ) -> None:
        """
        Args:
            responses: 预设 (driver, tool_name) -> response body;匹配即返回
            default: 未命中预设时的默认响应;若也 None 则报 ok=True 空响应
        """
        self._responses: dict[tuple[str, str], dict[str, Any]] = dict(responses or {})
        self._default = default if default is not None else {"ok": True, "output": {"mocked": True}}
        self.calls: list[dict[str, Any]] = []

    async def call(self, driver: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append({"driver": driver, "tool_name": tool_name, "arguments": dict(arguments)})
        return self._responses.get((driver, tool_name), dict(self._default))


class ErrorDaemonClient(DaemonClient):
    """单测用:模拟 daemon 抛错的 client。"""

    def __init__(self, message: str = "daemon down", status_code: int | None = 500) -> None:
        self._message = message
        self._status = status_code
        self.calls: list[dict[str, Any]] = []

    async def call(self, driver: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append({"driver": driver, "tool_name": tool_name, "arguments": dict(arguments)})
        raise DaemonError(self._message, status_code=self._status)