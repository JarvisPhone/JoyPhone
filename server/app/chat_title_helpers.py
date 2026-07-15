"""聊天页识别 + 发送按钮识别 + 群名校验 helpers。

纯函数,无副作用。给 gateway.py 在下行 action 拦截时使用,
不放在 decision.py 里,以免污染 LLM 决策路径。
"""
from __future__ import annotations

from typing import Iterable, Optional

from app.protocol import Node


# 飞书 / 微信 / QQ 在「即将发送」这一帧的群名 / 联系人名 通常出现在 toolbar 顶部。
# 已知 resource id 关键词(不全,作为软匹配),命中任一即认为是 title 节点。
_TITLE_RID_KEYWORDS: tuple[str, ...] = (
    "title",
    "chat_name",
    "conversation_name",
    "tv_title",
    "tv_chat_name",
    "toolbar_title",
    "action_bar",
    "tv_conversation",
)


# 发送按钮:resource id / text / desc 任一命中即视为「即将点发送」,需要拦截做群名校验。
_SEND_BUTTON_RID_KEYWORDS: tuple[str, ...] = (
    "send_button",
    "btn_send",
    "iv_send",
    "send_btn",
    "ib_send",
    "tv_send",
    "sendmessage",
)

_SEND_BUTTON_TEXT_KEYWORDS: tuple[str, ...] = (
    "发送",  # 中文
    "send",  # 英文小写
    "sending",
)


def detect_chat_title(nodeTree: Iterable[Node]) -> Optional[str]:
    """从当前屏幕节点树里识别群名 / 联系人名(飞书 / 微信 聊天页顶部 toolbar)。

    策略(按优先级):
      1. resource id 含 title/chat_name 等关键词 的节点的 text
      2. desc 含「title」或「标题」的节点的 text
      3. 退化:第一个非输入区、长度 ≥ 2 的非空 text

    返回 None 表示当前不在聊天页 / 无法识别。
    """
    nodes = list(nodeTree)

    # 1) resource id 命中
    for n in nodes:
        rid = (n.viewIdResourceName or "").lower()
        if any(k in rid for k in _TITLE_RID_KEYWORDS):
            t = (n.text or "").strip()
            if len(t) >= 2:
                return t

    # 2) desc 命中(部分 app 用 content-desc 而非 text)
    for n in nodes:
        desc = (n.desc or "").lower()
        if "title" in desc or "标题" in (n.desc or ""):
            t = (n.text or (n.desc or "")).strip()
            if len(t) >= 2:
                return t

    # 3) 退化:首个带 text 的非输入区节点
    for n in nodes:
        if n.editable:
            continue
        t = (n.text or "").strip()
        if len(t) >= 2:
            return t

    return None


def is_send_button(node: Node) -> bool:
    """判断节点是否「发送」按钮。

    飞书:通常 resource id 末段含 send / sendButton,text 是「发送」
    微信:resource id 末段含 send_btn,text 是「发送」
    QQ:类似
    """
    rid = (node.viewIdResourceName or "").lower()
    if any(k in rid for k in _SEND_BUTTON_RID_KEYWORDS):
        return True
    label = ((node.text or "") + " " + (node.desc or "")).strip().lower()
    return any(kw.lower() in label for kw in _SEND_BUTTON_TEXT_KEYWORDS)


def match_chat_title(target: str, current: str) -> bool:
    """宽松匹配:target 是 current 的子串,或 current 是 target 的子串,
    或去掉空白后相等(emoji / 标点容忍)。

    Examples:
        target='张三'        current='张三(企业)' -> True(子串)
        target='AI 产品交流群' current='AI 产品交流群🏢' -> True
    """
    if not target or not current:
        return False
    t = target.replace(" ", "").strip()
    c = current.replace(" ", "").strip()
    if not t or not c:
        return False
    return t in c or c in t