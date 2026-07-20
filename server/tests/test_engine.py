from app.decision.engine import DecideInput, DecisionEngine
from app.decision.llm import FakeLLM
from app.decision.skills import BoundSkill, SkillCursor, SkillStep, SkillTemplate
from app.protocol import Node, Perception

TPL = SkillTemplate(
    name="send", app="com.x", keywords=["发"], params=["contact"],
    steps=[
        SkillStep(op="tap", desc="搜索"),
        SkillStep(op="input", input_text="{contact}"),
        SkillStep(op="verify_title", match_text="{contact}"),
        SkillStep(op="tap", text="发送"),
    ],
)


def _frame(title: str) -> Perception:
    return Perception(pkg="com.x", nodeTree=[Node(id="0", text=title, viewIdResourceName="a:id/title")])


def test_verify_title_fail_does_not_advance_cursor_and_falls_to_llm():
    eng = DecisionEngine(llm=FakeLLM(["back"]), cache=None)
    cur = SkillCursor(index=2)
    skill = BoundSkill.bind(TPL, {"contact": "张三"})
    d = eng.decide(DecideInput(goal="g", frame=_frame("其他群"), target_pkg="com.x",
                               cursor=cur, bound_skill=skill, guard={}, title_keywords=("title",)))
    assert d.source == "llm" and cur.index == 2 and cur.state == "failed"


def test_verify_title_pass_returns_read_screen_with_skill_source():
    eng = DecisionEngine(llm=FakeLLM(["done"]), cache=None)
    cur = SkillCursor(index=2)
    skill = BoundSkill.bind(TPL, {"contact": "张三"})
    d = eng.decide(DecideInput(goal="g", frame=_frame("张三"), target_pkg="com.x",
                               cursor=cur, bound_skill=skill, guard={}, title_keywords=("title",)))
    assert d.source == "skill" and d.actions[0].op == "read_screen" and cur.index == 2  # ack 后才推进


def test_decide_never_returns_none_and_llm_empty_falls_to_read_screen():
    eng = DecisionEngine(llm=FakeLLM([""]), cache=None)
    d = eng.decide(DecideInput(goal="g", frame=_frame("x"), target_pkg="",
                               cursor=SkillCursor(), bound_skill=None, guard={}, title_keywords=()))
    assert d.source == "llm" and d.actions[0].op == "read_screen"


def test_failed_skill_is_skipped_next_frame():
    eng = DecisionEngine(llm=FakeLLM(["back", "home"]), cache=None)
    cur = SkillCursor(index=2, state="failed")
    skill = BoundSkill.bind(TPL, {"contact": "张三"})
    d = eng.decide(DecideInput(goal="g", frame=_frame("张三"), target_pkg="com.x",
                               cursor=cur, bound_skill=skill, guard={}, title_keywords=("title",)))
    assert d.source == "llm"
