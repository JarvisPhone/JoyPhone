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


# ---- tap 坐标下发：云侧把 LLM 选中节点解析为 bounds 中心坐标 ----
# 真机根因：LLM 发 tap id='26' 本可精确点中桌面飞书图标，但端侧只认 match_text，
# 导致空点 + 全屏子串匹配误命中负一屏推荐磁贴进小红书。修复方案：云侧在 decide 出口
# 把 tap 的 id/match_text 还原为选中 Node 的 bounds 中心坐标 (x,y) 下发，端侧按坐标点击。


def test_tap_by_id_resolves_to_bounds_center(monkeypatch):
    llm = FakeLLM(['{"op":"tap","params":{"id":"1"}}'])
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    nodes = [
        Node(id="a", text="微信", clickable=True, bounds=(0, 0, 100, 100)),
        Node(id="b", text="飞书", clickable=True, bounds=(200, 300, 400, 500)),
    ]
    action = engine.decide(goal="打开飞书", perception=_perc(nodes), skill_name=None, cursor=0, history=[])

    assert action.op == "tap"
    # 选中 nodes[1] "飞书" bounds=(200,300,400,500) -> 中心 (300, 400)
    assert action.params["x"] == "300"
    assert action.params["y"] == "400"


def test_tap_only_resolves_by_id_not_match_text(monkeypatch):
    # 节点引用键只认 [n] 下标(id)；match_text 不再参与 tap 解析。
    # params 只给 match_text 时无法命中,不注入坐标,保留原 params。
    llm = FakeLLM(['{"op":"tap","params":{"match_text":"飞书"}}'])
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    nodes = [
        Node(id="a", text="微信", clickable=True, bounds=(0, 0, 100, 100)),
        Node(id="b", text="飞书", clickable=True, bounds=(200, 300, 400, 500)),
    ]
    action = engine.decide(goal="打开飞书", perception=_perc(nodes), skill_name=None, cursor=0, history=[])

    assert action.op == "tap"
    assert "x" not in action.params
    assert "y" not in action.params
    assert action.params.get("match_text") == "飞书"


def test_tap_by_id_out_of_range_keeps_original(monkeypatch):
    # id 越界 -> 解析失败,不注入坐标,保留原 params。
    llm = FakeLLM(['{"op":"tap","params":{"id":"99"}}'])
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    nodes = [Node(id="a", text="飞书", clickable=True, bounds=(200, 300, 400, 500))]
    action = engine.decide(goal="打开飞书", perception=_perc(nodes), skill_name=None, cursor=0, history=[])

    assert action.op == "tap"
    assert "x" not in action.params
    assert "y" not in action.params
    assert action.params.get("id") == "99"


def test_tap_by_id_node_without_bounds_keeps_original(monkeypatch):
    # id 命中但该 node 无 bounds -> 不注入坐标,保留原 params。
    llm = FakeLLM(['{"op":"tap","params":{"id":"0"}}'])
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    nodes = [Node(id="a", text="飞书", clickable=True, bounds=None)]
    action = engine.decide(goal="打开飞书", perception=_perc(nodes), skill_name=None, cursor=0, history=[])

    assert action.op == "tap"
    assert "x" not in action.params
    assert "y" not in action.params
    assert action.params.get("id") == "0"


def test_tap_unresolvable_keeps_original_params(monkeypatch):
    # 选中节点找不到或无 bounds -> 不注入坐标，保留原 params 供端侧兜底
    llm = FakeLLM(['{"op":"tap","params":{"match_text":"不存在"}}'])
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    nodes = [Node(id="a", text="飞书", clickable=True, bounds=(0, 0, 10, 10))]
    action = engine.decide(goal="打开飞书", perception=_perc(nodes), skill_name=None, cursor=0, history=[])

    assert "x" not in action.params
    assert "y" not in action.params
    assert action.params.get("match_text") == "不存在"


def test_system_prompt_teaches_minus_one_screen_exit():
    # 负一屏(小布建议/推荐磁贴)不是桌面，�点会进错 app。
    # prompt 必须告诉 LLM 识别负一屏特征并向右滑动退出。
    from app.decision import _SYSTEM_PROMPT

    assert "负一屏" in _SYSTEM_PROMPT
    assert "小布建议" in _SYSTEM_PROMPT
    assert "right" in _SYSTEM_PROMPT


# ---- parse_actions: 纯文本指令解析纯函数 ----
from app.decision import parse_actions


def test_parse_actions_tap():
    assert parse_actions("tap 3") == [{"op": "tap", "id": "3"}]


def test_parse_actions_input_keeps_inner_spaces():
    assert parse_actions("input 5 你好 世界 abc") == [
        {"op": "input", "id": "5", "text": "你好 世界 abc"}
    ]


def test_parse_actions_swipe():
    assert parse_actions("swipe up") == [{"op": "swipe", "direction": "up"}]


def test_parse_actions_noarg_ops():
    assert parse_actions("back") == [{"op": "back"}]
    assert parse_actions("home") == [{"op": "home"}]


def test_parse_actions_alias_mapping():
    assert parse_actions("home_first") == [{"op": "home_first_page"}]
    assert parse_actions("read") == [{"op": "read_screen"}]


def test_parse_actions_wait():
    assert parse_actions("wait 500") == [{"op": "wait", "ms": "500"}]


def test_parse_actions_abort_reason_takes_rest():
    assert parse_actions("abort 未找到应用 飞书") == [
        {"op": "abort", "reason": "未找到应用 飞书"}
    ]


def test_parse_actions_skips_blank_and_unknown_lines():
    text = "\n\ntap 1\n   \nfoobar xyz\nhome\n"
    assert parse_actions(text) == [{"op": "tap", "id": "1"}, {"op": "home"}]


def test_parse_actions_multi_line_preserves_order():
    text = "home_first\nread\ntap 2\ninput 4 hi there\nswipe left\ndone"
    assert parse_actions(text) == [
        {"op": "home_first_page"},
        {"op": "read_screen"},
        {"op": "tap", "id": "2"},
        {"op": "input", "id": "4", "text": "hi there"},
        {"op": "swipe", "direction": "left"},
        {"op": "done"},
    ]