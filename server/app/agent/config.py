"""ProviderConfig:每设备 × 每驱动的配置抽象。

设计(per plan §4.5):
- driver_type:决定本 Provider 走哪类 SDK(vivo/oppo/a11y/git/...)
- device_id:路由到对应设备 daemon
- cert:CertProvider 抽象,后端不存证书原文
- daemon_client:可注入(单测用 Fake,生产用 Http)

Phase 2:VivoProvider 持有 ProviderConfig;Phase 3 通用 Adapter SPI 用
ProviderConfig 提供标准注册协议。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.agent.cert import CertProvider
from app.mcp.daemon_client import DaemonClient

DriverType = Literal["vivo", "oppo", "xiaomi", "a11y", "filesystem", "git"]


@dataclass
class ProviderConfig:
    driver_type: DriverType
    device_id: str
    cert: CertProvider
    daemon_client: DaemonClient

    def __post_init__(self) -> None:
        if not self.device_id:
            raise ValueError("device_id must be non-empty")
        if not self.driver_type:
            raise ValueError("driver_type must be non-empty")