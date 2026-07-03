from app.protocol import Node
from app.skills import SkillLibrary


def test_match_feishu_send_skill_when_contacts_visible():
    nodes = [Node(id="n1", text="通讯录")]

    step = SkillLibrary.next_step("feishu_send", nodes, 0)

    assert step == {"match_text": "通讯录", "op": "tap"}


def test_return_none_when_screen_not_match():
    nodes = [Node(id="n1", text="消息")]

    step = SkillLibrary.next_step("feishu_send", nodes, 1)

    assert step is None


def test_unknown_skill_returns_none():
    nodes = [Node(id="n1", text="通讯录")]

    step = SkillLibrary.next_step("unknown_skill", nodes, 0)

    assert step is None