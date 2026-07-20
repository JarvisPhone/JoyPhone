"""场景层 UI 识别 helpers:发送按钮 / 消息输入框 / 目标解析。

纯函数,无副作用。关键词一律来自 AppProfile 参数,与具体 app 解耦。
移植自旧 chat_title_helpers(is_send_button / is_message_input)与
app_goal_resolver(resolve_target_pkg / extract_target);
match_chat_title 已在 decision/ui_inspect.py(T3),此处仅 re-export
match_title 供场景层使用,不重复实现。
"""
from __future__ import annotations

import re
from typing import Optional, Sequence

from app.decision.ui_inspect import match_title
from app.protocol import Node
from app.scenario.base import AppProfile

__all__ = [
    "extract_target",
    "is_message_input",
    "is_send_button",
    "match_title",
    "resolve_pkg",
]


def is_send_button(node: Node, profile: AppProfile) -> bool:
    """判断节点是否「发送」按钮。

    resource id / text / desc 任一命中 profile.send_button_keywords
    即视为「即将点发送」,需要拦截做群名校验。
    """
    rid = (node.viewIdResourceName or "").lower()
    label = ((node.text or "") + " " + (node.desc or "")).strip().lower()
    return any(
        kw.lower() in rid or kw.lower() in label
        for kw in profile.send_button_keywords
    )


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
