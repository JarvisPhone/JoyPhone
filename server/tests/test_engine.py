from app.decision.engine import DecideInput, DecisionEngine, _encode_nodes, parse_actions
from app.decision.llm import FakeLLM
from app.decision.pkg_guard import SceneConfig
from app.decision.skills import BoundSkill, SkillCursor, SkillStep, SkillTemplate
from app.infra.config import Config
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


def _llm_decide(eng, nodes, pkg="com.x", target_pkg="", guard=None):
    frame = Perception(pkg=pkg, nodeTree=nodes, activity="Main", ts=1)
    return eng.decide(DecideInput(goal="g", frame=frame, target_pkg=target_pkg,
                                  cursor=SkillCursor(), bound_skill=None,
                                  guard=guard if guard is not None else {},
                                  title_keywords=()))


# ---- parse_actions: 纯文本指令解析 ----

def test_parse_actions_tap():
    assert parse_actions("tap 3") == [{"op": "tap", "id": "3"}]


def test_parse_actions_input_keeps_inner_spaces():
    assert parse_actions("input 5 你好 世界 abc") == [
        {"op": "input", "id": "5", "text": "你好 世界 abc"}
    ]


def test_parse_actions_swipe():
    assert parse_actions("swipe up") == [{"op": "swipe", "direction": "up"}]


def test_parse_actions_wait():
    assert parse_actions("wait 500") == [{"op": "wait", "ms": "500"}]


def test_parse_actions_noarg_ops():
    assert parse_actions("back") == [{"op": "back"}]
    assert parse_actions("home") == [{"op": "home"}]
    assert parse_actions("done") == [{"op": "done"}]


def test_parse_actions_read_alias():
    assert parse_actions("read") == [{"op": "read_screen"}]


def test_parse_actions_abort_reason_takes_rest():
    assert parse_actions("abort 未找到应用 飞书") == [
        {"op": "abort", "reason": "未找到应用 飞书"}
    ]


def test_parse_actions_skips_blank_and_unknown_lines():
    text = "\n\ntap 1\n   \nfoobar xyz\nhome\n"
    assert parse_actions(text) == [{"op": "tap", "id": "1"}, {"op": "home"}]


def test_parse_actions_multi_line_preserves_order():
    text = "swipe left\nread\ntap 2\ninput 4 hi there\nswipe left\ndone"
    assert parse_actions(text) == [
        {"op": "swipe", "direction": "left"},
        {"op": "read_screen"},
        {"op": "tap", "id": "2"},
        {"op": "input", "id": "4", "text": "hi there"},
        {"op": "swipe", "direction": "left"},
        {"op": "done"},
    ]


# ---- _encode_nodes: 类型标注 ----

def test_encode_nodes_type_annotation():
    nodes = [
        Node(id="a", text="首页", clickable=True),
        Node(id="b", text="搜索", editable=True),
        Node(id="c", desc="微博", clickable=True),
        Node(id="d", text="正文"),
    ]
    assert _encode_nodes(nodes) == (
        '[0] button "首页"\n[1] input "搜索"\n[2] button "微博"\n[3] text "正文"'
    )


def test_encode_nodes_empty_and_blank_label():
    assert _encode_nodes([]) == ""
    assert _encode_nodes([Node(id="x", clickable=True)]) == '[0] button ""'


# ---- _cap_nodes: 可交互节点优先保留 ----

def test_cap_nodes_under_threshold_returns_all():
    eng = DecisionEngine(llm=FakeLLM(["back"]), cache=None)
    nodes = [Node(id=f"n{i}", text=f"t{i}") for i in range(10)]
    assert eng._cap_nodes(nodes) == nodes


def test_cap_nodes_over_threshold_prefers_interactive():
    eng = DecisionEngine(llm=FakeLLM(["back"]), cache=None)
    nodes = [Node(id=f"t{i}", text=f"text{i}") for i in range(300)]
    target = Node(id="target", text="飞书", clickable=True)
    nodes.append(target)
    capped = eng._cap_nodes(nodes)
    assert len(capped) == eng.MAX_LLM_NODES
    assert target in capped


# ---- tap/input 坐标注入 ----

def test_tap_by_id_injects_bounds_center():
    eng = DecisionEngine(llm=FakeLLM(["tap 1"]), cache=None)
    nodes = [
        Node(id="a", text="微信", clickable=True, bounds=(0, 0, 100, 100)),
        Node(id="b", text="飞书", clickable=True, bounds=(200, 300, 400, 500)),
    ]
    d = _llm_decide(eng, nodes)
    action = d.actions[-1]
    assert action.op == "tap"
    assert action.params["x"] == "300"
    assert action.params["y"] == "400"


