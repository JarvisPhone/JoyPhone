import json

from app.protocol import Action, Perception
from app.decision import DecisionEngine


class DummySkills:
    def __init__(self, step):
        self.step = step

    def next_step(self, goal, perception, skill_name, cursor, history):
        return self.step


class DummyLLM:
    def __init__(self, response):
        self.response = response
        self.called = False
        self.last_request = None

    def complete(self, system, user):
        self.called = True
        self.last_request = {"system": system, "user": user}
        return json.dumps(self.response, ensure_ascii=False)


def make_perception() -> Perception:
    return Perception(
        nodeTree=[{"id": "n1", "text": "通讯录", "clickable": True}],
        pkg="com.ss.android.lark",
        activity="MainActivity",
        ts=1,
    )


def test_skill_hit_returns_tap_without_llm():
    llm = DummyLLM({"op": "back", "params": {}})
    skills = DummySkills({"op": "tap", "match_text": "通讯录"})
    engine = DecisionEngine(llm=llm, skills=skills)

    action = engine.decide(
        goal="打开通讯录",
        perception=make_perception(),
        skill_name="contacts",
        cursor=0,
        history=[],
    )

    assert isinstance(action, Action)
    assert action.op == "tap"
    assert action.params == {"match_text": "通讯录"}
    assert llm.called is False


def test_skill_miss_fallback_llm_returns_back():
    llm = DummyLLM({"op": "back", "params": {}})
    skills = DummySkills(None)
    engine = DecisionEngine(llm=llm, skills=skills)

    action = engine.decide("返回", make_perception(), "contacts", 0, [])

    assert isinstance(action, Action)
    assert action.op == "back"
    assert action.params == {}
    assert llm.called is True
    assert llm.last_request["system"] == "decide next UI action"