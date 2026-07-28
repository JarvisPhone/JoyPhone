# server/app/decision/home_locate.py
"""桌面找图标守卫(纯云端确定性,双向扫描)。

设计:每一页对我们等价,不区分「首页/末页」;只关心「当前方向是否还能翻」。
- 边界:连续两帧同 fingerprint(swipe 未实际翻页)。HOME 与 MINUS_ONE 同判据。
- 命中当前方向边界 → 切另一方向;两向皆达边界 → abort。
- 图标识别只认「onscreen 可点、非 smart-card」节点:
  * ColorOS 上 detect_scene 对 HOME 的 workspace inset 会误判 MINUS_ONE,不能
    按 scene 决定要不要 find_icon;launcher 内一律尝试 find_icon。
  * 负一屏「com.nearme.instant.card / seedling」小布卡片、offscreen 页的
    离屏 TextView(bounds 退化到几十像素宽) 都通过 icon-like 过滤剔除,避免
    误命中(通知磁贴 tap 不到应用,离屏坐标 tap 也无效)。
"""
from __future__ import annotations

import uuid

from app.decision.pkg_guard import Scene, detect_scene
from app.protocol import Action, Node, Perception
from app.protocol.models import Op

# 图标最小边长:小于这个值的节点大概率是离屏(bounds 退化)或装饰性小图形,
# 100px 阈值经真机验证(app 图标典型 240×240,通知卡内元素 ≤50)。
_MIN_ICON_SIZE = 100

# smart-card viewIdResourceName 关键字:ColorOS 负一屏「小布助理」通知磁贴
# 使用这些前缀,即便 label 匹配 alias 也不作为图标入口(tap 后跳的是通知列表)。
_ICON_EXCLUDE_RESID = ("instant.card", "seedling")


def _is_icon_like(node: Node) -> bool:
    """图标节点判据:可点 + bounds 足够大 + 非 smart-card。"""
    if not node.clickable:
        return False
    b = node.bounds
    if b is None:
        return False
    w = b[2] - b[0]
    h = b[3] - b[1]
    if w < _MIN_ICON_SIZE or h < _MIN_ICON_SIZE:
        return False
    rid = node.viewIdResourceName or ""
    if any(sub in rid for sub in _ICON_EXCLUDE_RESID):
        return False
    return True


def _icons(nodes: list[Node]) -> list[Node]:
    return [n for n in nodes if _is_icon_like(n)]


def _screen_icon_fingerprint(nodes: list[Node]) -> frozenset[str]:
    """当前屏可点 icon 的 text/desc 集合;判断 swipe 是否实际翻页。

    只算 icon-like 节点,避免小布卡片加载状态刷新(「一键加速」→「一键加速可释放 445MB」)
    污染指纹导致误判"还在翻页"。
    """
    out: set[str] = set()
    for n in _icons(nodes):
        for raw in (n.text, n.desc):
            if raw and raw.strip():
                out.add(raw.strip())
    return frozenset(out)


def find_icon(nodes: list[Node], aliases: list[str]) -> Node | None:
    """在 icon-like 节点里扫 text/desc,命中任一 alias 返回该节点;完全相等优先。"""
    lowered = [a.strip().lower() for a in aliases if a.strip()]
    if not lowered:
        return None
    best_contains: Node | None = None
    for n in _icons(nodes):
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

    # HOME/MINUS_ONE 一律尝试命中(icon-like 过滤剔除通知卡片和离屏元素)
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