def test_input_by_id_injects_bounds_center():
    eng = DecisionEngine(llm=FakeLLM(["input 0 你好"]), cache=None)
    nodes = [Node(id="a", text="搜索框", editable=True, bounds=(0, 0, 100, 100))]
    d = _llm_decide(eng, nodes)
    action = d.actions[0]
    assert action.op == "input"
    assert action.params["text"] == "你好"
    assert action.params["x"] == "50"
    assert action.params["y"] == "50"


def test_tap_out_of_range_id_no_coords():
    eng = DecisionEngine(llm=FakeLLM(["tap 99"]), cache=None)
    nodes = [Node(id="a", text="飞书", clickable=True, bounds=(200, 300, 400, 500))]
    action = _llm_decide(eng, nodes).actions[-1]
    assert action.op == "tap"
    assert "x" not in action.params and "y" not in action.params
    assert action.params.get("id") == "99"


def test_tap_non_int_id_no_coords():
    eng = DecisionEngine(llm=FakeLLM(["tap abc"]), cache=None)
    nodes = [Node(id="a", text="飞书", clickable=True, bounds=(0, 0, 10, 10))]
    action = _llm_decide(eng, nodes).actions[-1]
    assert "x" not in action.params and "y" not in action.params


def test_tap_empty_id_no_coords():
    eng = DecisionEngine(llm=FakeLLM(["tap"]), cache=None)
    nodes = [Node(id="a", text="飞书", clickable=True, bounds=(0, 0, 10, 10))]
    action = _llm_decide(eng, nodes).actions[-1]
    assert "x" not in action.params and "y" not in action.params


def test_tap_node_without_bounds_no_coords():
    eng = DecisionEngine(llm=FakeLLM(["tap 0"]), cache=None)
    nodes = [Node(id="a", text="飞书", clickable=True, bounds=None)]
    action = _llm_decide(eng, nodes).actions[-1]
    assert "x" not in action.params and "y" not in action.params
    assert action.params.get("id") == "0"


# ---- pkg_guard 三级脱困阶梯 ----

def _stuck_frame() -> Perception:
    return Perception(pkg="com.tencent.mm", activity="X", ts=1,
                      nodeTree=[Node(id="n1", text="未知界面")])


def _guard_engine(escape_response: str):
    main = FakeLLM(["back"])
    escape = FakeLLM([escape_response])
    return DecisionEngine(llm=main, cache=None, escape_llm=escape), main, escape


def _guard_decide(eng, guard):
    return eng.decide(DecideInput(goal="打开飞书", frame=_stuck_frame(),
                                  target_pkg="com.ss.android.lark",
                                  cursor=SkillCursor(), bound_skill=None,
                                  guard=guard, title_keywords=()))


def test_pkg_guard_stall_escalates_to_llm_level1(monkeypatch):
    eng, main, escape = _guard_engine("target_scene: HOME")
    monkeypatch.setattr(main, "complete",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("主 LLM 不应被调用")))
    calls = {"n": 0}
    orig = escape.complete

    def _counting(*a, **k):
        calls["n"] += 1
        return orig(*a, **k)

    monkeypatch.setattr(escape, "complete", _counting)
    guard: dict = {}
    # 同 scene 反复出现,第 STALL_THRESHOLD 帧即触发停滞/振荡 -> LLM 脱困
    for _ in range(SceneConfig.STALL_THRESHOLD):
        d = _guard_decide(eng, guard)
    assert calls["n"] >= 1
    assert guard["escalation_level"] == 1
    assert d.source == "pkg_guard"


def test_pkg_guard_level2_mechanical_fallback(monkeypatch):
    eng, main, escape = _guard_engine("target_scene: HOME")
    monkeypatch.setattr(main, "complete",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("主 LLM 不应被调用")))
    guard: dict = {}
    for _ in range(SceneConfig.STALL_THRESHOLD + 1):
        d = _guard_decide(eng, guard)
    assert guard["escalation_level"] == 2
    assert d.source == "pkg_guard"
    # IN_APP 的 fallback 动作是 home
    assert d.actions[0].op == "home"


def test_pkg_guard_level2_exhausted_aborts(monkeypatch):
    eng, main, escape = _guard_engine("target_scene: HOME")
    monkeypatch.setattr(main, "complete",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("主 LLM 不应被调用")))
    guard: dict = {}
    for _ in range(SceneConfig.STALL_THRESHOLD + 2):
        d = _guard_decide(eng, guard)
    assert d.actions[0].op == "abort"
    assert d.actions[0].params["reason"].startswith("pkg_guard_stuck")


