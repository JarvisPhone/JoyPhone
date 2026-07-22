"""decision.ui_inspect 标题识别测试。

覆盖场景:
  - 优先级 1 命中(rid 含 title_keywords)
  - 优先级 2 命中(desc 含 title/标题)
  - 优先级 3 退化命中(text 非空且非黑名单)
  - 飞书群聊页回归:priority 1 命中 default_center_view_container,
    不退化命中 chat_message_list_view="Ra" 残留(2026-07-23 真机根因)
  - 优先级 3 跳过黑名单(chat msg group / chat_message_list_view 等容器)
"""
from __future__ import annotations

from app.decision.ui_inspect import detect_title, match_title
from app.protocol import Node


_TITLE_KW = ("title_zone", "default_center_view_container", "chat_name", "chat_info_view")


def _node(
    id: str,
    text: str | None = None,
    desc: str | None = None,
    rid: str | None = None,
    editable: bool = False,
) -> Node:
    kwargs: dict[str, object] = {"id": id, "editable": editable}
    if text is not None:
        kwargs["text"] = text
    if desc is not None:
        kwargs["desc"] = desc
    if rid is not None:
        kwargs["viewIdResourceName"] = rid
    return Node(**kwargs)


# ---- 优先级 1:rid 含 title_keywords ----


def test_detect_title_priority1_rid_keyword():
    """rid 命中 title_keywords 的节点 text 作为标题返回。"""
    tree = [_node("a", text="张三", rid="com.app:id/title_zone")]
    assert detect_title(tree, _TITLE_KW) == "张三"


def test_detect_title_priority1_default_center_view_container_feishu_group():
    """飞书群聊页群名节点:rid 含 default_center_view_container。

    2026-07-23 真机根因回归:进群后 default_center_view_container.text="Android AI 开发组"
    不在历史 profile 里,导致 priority 1 不命中、退化命中 chat_message_list_view="Ra",
    INPUT_GUARD 误判还在错的群。
    """
    nodes = [
        _node("0-0-1-0", text="Ra", rid="com.ss.android.lark:id/chat_message_list_view"),
        _node("0-0-1-1", text="1", rid="com.ss.android.lark:id/title_zone"),
        _node("0-0-1-1-2-0", text="Android AI 开发组",
              rid="com.ss.android.lark:id/default_center_view_container"),
        _node("0-0-1-3-0-0", text="发送给 Android AI 开发组",
              rid="com.ss.android.lark:id/kb_rich_text_content", editable=True),
    ]
    assert detect_title(nodes, _TITLE_KW) == "Android AI 开发组"


def test_detect_title_priority1_chat_info_view_redesign_feishu_group_info():
    """飞书群信息页群名节点:rid 含 chat_info_view_redesign(通过 chat_info_view 命中)。"""
    nodes = [
        _node("0-4", text="Android AI 开发组"),
        _node("0-4-0", text="Android AI 开发组",
              rid="com.ss.android.lark:id/chat_info_view_redesign"),
    ]
    assert detect_title(nodes, _TITLE_KW) == "Android AI 开发组"


# ---- 优先级 2:desc 含 title/标题 ----


def test_detect_title_priority2_desc_keyword():
    """desc 含「标题」的节点 text 作为标题返回(部分 app 用 content-desc 而非 rid)。"""
    nodes = [
        _node("t1", text="李四", desc="聊天标题"),
        _node("t2", text="无关"),
    ]
    assert detect_title(nodes, _TITLE_KW) == "李四"


# ---- 优先级 3 退化:跳过黑名单 + editable + 过短 text ----


def test_detect_title_priority3_skip_short_text():
    """text 长度 < 2 跳过。"""
    nodes = [_node("s", text="A")]
    assert detect_title(nodes, _TITLE_KW) is None


def test_detect_title_priority3_skip_editable():
    """editable 节点(输入框)跳过。"""
    nodes = [_node("e", text="发给某人", editable=True)]
    assert detect_title(nodes, _TITLE_KW) is None


def test_detect_title_priority3_skip_chat_message_list_view_residual():
    """飞书 view hierarchy 残留:chat_message_list_view 节点 text="Ra" 不应作为标题。

    退化逻辑必须按 rid 关键词跳过结构性容器节点,避免 view hierarchy 残留
    把上一个会话名误报为当前标题(2026-07-23 真机根因:
    进群后 chat_message_list_view.text="Ra" 被错误地识别为标题,
    INPUT_GUARD 误判还在错的群)。
    """
    nodes = [
        _node("r", text="Ra", rid="com.ss.android.lark:id/chat_message_list_view"),
        _node("s", text="msg_swipe_view", rid="com.ss.android.lark:id/msg_swipe_view"),
        _node("rc", text="round container", rid="com.app:id/round_container"),
    ]
    assert detect_title(nodes, _TITLE_KW) is None


def test_detect_title_priority3_skip_blocklist_rid_substring():
    """rid 含黑名单子串即跳过(黑名单走资源 id,不走 text)。"""
    nodes = [
        _node("a", text="某个可能的标题", rid="com.app:id/wrapper_msg_swipe_view"),
        _node("b", text="真正的标题"),
    ]
    assert detect_title(nodes, _TITLE_KW) == "真正的标题"


def test_detect_title_priority3_keeps_legitimate_short_title():
    """text 黑名单会误伤真实标题(如某 app 群名带"列表"),因此用 rid 黑名单。

    保护性测试:一段 ≥2 字符合法短标题("群名")不被错误过滤。
    """
    nodes = [_node("a", text="群名", rid="com.app:id/group_name_text")]
    assert detect_title(nodes, _TITLE_KW) == "群名"


def test_detect_title_priority3_fallback_first_long_text():
    """黑名单都不命中时,选第一个非 editable 且 text≥2 的节点。"""
    nodes = [
        _node("a", text="x"),                              # 长度 < 2 跳过
        _node("b", text="群名称", editable=False),         # 命中
        _node("c", text="其他"),
    ]
    assert detect_title(nodes, _TITLE_KW) == "群名称"


def test_detect_title_returns_none_when_no_candidate():
    """全部跳过(都是黑名单 rid/输入框/过短)时返回 None。"""
    nodes = [
        _node("a", text="长文本但 rid 在黑名单",
              rid="com.app:id/msg_swipe_view"),  # rid 黑名单跳过
        _node("b", text="input", editable=True),  # editable 跳过
    ]
    assert detect_title(nodes, _TITLE_KW) is None


# ---- 优先级交互:priority 1 命中就不再走 priority 3 ----


def test_detect_title_priority1_does_not_fall_through():
    """priority 1 命中后不再退化,即使 priority 3 有更靠前的非空 text。"""
    nodes = [
        _node("first", text="my_status_bar"),  # 这是 priority 3 候选,但被黑名单跳过也会跳过
        _node("title", text="目标群",
              rid="com.app:id/title_zone"),  # priority 1 命中
    ]
    assert detect_title(nodes, _TITLE_KW) == "目标群"


# ---- match_title(放在这里方便 detect_title 测试一起跑)----


def test_match_title_substring():
    assert match_title("张三", "张三(企业)") is True


def test_match_title_not_match():
    assert match_title("张三", "李四") is False


def test_match_title_empty():
    assert match_title("", "张三") is False
    assert match_title("张三", "") is False
