"""CertProvider 抽象 + StaticCertProvider 实现测试。"""
from __future__ import annotations

import pytest

from app.agent.cert import CertProvider, StaticCertProvider


def test_static_cert_provider_rejects_empty_fingerprint():
    with pytest.raises(ValueError, match="fingerprint"):
        StaticCertProvider(fingerprint="", signing_key=b"k")


def test_static_cert_provider_rejects_empty_key():
    with pytest.raises(ValueError, match="signing_key"):
        StaticCertProvider(fingerprint="fp", signing_key=b"")


async def test_static_cert_provider_fingerprint_round_trip():
    cert = StaticCertProvider(fingerprint="vivo-001", signing_key=b"abc")
    assert await cert.fingerprint() == "vivo-001"


async def test_static_cert_provider_sign_deterministic():
    cert = StaticCertProvider(fingerprint="x", signing_key=b"\x01\x02\x03")
    sig1 = await cert.sign(b"hello")
    sig2 = await cert.sign(b"hello")
    assert sig1 == sig2
    assert len(sig1) == len(b"hello")  # PRF 长度等于输入


async def test_static_cert_provider_sign_different_payload_yields_different_sig():
    cert = StaticCertProvider(fingerprint="x", signing_key=b"\x01\x02\x03")
    assert await cert.sign(b"hello") != await cert.sign(b"world")


async def test_cert_provider_is_abstract():
    """CertProvider 不能直接实例化,必须子类化。"""
    with pytest.raises(TypeError):
        CertProvider()  # type: ignore[abstract]