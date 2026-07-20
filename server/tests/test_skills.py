from app.decision.skills import BoundSkill, CursorState, SkillCursor, SkillStep, SkillTemplate
from app.protocol import Node

TPL = SkillTemplate(
    name="send", app="com.x", keywords=["发"], params=["contact"],
    steps=[
        SkillStep(op="tap", desc="搜索"),
        SkillStep(op="input", input_text="{contact}"),
        SkillStep(op="verify_title", match_text="{contact}"),
        SkillStep(op="tap", text="发送"),
    ],
)

def test_bind_substitutes_placeholders():
    s = BoundSkill.bind(TPL, {"contact": "张三"})
    assert s is not None
    step = s.next_step([Node(id="0", editable=True)], 1)
    assert step["input_text"] == "张三"

def test_bind_missing_param_returns_none():
    assert BoundSkill.bind(TPL, {}) is None

def test_cursor_advance_and_fail():
    c = SkillCursor()
    c.advance(); assert c.index == 1 and c.state == "pending"
    c.fail(); assert c.state == "failed"

def test_next_step_out_of_range_returns_none():
    s = BoundSkill.bind(TPL, {"contact": "张三"})
    assert s.next_step([], 99) is None

def test_verify_title_step_returns_expected_title():
    s = BoundSkill.bind(TPL, {"contact": "张三"})
    step = s.next_step([], 2)
    assert step == {"op": "verify_title", "expected_title": "张三"}
