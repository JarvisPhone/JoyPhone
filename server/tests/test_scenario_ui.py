"""scenario.ui 等价测试(改写自 test_chat_title_helpers,关键词从 AppProfile 传入)。"""
from app.protocol import Node
from app.scenario.profiles.feishu import FEISHU_PROFILE
from app.scenario.ui import extract_target, is_message_input, is_send_button, match_title


def test_message_input_box_is_message_input():
    """聊天正文输入框:editable=True + desc/text 含输入类词 且不含搜索 -> True。"""
    node = Node(id="e1", desc="发消息", editable=True)
    assert is_message_input(node, FEISHU_PROFILE) is True


def test_message_input_box_by_text_hint():
    node = Node(id="e2", text="输入内容", editable=True)
    assert is_message_input(node, FEISHU_PROFILE) is True


def test_search_box_is_not_message_input():
    """搜索框:含「搜索」词 -> False(避免误伤搜群名场景)。"""
    node = Node(id="s1", desc="搜索", editable=True)
    assert is_message_input(node, FEISHU_PROFILE) is False


def test_search_box_english_hint_is_not_message_input():
    node = Node(id="s2", desc="Search users", editable=True)
    assert is_message_input(node, FEISHU_PROFILE) is False


def test_non_editable_node_is_not_message_input():
    """非编辑框(editable=False) -> False。"""
    node = Node(id="t1", text="发消息", editable=False)
    assert is_message_input(node, FEISHU_PROFILE) is False


def test_message_input_english_hint():
    node = Node(id="e3", desc="Send a message", editable=True)
    assert is_message_input(node, FEISHU_PROFILE) is True


def test_send_button_by_rid():
    node = Node(id="b1", viewIdResourceName="com.ss.android.lark:id/btn_send")
    assert is_send_button(node, FEISHU_PROFILE) is True


def test_send_button_rid_with_send_substring_is_not_send_button():
    """rid 含 send 子串(如 message_sender_avatar)但非发送按钮 rid 模式 -> False。

    回归:rid/text 关键词必须分流,rid 只匹配 rid 关键词,
    text 关键词("send"/"sending")不得拿去匹配 rid。
    """
    node = Node(id="b4", viewIdResourceName="com.x:id/message_sender_avatar")
    assert is_send_button(node, FEISHU_PROFILE) is False


def test_send_button_text_keyword_does_not_match_rid():
    """text 关键词只匹配 label:rid 含 "sending" 但 label 无发送词 -> False。"""
    node = Node(id="b5", viewIdResourceName="com.x:id/sending_progress", text="进度")
    assert is_send_button(node, FEISHU_PROFILE) is False


def test_send_button_by_text():
    node = Node(id="b2", text="发送")
    assert is_send_button(node, FEISHU_PROFILE) is True


def test_non_send_button():
    node = Node(id="b3", text="取消")
    assert is_send_button(node, FEISHU_PROFILE) is False


def test_extract_target_quoted():
    assert extract_target("给“张三”发消息") == "张三"
    assert extract_target("给「AI 产品交流群」发个通知") == "AI 产品交流群"


def test_extract_target_structural():
    assert extract_target("给张三发消息") == "张三"
    assert extract_target("搜索测试群") == "测试"
    assert extract_target("给测试群发一条消息") == "测试"
    assert extract_target("找李四好友") == "李四"


def test_extract_target_none():
    assert extract_target("截个屏") is None
    assert extract_target("") is None


def test_match_title_reexport():
    """scenario.ui re-export decision.ui_inspect.match_title 供场景层使用。"""
    assert match_title("张三", "张三(企业)") is True
    assert match_title("张三", "李四") is False
