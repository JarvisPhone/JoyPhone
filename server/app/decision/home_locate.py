# server/app/decision/home_locate.py
"""桌面找图标守卫(纯云端确定性,双向扫描)。

设计:每一页对我们等价,不区分「首页/末页」;只关心「当前方向是否还能翻」。
- 边界:连续两帧同 fingerprint(swipe 未实际翻页)。HOME 与 MINUS_ONE 走同一条判据。
- 命中当前方向边界 → 切另一方向;两向皆达边界 → abort。
- MINUS_ONE 上跳过 find_icon:负一屏通知卡片(如「飞书 有4条通知」)会造成 alias
  误命中,tap 下去要么被端侧拒(非可点/退化 bounds),要么跳到错的入口。
"""
from __future__ import annotations

import uuid

from app.decision.pkg_guard import Scene, detect_scene
from app.protocol import Action, Node, Perception
from app.protocol.models import Op


def _screen_icon_fingerprint(nodes: list[Node]) -> frozenset[str]:
    """所有节点非空 text/desc(strip)组成的集合指纹,判断当前方向 swipe 是否有效。"""
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


_MAX_SWIPE = 20  # 双向扫描总上限,防边界判据失效死翻


def _act(op: Op, params: dict) -> Action:
    return Action(actionId=str(uuid.uuid4()), op=op, params=params)


def _initial_state() -> dict:
    """扫描状态初值。默认方向 "left"(手势 swipe left = 内容左移 = 向右翻页)。

    起点无所谓从哪个方向开始:任一方向达边界后会自动切另一向补扫。
    """
    return {
        "direction": "left",
        "last_fp": None,
        "exhausted": set(),
        "swipe_count": 0,
    }


def _abort(reason_target: str) -> list[Action]:
    return [_act("abort", {"reason": f"app_not_found:{reason_target}"})]


def home_locate_action(
    perception: Perception,
    target_pkg: str,
    aliases: list[str],
    guard: dict,
) -> list[Action] | None:
    """桌面找图标守卫;不该介入返回 None(放行给后续 LLM 决策)。"""
    if not aliases:
        return None
    if perception.pkg == target_pkg:
        return None
    scene = detect_scene(perception)
    if scene not in (Scene.HOME, Scene.MINUS_ONE):
        return None

    st = guard.get("home_locate")
    if st is None:
        st = _initial_state()
        guard["home_locate"] = st

    # 安全上限兜底(边界判据理论上不会失效,但守死循环)
    if st["swipe_count"] >= _MAX_SWIPE:
        return _abort(aliases[0])

    # HOME 上尝试命中图标;MINUS_ONE 跳过 find_icon(通知卡片文本会误命中)
    if scene == Scene.HOME:
        hit = find_icon(perception.nodeTree, aliases)
        if hit is not None:
            guard.pop("home_locate", None)
            return [_act("tap", {"match_text": (hit.text or hit.desc or "").strip()})]

    # 边界:连续两帧同 fingerprint,当前方向翻不动
    current_fp = _screen_icon_fingerprint(perception.nodeTree)
    if st["last_fp"] is not None and st["last_fp"] == current_fp:
        st["exhausted"].add(st["direction"])
        if len(st["exhausted"]) >= 2:
            return _abort(aliases[0])
        # 切另一方向;last_fp=None 让下一帧属于新方向的起点,不误判边界
        st["direction"] = "right" if st["direction"] == "left" else "left"
        st["last_fp"] = None
        st["swipe_count"] += 1
        return [_act("swipe", {"direction": st["direction"]})]

    # 未到边界:记录 fp,朝当前方向继续
    st["last_fp"] = current_fp
    st["swipe_count"] += 1
    return [_act("swipe", {"direction": st["direction"]})]
