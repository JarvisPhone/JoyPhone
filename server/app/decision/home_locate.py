# server/app/decision/home_locate.py
"""桌面找图标守卫（纯云端确定性）。

设计: docs/superpowers/specs/2026-07-27-home-locate-guard-design.md
HOME 场景且未进目标 app 时接管:找图标 tap / 归位 / 逐屏扫描 / 到底 abort。
LLM 桌面阶段不参与。端侧、协议零改动。
"""
from __future__ import annotations

from app.protocol import Node


def _screen_icon_fingerprint(nodes: list[Node]) -> frozenset[str]:
    """取所有节点非空 text/desc(strip)组成的集合指纹,判翻页到底。"""
    out: set[str] = set()
    for n in nodes:
        for raw in (n.text, n.desc):
            if raw and raw.strip():
                out.add(raw.strip())
    return frozenset(out)