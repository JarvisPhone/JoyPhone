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

    # 系统提示词必须约束 LLM 扮演决策器、列出合法 op、强制 JSON-only 输出，
    # 否则真实模型会返回自然语言导致 json.loads 崩溃（真机联调实测暴露）。
    system = captured["system"]
    assert "JSON" in system
    for op in ("tap", "input", "swipe", "done", "abort", "read_screen"):
        assert op in system

    payload = json.loads(captured["user"])
    assert set(payload.keys()) == {"goal", "screen", "history"}
    assert payload["goal"] == "发消息"
    assert payload["history"] == []
    assert payload["screen"] == '[0] text "首页"'


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


def test_llm_non_json_falls_back_to_read_screen(monkeypatch):
    # 真机联调实测：真实 LLM 可能返回自然语言/空串，json.loads 会崩溃并断连。
    # 决策层必须兜底为 read_screen（重新观察），保证 WS 循环不中断。
    llm = FakeLLM(["这不是 JSON，我需要更多信息"])
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    p = _perc([Node(id="n1", text="首页")])

    action = engine.decide(goal="发消息", perception=p, skill_name=None, cursor=0, history=[])

    assert action.op == "read_screen"
    assert action.params == {}
    uuid.UUID(action.actionId)


def test_llm_empty_string_falls_back_to_read_screen():
    llm = FakeLLM([""])
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    p = _perc([Node(id="n1", text="首页")])

    action = engine.decide(goal="发消息", perception=p, skill_name=None, cursor=0, history=[])

    assert action.op == "read_screen"


from app.decision import _encode_nodes


def test_encode_nodes_formats_numbered_lines():
    nodes = [
        Node(id="a", text="首页", clickable=True),
        Node(id="b", text="搜索", editable=True),
        Node(id="c", desc="微博", clickable=True),
        Node(id="d", text="正文"),
    ]
    out = _encode_nodes(nodes)
    assert out == '[0] button "首页"\n[1] input "搜索"\n[2] button "微博"\n[3] text "正文"'


def test_encode_nodes_empty_is_empty_string():
    assert _encode_nodes([]) == ""


def test_encode_nodes_blank_text_and_desc_keeps_empty_quotes():
    nodes = [Node(id="x", clickable=True)]
    assert _encode_nodes(nodes) == '[0] button ""'


def test_large_node_tree_capped_and_encoded(monkeypatch):
    captured = {}
    llm = FakeLLM(['{"op":"back","params":{}}'])

    def _capture(system, user, image_b64=None):
        captured["user"] = user
        return '{"op":"back","params":{}}'

    monkeypatch.setattr(llm, "complete", _capture)
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    nodes = [Node(id=f"n{i}", text=f"item{i}") for i in range(3000)]
    engine.decide(goal="发消息", perception=_perc(nodes), skill_name=None, cursor=0, history=[])

    payload = json.loads(captured["user"])
    assert "screen" in payload and "nodes" not in payload
    line_count = len(payload["screen"].splitlines())
    assert line_count <= DecisionEngine.MAX_LLM_NODES


def test_capping_prefers_interactive_nodes(monkeypatch):
    captured = {}
    llm = FakeLLM(['{"op":"back","params":{}}'])

    def _capture(system, user, image_b64=None):
        captured["user"] = user
        return '{"op":"back","params":{}}'

    monkeypatch.setattr(llm, "complete", _capture)
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    nodes = [Node(id=f"t{i}", text=f"text{i}") for i in range(3000)]
    nodes.append(Node(id="target", text="飞书", clickable=True))
    engine.decide(goal="打开飞书", perception=_perc(nodes), skill_name=None, cursor=0, history=[])

    payload = json.loads(captured["user"])
    assert '飞书' in payload["screen"]