# ---- cache 回放:上下文/禁用/占位符/锚点 ----

from app.decision.cache import SkillCache


def _active_cache(tmp_path, goal="g", context="com.x|unknown", steps=None):
    cache = SkillCache(tmp_path / "c.json")
    key = "%s|%s" % (goal, context)
    cache._data[key] = {
        "key": key, "status": "active",
        "steps": steps or [{"op": "tap", "params": {"match_text": "发送"}}],
        "count": 3, "hits": 0, "created_ts": 0, "updated_ts": 0,
    }
    cache._flush()
    return cache


def _cache_decide(eng, pkg="com.x", text="发送", desc=None, **kw):
    nodes = [Node(id="n", text=text, desc=desc)]
    frame = Perception(pkg=pkg, nodeTree=nodes)
    return eng.decide(DecideInput(
        goal="g", frame=frame, target_pkg=pkg, cursor=SkillCursor(),
        bound_skill=None, guard={}, title_keywords=(), **kw,
    ))


def test_cache_hit_uses_cache_context(tmp_path):
    cache = _active_cache(tmp_path)
    eng = DecisionEngine(llm=FakeLLM(["read"]), cache=cache)
    d = _cache_decide(eng, cache_context="com.x|unknown")
    assert d.source == "cache" and d.actions[0].op == "tap"


def test_cache_disabled_skips_replay(tmp_path):
    cache = _active_cache(tmp_path)
    eng = DecisionEngine(llm=FakeLLM(["read"]), cache=cache)
    d = _cache_decide(eng, cache_context="com.x|unknown", cache_disabled=True)
    assert d.source != "cache"


def test_cache_binds_placeholders(tmp_path):
    cache = _active_cache(
        tmp_path,
        steps=[{"op": "input", "params": {"text": "{contact}"}}],
    )
    eng = DecisionEngine(llm=FakeLLM(["read"]), cache=cache)
    d = _cache_decide(eng, cache_context="com.x|unknown", bindings={"contact": "张三"})
    assert d.source == "cache" and d.actions[0].params["text"] == "张三"


def test_cache_unbound_placeholder_skips(tmp_path):
    cache = _active_cache(
        tmp_path,
        steps=[{"op": "input", "params": {"text": "{contact}"}}],
    )
    eng = DecisionEngine(llm=FakeLLM(["read"]), cache=cache)
    d = _cache_decide(eng, cache_context="com.x|unknown", bindings={})
    assert d.source != "cache"


def test_cache_relocates_anchor_by_desc(tmp_path):
    cache = _active_cache(tmp_path)
    eng = DecisionEngine(llm=FakeLLM(["read"]), cache=cache)
    d = _cache_decide(eng, text=None, desc="发送", cache_context="com.x|unknown")
    assert d.source == "cache"


def test_cache_miss_when_anchor_not_on_screen(tmp_path):
    cache = _active_cache(tmp_path)
    eng = DecisionEngine(llm=FakeLLM(["read"]), cache=cache)
    d = _cache_decide(eng, text="别的", cache_context="com.x|unknown")
    assert d.source != "cache"


# ---- skill 无匹配熔断 ----


def test_skill_disabled_after_max_misses():
    eng = DecisionEngine(llm=FakeLLM(["read"] * 10), cache=None)
    skill = BoundSkill.bind(TPL, {"contact": "张三"})
    cur = SkillCursor(index=0)
    frame = Perception(pkg="com.x", nodeTree=[Node(id="n", text="无关页面")])
    for _ in range(Config.SKILL_MAX_MISSES):
        eng.decide(DecideInput(goal="g", frame=frame, target_pkg="com.x",
                               cursor=cur, bound_skill=skill, guard={}, title_keywords=()))
    assert cur.misses == Config.SKILL_MAX_MISSES
    # 再 decide:skill 已被跳过,misses 不再增长
    eng.decide(DecideInput(goal="g", frame=frame, target_pkg="com.x",
                           cursor=cur, bound_skill=skill, guard={}, title_keywords=()))
    assert cur.misses == Config.SKILL_MAX_MISSES


# ---- LLM tap/input 语义锚点注入 ----


def test_llm_tap_injects_match_text_anchor():
    eng = DecisionEngine(llm=FakeLLM(["tap 0"]), cache=None)
    nodes = [Node(id="a", text="飞书", clickable=True, bounds=(0, 0, 100, 100))]
    d = _llm_decide(eng, nodes)
    assert d.actions[0].params["match_text"] == "飞书"
