# server/app/decision/home_locate.py
"""桌面找图标守卫（纯云端确定性）。

设计: docs/superpowers/specs/2026-07-27-home-locate-guard-design.md
HOME 场景且未进目标 app 时接管:找图标 tap / 归位 / 逐屏扫描 / 到底 abort。
LLM 桌面阶段不参与。端侧、协议零改动。
"""
from __future__ import annotations

import uuid

from app.decision.pkg_guard import Scene, detect_scene
from app.protocol import Action, Node, Perception


def _screen_icon_fingerprint(nodes: list[Node]) -> frozenset[str]:
    """取所有节点非空 text/desc(strip)组成的集合指纹,判翻页到底。"""
    out: set[str] = set()
    for n in nodes:
        for raw in (n.text, n.desc):
            if raw and raw.strip():
                out.add(raw.strip())
    return frozenset(out)


def find_icon(nodes: list[Node], aliases: list[str]) -> Node | None:
    """扫节点 text/desc,命中任一 alias 返回该节点;完全相等优先于包含。"""
    lowered = [a.strip().lower() for a in aliases if a.strip()]
    if not lowered:
        return None
    best_contains: Node | None = None
    for n in nodes:
        for raw in (n.text, n.desc):
            if not raw:
                continue
            label = raw.strip().lower()
            if not label:
                continue
            if label in lowered:
                return n  # 完全相等,立即命中
            if best_contains is None and any(a in label for a in lowered):
                best_contains = n
    return best_contains


_MAX_SWIPE = 20  # 归位+扫描总上限,防双判据失效死翻


def _act(op: str, params: dict) -> Action:
    return Action(actionId=str(uuid.uuid4()), op=op, params=params)


def home_locate_action(
    perception: Perception,
    target_pkg: str,
    aliases: list[str],
    guard: dict,
) -> list[Action] | None:
    """桌面找图标守卫;不该介入返回 None(放行给后续 LLM 决策)。"""
    # fallback: 无匹配依据不介入
    if not aliases:
        return None
    # 已进目标 app / 非桌面场景 → 放行
    if perception.pkg == target_pkg:
        return None
    scene = detect_scene(perception)
    if scene not in (Scene.HOME, Scene.MINUS_ONE):
        return None

    st = guard.setdefault("home_locate", {"phase": "homing", "last_fingerprint": [], "swipe_count": 0})

    # 安全上限兜底
    if st["swipe_count"] >= _MAX_SWIPE:
        return [_act("abort", {"reason": f"app_not_found:{aliases[0]}"})]

    # 归位阶段:滑到负一屏说明越过首屏 → 退回首屏,切扫描
    if st["phase"] == "homing":
        if scene == Scene.MINUS_ONE:
            st["phase"] = "scanning"
            st["last_fingerprint"] = []
            st["swipe_count"] += 1
            return [_act("swipe", {"direction": "left"})]
        # 仍在 HOME:先找图标,命中即 tap
        hit = find_icon(perception.nodeTree, aliases)
        if hit is not None:
            guard.pop("home_locate", None)
            return [_act("tap", {"match_text": (hit.text or hit.desc or "").strip()})]
        st["swipe_count"] += 1
        return [_act("swipe", {"direction": "right"})]

    # 扫描阶段:先找图标
    hit = find_icon(perception.nodeTree, aliases)
    if hit is not None:
        guard.pop("home_locate", None)
        return [_act("tap", {"match_text": (hit.text or hit.desc or "").strip()})]
    # 指纹到底判定
    fp = _screen_icon_fingerprint(perception.nodeTree)
    if st["last_fingerprint"] and frozenset(st["last_fingerprint"]) == fp:
        return [_act("abort", {"reason": f"app_not_found:{aliases[0]}"})]
    st["last_fingerprint"] = sorted(fp)
    st["swipe_count"] += 1
    return [_act("swipe", {"direction": "left"})]