import json
import uuid

from app.decision import DecisionEngine
from app.llm import FakeLLM
from app.protocol import Node, Perception
from app.skill_cache import SkillCache
from app.skills import SkillLibrary


def _perc(nodes: list[Node]) -> Perception:
    return Perception(nodeTree=nodes, pkg="com.ss.android.lark", activity="Main", ts=1)


def test_skill_hit_without_llm(monkeypatch):
    llm = FakeLLM(['{"op":"back","params":{}}'])

    def _should_not_be_called(system: str, user: str, image_b64: str | None = None) -> str:
        raise AssertionError("LLM should not be called when skill hits")

    monkeypatch.setattr(llm, "complete", _should_not_be_called)
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    p = _perc([Node(id="n1", text="通讯录", clickable=True)])

    action = engine.decide(goal="发消息", perception=p, skill_name="feishu_send", cursor=0, history=[])

    assert action.op == "tap"
    assert action.params == {"match_text": "通讯录"}
    uuid.UUID(action.actionId)


def test_fallback_to_llm_when_skill_miss(monkeypatch):
    llm = FakeLLM(['{"op":"back","params":{}}'])
    captured: dict[str, str] = {}

    def _capture_complete(system: str, user: str, image_b64: str | None = None) -> str:
        captured["system"] = system
        captured["user"] = user
        return '{"op":"back","params":{}}'

    monkeypatch.setattr(llm, "complete", _capture_complete)
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    p = _perc([Node(id="n1", text="首页")])

    action = engine.decide(goal="发消息", perception=p, skill_name="feishu_send", cursor=0, history=[])

    assert action.op == "back"
    assert action.params == {}
    uuid.UUID(action.actionId)
    assert captured["system"] == "decide next UI action"

    payload = json.loads(captured["user"])
    assert set(payload.keys()) == {"goal", "nodes", "history"}
    assert payload["goal"] == "发消息"
    assert payload["history"] == []
    assert payload["nodes"] == [
        {"id": "n1", "text": "首页", "clickable": False, "editable": False}
    ]


def test_cache_hit_returns_step_without_llm(tmp_path, monkeypatch):
    cache = SkillCache(tmp_path / "c.json")
    cache.learn("发消息", "com.ss.android.lark", [{"op": "tap", "params": {"match_text": "搜索"}}])

    llm = FakeLLM(['{"op":"back","params":{}}'])

    def _fail(system: str, user: str, image_b64: str | None = None) -> str:
        raise AssertionError("LLM must not be called on cache hit")

    monkeypatch.setattr(llm, "complete", _fail)
    engine = DecisionEngine(llm=llm, skills=SkillLibrary(), cache=cache)
    p = _perc([Node(id="n1", text="搜索", clickable=True)])

    action = engine.decide(goal="发消息", perception=p, skill_name=None, cursor=0, history=[])

    assert action.op == "tap"
    assert action.params == {"match_text": "搜索"}


def test_cache_miss_when_node_not_matchable_falls_through(tmp_path):
    cache = SkillCache(tmp_path / "c.json")
    cache.learn("发消息", "com.ss.android.lark", [{"op": "tap", "params": {"match_text": "搜索"}}])

    llm = FakeLLM(['{"op":"back","params":{}}'])
    engine = DecisionEngine(llm=llm, skills=SkillLibrary(), cache=cache)
    p = _perc([Node(id="n1", text="首页")])  # 无“搜索”节点，缓存步无法重定位

    action = engine.decide(goal="发消息", perception=p, skill_name=None, cursor=0, history=[])

    assert action.op == "back"  # 回退到 LLM