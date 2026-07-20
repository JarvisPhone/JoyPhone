"""屏幕场景状态机 + pkg 收敛守卫。

把一帧感知(Perception)归类到有限的屏幕场景,替代只看 pkg 的裸 guard,
根治 launcher 各态之间兜圈的死循环。pkg_guard_action 在目标 app 已解析
且与当前 pkg 不一致时,按场景状态机逐帧收敛回 HOME(跳过 LLM,避免看到
通知/磁贴就 tap 跑飞),并配三级脱困阶梯(LLM 脱困 -> 机械降级 -> abort)。

区分规则(与真机采样分析对齐):
1. pkg 不是 launcher/systemui   -> IN_APP(在目标 App / 任意第三方 App 内)
2. pkg 是 systemui:
     - lock_icon_view / keyguard        -> LOCK_SCREEN
     - expandableNotificationRow        -> NOTIFICATION(下拉通知)
     - qs 磁贴 / oplus_qs_clock          -> CONTROL_CENTER(控制中心)
3. pkg 是 launcher:
     - overview_panel / task_header      -> RECENT_APPS(最近任务)
     - workspace 全屏 [0,0,..]           -> HOME(桌面,首屏/其他屏都归 HOME)
     - workspace 内缩 (left/top > 0)      -> MINUS_ONE(负一屏)
4. 其余(空感知/无法识别)                 -> UNKNOWN

resource-id 用后缀匹配(endswith/contains),不硬编码完整 oplus 包名前缀,保跨设备普适。
负一屏判据是 workspace 的 bounds 尺寸: home 全屏(left=0,top=0),负一屏被卡片
容器包裹有内边距(left/top > 0)——这是唯一稳定判据,不看搜索框/卡片等内容特征。
"""
from __future__ import annotations

import json
import logging
import uuid
from enum import Enum
from typing import Optional

from app.decision.llm import LLM
from app.protocol import Action, Perception

_LAUNCHER = "launcher"
_SYSTEMUI = "systemui"


# ==== 场景状态机配置常量 ====
class SceneConfig:
    """场景状态机相关配置常量，统一管理魔法数字。"""
    STALL_THRESHOLD = 3       # 连续同 scene 同 op 判停滞
    CYCLE_THRESHOLD = 2       # 非目标 scene 在窗口内重复次数判振荡
    WINDOW = 6                # scene_history 窗口长度
    LLM_ESCALATION_TRIES = 1  # 给 LLM 几次脱困机会
    FALLBACK_TRIES = 2        # 机械降级动作尝试次数


class Scene(str, Enum):
    HOME = "home"                    # 桌面(首屏及其他屏,不区分第几屏)
    MINUS_ONE = "minus_one"          # 负一屏
    NOTIFICATION = "notification"    # 下拉通知栏
    CONTROL_CENTER = "control_center"  # 控制中心
    IN_APP = "in_app"                # 在某个 App 内(含目标 App)
    LOCK_SCREEN = "lock_screen"      # 锁屏
    RECENT_APPS = "recent_apps"      # 最近任务
    UNKNOWN = "unknown"              # 无法识别


def _ids(perception: Perception) -> list[str]:
    """收集所有节点的 viewIdResourceName(非空)。"""
    return [n.viewIdResourceName or "" for n in perception.nodeTree if n.viewIdResourceName]


def _has_id(ids: list[str], *needles: str) -> bool:
    """任一节点 resource-id 的 :id/ 段包含给定关键词(后缀 contains,不看包名)。"""
    for rid in ids:
        seg = rid.rsplit("/", 1)[-1]  # ':id/lock_icon_view' -> 'lock_icon_view'
        if any(needle in seg for needle in needles):
            return True
    return False


def _workspace_node(perception: Perception):
    """找 launcher 的 workspace 节点,用其 bounds 区分 home / 负一屏。"""
    for n in perception.nodeTree:
        rid = n.viewIdResourceName or ""
        if rid.rsplit("/", 1)[-1] == "workspace" and _LAUNCHER in rid:
            return n
    return None


