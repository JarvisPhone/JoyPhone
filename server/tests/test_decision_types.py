from app.decision.types import Decision
from app.decision.ui_inspect import detect_title, match_title
from app.protocol import Action, Node


def test_decision_never_empty_actions():
    d = Decision(actions=[Action(actionId="x", op="read_screen", params={})], source="llm")
    assert d.actions and d.source == "llm"


def test_detect_title_by_rid_keyword():
    nodes = [Node(id="0", text="张三", viewIdResourceName="com.x:id/tv_title")]
    assert detect_title(nodes, ("title",)) == "张三"


def test_detect_title_fallback_first_text():
    nodes = [Node(id="0", text="某群聊", clickable=False), Node(id="1", editable=True, text="输入")]
    assert detect_title(nodes, ()) == "某群聊"


def test_match_title_substring_bidirectional():
    assert match_title("张三", "张三(企业)")
    assert not match_title("张三", "李四")
