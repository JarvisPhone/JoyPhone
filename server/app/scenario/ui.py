"""场景层 UI 识别 helpers:发送按钮 / 消息输入框 / 目标解析。

纯函数,无副作用。关键词一律来自 AppProfile 参数,与具体 app 解耦。
移植自旧 chat_title_helpers(is_send_button / is_message_input)与
app_goal_resolver(resolve_target_pkg / extract_target);
match_chat_title 已在 decision/ui_inspect.py(T3),此处仅 re-export
match_title 供场景层使用,不重复实现。
"""
from __future__ import annotations

import re
from typing import Mapping, Optional, Sequence

from app.decision.ui_inspect import match_title
from app.protocol import Node
from app.scenario.base import AppProfile

__all__ = [
    "extract_target",
    "is_message_input",
    "is_send_button",
    "match_title",
    "resolve_anchor_node",
    "resolve_pkg",
]


def resolve_anchor_node(params: Mapping[str, object], nodes: list[Node]) -> Node | None:
    """按语义锚点在节点列表中定位目标节点(与端侧 AnchorResolver 同一阶梯语义)。

    阶梯:match_rid 尾段精确 -> text 精确 -> desc 精确;
    同名多节点时按 occurrence 选取;无锚点或未命中返回 None(fail-closed,
    不做子串猜测)。云端策略(确认拦截/错群守卫)借此把 decided action
    还原为语义节点,不再依赖会过期的坐标。
    """
    rid = str(params.get("match_rid", "") or "").strip()
    text = str(params.get("match_text", "") or "").strip()
    matches: list[Node] = []
    if rid:
        matches = [n for n in nodes
                   if (n.viewIdResourceName or "").rsplit("/", 1)[-1] == rid]
    elif text:
        matches = [n for n in nodes if (n.text or "").strip() == text]
        if not matches:
            matches = [n for n in nodes if (n.desc or "").strip() == text]
    if not matches:
        return None
    occ = params.get("occurrence")
    if occ is not None and str(occ).strip() != "":
        try:
            i = int(str(occ))
        except (ValueError, TypeError):
            return None
        return matches[i] if 0 <= i < len(matches) else None
    return matches[0]


# 旧 chat_title_helpers._SEND_BUTTON_RID_KEYWORDS。
# profile.send_button_keywords 是「rid 关键词 + text 关键词」合并的单一列表,
# 匹配语义必须与旧实现等价:rid 只匹配 rid 关键词,label 只匹配 text 关键词,
# 因此在函数内按关键词来源分流(在该集合内 -> rid 匹配,否则 -> label 匹配)。
_SEND_BUTTON_RID_KEYWORDS: frozenset[str] = frozenset({
    "send_button",
    "btn_send",
    "iv_send",
    "send_btn",
    "ib_send",
    "tv_send",
    "sendmessage",
})


def is_send_button(node: Node, profile: AppProfile) -> bool:
    """判断节点是否「发送」按钮。

    与旧 chat_title_helpers.is_send_button 等价:
      - rid 命中 rid 关键词 -> True
      - label(text+desc)命中 text 关键词 -> True
      - 二者不交叉(text 关键词如 "send" 不匹配 rid,避免
        "message_sender_avatar" 之类 rid 误判)
    """
    rid = (node.viewIdResourceName or "").lower()
    label = ((node.text or "") + " " + (node.desc or "")).strip().lower()
    for kw in profile.send_button_keywords:
        k = kw.lower()
        if k in _SEND_BUTTON_RID_KEYWORDS:
            if k in rid:
                return True
        elif k in label:
            return True
    return False


def is_message_input(node: Node, profile: AppProfile) -> bool:
    """判断节点是否为「聊天正文输入框」(而非搜索框)。

    保守策略(避免误伤搜群名的搜索框):
      - 非 editable 直接 False(用 editable 比 className 更可靠)
      - desc+text 组合的小写标签命中 profile.search_hints -> False
      - 命中 profile.message_input_hints -> True
      - 都不命中 -> False(宁可漏拦也不误拦搜索框)

    漏判只会退化为「不拦截」,属于保守失败方向。
    """
    if not node.editable:
        return False
    label = ((node.text or "") + " " + (node.desc or "")).strip().lower()
    if not label:
        return False
    if any(kw.lower() in label for kw in profile.search_hints):
        return False
    return any(kw.lower() in label for kw in profile.message_input_hints)


def resolve_pkg(goal: str, profiles: Sequence[AppProfile]) -> Optional[str]:
    """从 goal 里提取目标 app 的 package;无法识别返回 None。

    规则:goal 中出现任一 profile 的别名(中文/英文,大小写不敏感)
    即返回首个匹配的 pkg。别名表归位于各 profile.aliases。
    """
    if not goal:
        return None
    haystack = goal.lower()
    for profile in profiles:
        for alias in profile.aliases:
            if alias.lower() in haystack:
                return profile.pkg
    return None


# ---- 目标标识符提取(群名 / 联系人)----
# 优先级:成对引号 > 成对书名号 > 裸词(在「给/找/发给/搜索/搜...」之后)
_BRACKETED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"[“”]([^“”]{2,40})[“”]"),  # "..."
    re.compile(r"[「」]([^「」]{2,40})[「」]"),  # 「...」
    re.compile(r"[『』]([^『』]{2,40})[『』]"),  # 『...』
)

def extract_target(goal: str) -> Optional[str]:
    """从自然语言 goal 里提取消息接收方(群名 / 联系人)。无法识别返回 None。

    三层匹配:
      1. 双引号 / 「」 / 『』 包起来的字符串("给『张三』发消息" -> 张三)
      2. 「给/发给/搜索/找 X 群/好友/消息」句式里 X(裸词,中文/英文 up to 40 字)
      3. 没匹配到 -> None (走 LLM 决策上下文,不强校验)
    """
    if not goal:
        return None

    for pat in _BRACKETED_PATTERNS:
        m = pat.search(goal)
        if m:
            t = m.group(1).strip()
            if t:
                return t

    structural = re.search(
        r"(?:给|发给|给到|发送给|发给|发消息给|搜索|搜|搜一下|找|找一下)\s*"
        r"([一-鿿A-Za-z0-9_\-\s]{2,40}?)\s*"
        r"(?:发|群|好友|联系人|发一条|发一条消息|发消息|发信息|发条消息|发条信息|发微信|发飞书|$)",
        goal,
    )
    if structural:
        t = structural.group(1).strip()
        t = re.sub(r"^(群|好友|联系人|群组)\s*", "", t)
        if t:
            return t

    return None