def detect_scene(perception: Perception) -> Scene:
    pkg = perception.pkg or ""

    # 空感知直接 UNKNOWN
    if not pkg and not perception.nodeTree:
        return Scene.UNKNOWN

    # 1. 非系统界面 -> 在 App 内(优先级最高)
    if pkg and _LAUNCHER not in pkg and _SYSTEMUI not in pkg:
        return Scene.IN_APP

    ids = _ids(perception)

    # 2. systemui 三态
    if _SYSTEMUI in pkg:
        if _has_id(ids, "lock_icon_view", "keyguard"):
            return Scene.LOCK_SCREEN
        if _has_id(ids, "expandableNotificationRow"):
            return Scene.NOTIFICATION
        if _has_id(ids, "qs_clock", "qs_tile", "qs_panel", "quick_settings"):
            return Scene.CONTROL_CENTER
        return Scene.UNKNOWN

    # 3. launcher 各态
    if _LAUNCHER in pkg:
        if _has_id(ids, "overview_panel", "task_header"):
            return Scene.RECENT_APPS
        ws = _workspace_node(perception)
        if ws is not None and ws.bounds is not None:
            left, top, _, _ = ws.bounds
            # 内缩(有边距)=负一屏;全屏(left=0,top=0)=桌面
            if left > 0 or top > 0:
                return Scene.MINUS_ONE
            return Scene.HOME
        return Scene.UNKNOWN

    return Scene.UNKNOWN


# ==== 场景转移表 ====
# 职责分层: LLM 只输出「想去的目标场景」,不碰具体 op;本地维护转移表把
# (from_scene, to_scene) 翻译成端侧动作,并由外层逐帧重判 scene 收敛到位——
# 即转移表提供「单步导航」,动作执行后重抓帧再判,直到 detect_scene==target。
#
# 目前只覆盖「收敛回 HOME」这一组(pkg guard 的核心诉求)。后续可按需扩展
# 任意两场景间的最短路径。表里没有的 (from,to) 用 home 兜底。
_TRANSITIONS: dict[tuple["Scene", "Scene"], tuple[str, dict]] = {
    # 负一屏在桌面最左侧,向右滑退出回到桌面
    (Scene.MINUS_ONE, Scene.HOME): ("swipe", {"direction": "right"}),
    # 最近任务界面按 home 键回桌面
    (Scene.RECENT_APPS, Scene.HOME): ("home", {}),
    # 下拉通知栏 / 控制中心 back 收起
    (Scene.NOTIFICATION, Scene.HOME): ("back", {}),
    (Scene.CONTROL_CENTER, Scene.HOME): ("back", {}),
    # 在 App 内回桌面
    (Scene.IN_APP, Scene.HOME): ("home", {}),
}


def next_action(current: "Scene", target: "Scene") -> Optional[Action]:
    """朝 target 收敛的下一个动作;已在 target 返回 None。

    表里没有精确 (current, target) 项时,用 home 兜底——它能把
    绝大多数异常场景(未知/锁屏等)拉回桌面确定起点,外层再重判 scene 继续收敛。
    """
    if current == target:
        return None
    op, params = _TRANSITIONS.get((current, target), ("home", {}))
    return Action(actionId=str(uuid.uuid4()), op=op, params=dict(params))


# 机械降级备选表：主转移动作失效时的次选动作（每个非目标 scene 至少一个）。
_FALLBACK: dict[tuple["Scene", "Scene"], tuple[str, dict]] = {
    (Scene.MINUS_ONE, Scene.HOME): ("home", {}),          # swipe right 失效 -> 按 home 键
    (Scene.RECENT_APPS, Scene.HOME): ("back", {}),        # home 键失效 -> back
    (Scene.NOTIFICATION, Scene.HOME): ("home", {}),
    (Scene.CONTROL_CENTER, Scene.HOME): ("home", {}),
    (Scene.IN_APP, Scene.HOME): ("home", {}),
}


