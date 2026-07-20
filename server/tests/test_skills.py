from app.decision.skills import BoundSkill, CursorState, SkillCursor, SkillStep, SkillTemplate, match_node
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

def test_match_node_by_text_substring():
    nodes = [
        Node(id="n1", text="通讯录联系人", clickable=True),
        Node(id="n2", text="搜索", clickable=True),
    ]
    step = SkillStep(op="tap", text="通讯录")
    assert match_node(step, nodes, 0) is True
    assert match_node(step, nodes, 1) is False

def test_match_node_by_desc_substring():
    nodes = [Node(id="n1", text="", desc="搜索图标", clickable=True)]
    step = SkillStep(op="tap", desc="搜索")
    assert match_node(step, nodes, 0) is True

def test_match_node_by_view_id_substring():
    nodes = [Node(id="n1", text="", viewIdResourceName="com.feishu:id/search_btn")]
    step = SkillStep(op="tap", view_id="search_btn")
    assert match_node(step, nodes, 0) is True

def test_match_node_by_index():
    nodes = [Node(id="n1", text="A"), Node(id="n2", text="B")]
    step = SkillStep(op="tap", index=1)
    assert match_node(step, nodes, 0) is False
    assert match_node(step, nodes, 1) is True

def test_match_node_no_match_returns_false():
    nodes = [Node(id="n1", text="通讯录", desc="联系人", viewIdResourceName="com.x:id/list")]
    step = SkillStep(op="tap", text="发送", desc="搜索", view_id="search", class_name="Button")
    assert match_node(step, nodes, 0) is False

def test_match_node_by_class_name_positive():
    nodes = [Node(id="0", className="android.widget.Button")]
    step = SkillStep(op="tap", class_name="Button")
    assert match_node(step, nodes, 0) is True

def test_match_node_input_editable_rule():
    step = SkillStep(op="input", input_text="x")
    assert match_node(step, [Node(id="0", editable=True)], 0) is True
    assert match_node(step, [Node(id="0", editable=False)], 0) is False
