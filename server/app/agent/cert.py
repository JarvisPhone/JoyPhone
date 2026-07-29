"""CertProvider 抽象:设备侧存证书,后端不存证书原文。

设计要点(per plan §4.5):
- 后端只持 CertProvider 接口,不见证书原文
- 设备 daemon 启动时从本机读证书 → 构造 CertProvider 实例 → 经 DaemonClient 代理
- 后端到 daemon 的链路只传 fingerprint(用于路由)+ 签名结果(由 daemon 完成)
- fingerprint 是设备的"逻辑 ID",用于后端路由表(device_id → alive drivers)
- sign() 在 daemon 端完成,后端只下指令 + 收结果

Phase 2 实装:
- ABC 定义接口
- StaticCertProvider 简单实现(指纹 + 静态签名,用于单测/真设备首启)
- 真实生产实现(OSKeystore 等)Phase 3 接入
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class CertProvider(ABC):
    """证书抽象。返回 fingerprint + 签名结果,后端不存证书原文。"""

    @abstractmethod
    async def fingerprint(self) -> str:
        """设备指纹,用于后端路由表查找。"""

    @abstractmethod
    async def sign(self, payload: bytes) -> bytes:
        """对 payload 签名。签名前后端只通过该函数交互,原文不外泄。"""


class StaticCertProvider(CertProvider):
    """Phase 2 用的简单实现:fingerprint + 固定签名 key。

    真实生产场景:由设备 daemon 加载 OS keystore / 出厂预置凭证生成。
    """

    def __init__(self, fingerprint: str, signing_key: bytes) -> None:
        if not fingerprint:
            raise ValueError("fingerprint must be non-empty")
        if not signing_key:
            raise ValueError("signing_key must be non-empty")
        self._fingerprint = fingerprint
        self._key = signing_key

    async def fingerprint(self) -> str:
        return self._fingerprint

    async def sign(self, payload: bytes) -> bytes:
        # 极简 PRF:重复 key XOR payload(仅为契约示例,真实场景用 HMAC-SHA256)
        return bytes(b ^ self._key[i % len(self._key)] for i, b in enumerate(payload))