def fallback_action(current: "Scene", target: "Scene") -> Optional[Action]:
    """机械降级备选动作；已在 target 返回 None，无备选时默认按 home 键兜底。"""
    if current == target:
        return None
    op, params = _FALLBACK.get((current, target), ("home", {}))
    return Action(actionId=str(uuid.uuid4()), op=op, params=dict(params))


_ESCAPE_PROMPT = (
    "你是屏幕导航脱困助手。当前自动化在场景间反复横跳或停滞，无法到达目标场景。"
    "根据 current_scene / target_scene / scene_history，判断应先前往哪个中间场景来脱困。"
    "只输出一行：target_scene: <SCENE>，其中 <SCENE> 为大写枚举名"
    "（HOME/MINUS_ONE/NOTIFICATION/CONTROL_CENTER/IN_APP/LOCK_SCREEN/RECENT_APPS/UNKNOWN）。"
)


def _parse_target_scene(raw: str) -> Scene | None:
    """从 LLM 文本里解析出 target_scene: <SCENE>。识别不了返回 None。"""
    if not raw:
        return None
    for line in raw.splitlines():
        line = line.strip()
        _, sep, rest = line.partition("target_scene:")
        if not sep:
            continue
        name = rest.strip().upper()
        try:
            return Scene[name]
        except KeyError:
            return None
    return None


def llm_escape(
    escape_llm: LLM,
    perception: Perception,
    current: Scene,
    target: Scene,
    guard: dict,
) -> list[Action]:
    raw = escape_llm.complete(
        system=_ESCAPE_PROMPT,
        user=json.dumps({
            "current_scene": current.value,
            "target_scene": target.value,
            "scene_history": guard.get("scene_history", []),
        }, ensure_ascii=False),
    )
    new_target = _parse_target_scene(raw) or target
    act = next_action(current, new_target) or next_action(current, Scene.HOME)
    return [act] if act else [Action(actionId=str(uuid.uuid4()), op="home", params={})]


def pkg_guard_action(
    perception: Perception,
    target_pkg: str,
    guard: dict | None,
    escape_llm: LLM,
) -> list[Action] | None:
    """pkg 边界守卫:跑错应用时按场景状态机收敛回 HOME,不收敛返回 None。"""
    if not (target_pkg and perception.pkg and perception.pkg != target_pkg):
        return None
    current = detect_scene(perception)
    action = next_action(current, Scene.HOME)
    if action is None:  # 已在 HOME，放行给正常任务决策
        return None
    logging.getLogger("phoneagent.gateway").info(
        "[PKG_GUARD] scene=%s target_pkg=%s -> op=%s",
        current.value, target_pkg, action.op,
    )
    op = action.op
    # ==== 收敛守卫 ====
    # 停滞：相邻两帧 (scene, op) 相同则累加
    gd = guard if guard is not None else {}
    key = f"{current.value}|{op}"
    if gd.get("last_op") == key:
        gd["stall_count"] = gd.get("stall_count", 0) + 1
    else:
        gd["stall_count"] = 0
    gd["last_op"] = key
    # scene_history 滑窗
    hist = gd.setdefault("scene_history", [])
    hist.append(current.value)
    if len(hist) > SceneConfig.WINDOW:
        del hist[0]
    stalled = gd["stall_count"] >= SceneConfig.STALL_THRESHOLD
    oscillating = (
        current != Scene.HOME
        and hist.count(current.value) >= SceneConfig.CYCLE_THRESHOLD + 1
    )
    # ==== 三级脱困阶梯 ====
    if stalled or oscillating:
        lvl = gd.get("escalation_level", 0)
        if lvl == 0:
            gd["escalation_level"] = 1
            return llm_escape(escape_llm, perception, current, Scene.HOME, gd)
        if lvl == 1:
            gd["escalation_level"] = 2
            fb = fallback_action(current, Scene.HOME)
            if fb is not None:
                return [fb]
        # lvl >= 2：机械降级仍卡 -> abort
        return [Action(actionId=str(uuid.uuid4()), op="abort",
                       params={"reason": f"pkg_guard_stuck:{current.value}"})]
    return [action]
