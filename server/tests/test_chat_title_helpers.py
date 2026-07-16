from app.chat_title_helpers import is_message_input
from app.protocol import Node


def test_message_input_box_is_message_input():
    """聊天正文输入框:editable=True + desc/text 含输入类词 且不含搜索 -> True。"""
    node = Node(id="e1", desc="发消息", editable=True)
    assert is_message_input(node) is True


def test_message_input_box_by_text_hint():
    node = Node(id="e2", text="输入内容", editable=True)
    assert is_message_input(node) is True


def test_search_box_is_not_message_input():
    """搜索框:含「搜索」词 -> False(避免误伤搜群名场景)。"""
    node = Node(id="s1", desc="搜索", editable=True)
    assert is_message_input(node) is False


def test_search_box_english_hint_is_not_message_input():
    node = Node(id="s2", desc="Search users", editable=True)
    assert is_message_input(node) is False


def test_non_editable_node_is_not_message_input():
    """非编辑框(editable=False) -> False。"""
    node = Node(id="t1", text="发消息", editable=False)
    assert is_message_input(node) is False


def test_message_input_english_hint():
    node = Node(id="e3", desc="Send a message", editable=True)
    assert is_message_input(node) is True