"""App 内页型检测。

`Scene`(launcher/systemui/app/lock 等)是「顶层在哪」,粒度太粗——LLM 拿到
`scene=app` 时仍然不知道自己在飞书的消息列表还是聊天页,这是「进了二级
页面就出不来」的根因。

`AppPage` 是「app 内的页面层级」,在 pkg 是第三方 app 时进一步归类:
  - INBOX_LIST:     通讯录 / 消息列表(有输入框 + 列表,无消息气泡)
  - CHAT:           会话页(有消息气泡 + 输入框 + 发送按钮)
  - CONTACT_INFO:   联系人详情页(无输入框,有「发消息」/菜单)
  - GROUP_INFO:     群详情页(无输入框,有多人头像 + 群设置菜单)
  - SETTINGS:       设置页(有开关/菜单项列表,无输入框)
  - SEARCH:         搜索结果页(输入框有文字 + 结果列表)
  - UNKNOWN:        无法识别

页型检测是「纯描述」,不带策略——退出路径由 ExitHint 模板给出,
LoopGuard 的退阱兜底由 policies 负责。本模块只输出 page。

约定:detect_app_page 只在 scene == IN_APP 时调用;其它场景(launcher、
systemui、lock)走 Scene 即可。
"""
from __future__ import annotations

import logging
from enum import Enum

from app.decision.pkg_guard import Scene, detect_scene
from app.protocol import Node, Perception

_logger = logging.getLogger("phoneagent.app_page")


class AppPage(str, Enum):
    INBOX_LIST = "inbox_list"
    CHAT = "chat"
    CONTACT_INFO = "contact_info"
    GROUP_INFO = "group_info"
    SETTINGS = "settings"
    SEARCH = "search"
    UNKNOWN = "unknown"


# --- 启发式特征(纯文本/desc/rid 信号,不绑具体 app,跨 app 通用)----

# 发送按钮的常见 rid 关键词(飞书/微信/Telegram 等的命名习惯收敛)
_SEND_BUTTON_RIDS = frozenset({
    "send_button", "btn_send", "iv_send", "send_btn", "send",
    "send_message_button", "send_icon", "iv_send_msg",
})

# 消息气泡容器(聊天页特征;飞书 chat_message_list_view)
_CHAT_BUBBLE_RIDS = frozenset({
    "chat_message_list_view", "message_list", "msg_list", "chat_list",
    "recyclerview_chat", "chat_content",
})

# 设置页常见关键词
_SETTINGS_KEYWORDS = (
    "设置", "Settings", "通用设置", "Preferences", "Account", "账户设置",
    "通知设置", "隐私设置", "关于", "About",
)

# 联系人详情页常见按钮
_CONTACT_INFO_RIDS = frozenset({
    "btn_send_message", "send_msg_btn", "btn_chat", "iv_start_chat",
})

# 群详情页常见关键词
_GROUP_INFO_KEYWORDS = (
    "群成员", "群聊成员", "群设置", "Group members", "Group info",
    "Members", "群公告",
)


def _nodes_text(nodes: list[Node]) -> str:
    return " ".join(
        ((n.text or "") + " " + (n.desc or "")).strip()
        for n in nodes if (n.text or n.desc)
    )


def _has_text_anywhere(nodes: list[Node], *needles: str) -> bool:
    txt = _nodes_text(nodes)
    return any(n in txt for n in needles)


def _has_input(nodes: list[Node]) -> bool:
    return any(n.editable for n in nodes)


def _has_input_with_text(nodes: list[Node]) -> bool:
    return any(n.editable and (n.text or "").strip() for n in nodes)


def _has_send_button(nodes: list[Node]) -> bool:
    for n in nodes:
        if not n.clickable:
            continue
        rid_tail = (n.viewIdResourceName or "").rsplit("/", 1)[-1].lower()
        text = (n.text or "").strip()
        if any(k in rid_tail for k in _SEND_BUTTON_RIDS):
            return True
        if text in ("发送", "Send", "send"):
            return True
    return False


def _has_chat_bubbles(nodes: list[Node]) -> bool:
    for n in nodes:
        rid_tail = (n.viewIdResourceName or "").rsplit("/", 1)[-1].lower()
        if any(k in rid_tail for k in _CHAT_BUBBLE_RIDS):
            return True
        # 退化:有大量 clickable list_item 但不是「搜索结果列表」时,
        # 可能是消息列表——这里保守不依赖,交给 chat_bubble_rid 命中即可
    return False


def _has_settings_signature(nodes: list[Node]) -> bool:
    return _has_text_anywhere(nodes, *_SETTINGS_KEYWORDS)


def _has_contact_info_signature(nodes: list[Node]) -> bool:
    for n in nodes:
        rid_tail = (n.viewIdResourceName or "").rsplit("/", 1)[-1].lower()
        if any(k in rid_tail for k in _CONTACT_INFO_RIDS):
            return True
    text = _nodes_text(nodes)
    return "发消息" in text or "音视频通话" in text or "视频通话" in text


def _has_group_info_signature(nodes: list[Node]) -> bool:
    text = _nodes_text(nodes)
    return any(k in text for k in _GROUP_INFO_KEYWORDS)


def detect_app_page(perception: Perception) -> AppPage:
    """检测当前 app 内的页型。

    只在 scene == IN_APP 时调用;其它 scene 一律返回 UNKNOWN
    (launcher / systemui 不属于「app 内页型」语义)。
    """
    if detect_scene(perception) != Scene.IN_APP:
        return AppPage.UNKNOWN

    nodes = perception.nodeTree or []
    if not nodes:
        return AppPage.UNKNOWN

    has_input = _has_input(nodes)
    input_with_text = _has_input_with_text(nodes)
    has_send = _has_send_button(nodes)
    has_bubbles = _has_chat_bubbles(nodes)

    # 1. CHAT: 有输入框 + 发送按钮 + 消息列表
    if has_input and has_send and has_bubbles:
        return AppPage.CHAT

    # 2. SEARCH: 输入框已有文字 + 无发送按钮(典型搜索结果页)
    if input_with_text and not has_send:
        return AppPage.SEARCH

    # 3. GROUP_INFO: 群特征关键词(无输入框)
    if not has_input and _has_group_info_signature(nodes):
        return AppPage.GROUP_INFO

    # 4. CONTACT_INFO: 联系人特征按钮(无输入框)
    if not has_input and _has_contact_info_signature(nodes):
        return AppPage.CONTACT_INFO

    # 5. SETTINGS: 设置关键词(无输入框)
    if not has_input and _has_settings_signature(nodes):
        return AppPage.SETTINGS

    # 6. INBOX_LIST: 有搜索输入框 + 列表(无消息气泡/无发送按钮)
    if has_input and not has_send and not has_bubbles:
        return AppPage.INBOX_LIST

    return AppPage.UNKNOWN