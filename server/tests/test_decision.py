import json
import uuid

from app.decision import DecisionEngine
from app.decision.llm import FakeLLM
from app.protocol import Node, Perception
from app.skill_cache import SkillCache
from app.skills import SkillLibrary


def _perc(nodes: list[Node]) -> Perception:
    return Perception(nodeTree=nodes, pkg="com.ss.android.lark", activity="Main", ts=1)


def test_skill_hit_without_llm(monkeypatch):
    llm = FakeLLM(["back"])

    def _should_not_be_called(system: str, user: str, image_b64: str | None = None) -> str:
        raise AssertionError("LLM should not be called when skill hits")

    monkeypatch.setattr(llm, "complete", _should_not_be_called)
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    # feishu_send_message skill 第一步是 tap(desc="搜索")，所以需要节点有匹配的 desc
    p = _perc([Node(id="n1", text="搜索", desc="搜索", clickable=True)])

    actions = engine.decide(goal="发消息", perception=p, skill_name="feishu_send_message", cursor=0, history=[])

    assert isinstance(actions, list)
    assert len(actions) == 1
    assert actions[0].op == "tap"
    # step.to_dict() 包含 desc 作为 match_text 的依据
    assert "desc" in actions[0].params or "match_text" in actions[0].params
    uuid.UUID(actions[0].actionId)


def test_fallback_to_llm_when_skill_miss(monkeypatch):
    llm = FakeLLM(["back"])
    captured: dict[str, str] = {}

    def _capture_complete(system: str, user: str, image_b64: str | None = None) -> str:
        captured["system"] = system
        captured["user"] = user
        return "back"

    monkeypatch.setattr(llm, "complete", _capture_complete)
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    p = _perc([Node(id="n1", text="首页")])

    actions = engine.decide(goal="发消息", perception=p, skill_name="feishu_send", cursor=0, history=[])

    assert isinstance(actions, list)
    assert len(actions) == 1
    assert actions[0].op == "back"
    assert actions[0].params == {}
    uuid.UUID(actions[0].actionId)

    # 系统提示词必须教 LLM 用文本指令协议、列出合法指令名，并说明 screen 编码格式，
    # 否则真实模型不知如何回复。文本协议下不再要求 JSON。
    system = captured["system"]
    for op in ("tap", "input", "swipe", "done", "abort", "read"):
        assert op in system
    assert "每行一条" in system

    payload = json.loads(captured["user"])
    assert set(payload.keys()) == {"goal", "pkg", "target_pkg", "screen", "history"}
    assert payload["goal"] == "发消息"
    assert payload["history"] == []
    assert payload["screen"] == '[0] text "首页"'


def test_cache_hit_returns_step_without_llm(tmp_path, monkeypatch):
    cache = SkillCache(tmp_path / "c.json")
    cache.learn("发消息", "com.ss.android.lark", [{"op": "tap", "params": {"match_text": "搜索"}}])

    llm = FakeLLM(["back"])

    def _fail(system: str, user: str, image_b64: str | None = None) -> str:
        raise AssertionError("LLM must not be called on cache hit")

    monkeypatch.setattr(llm, "complete", _fail)
    engine = DecisionEngine(llm=llm, skills=SkillLibrary(), cache=cache)
    p = _perc([Node(id="n1", text="搜索", clickable=True)])

    actions = engine.decide(goal="发消息", perception=p, skill_name=None, cursor=0, history=[])

    assert isinstance(actions, list)
    assert len(actions) == 1
    assert actions[0].op == "tap"
    assert actions[0].params == {"match_text": "搜索"}


def test_cache_miss_when_node_not_matchable_falls_through(tmp_path):
    cache = SkillCache(tmp_path / "c.json")
    cache.learn("发消息", "com.ss.android.lark", [{"op": "tap", "params": {"match_text": "搜索"}}])

    llm = FakeLLM(["back"])
    engine = DecisionEngine(llm=llm, skills=SkillLibrary(), cache=cache)
    p = _perc([Node(id="n1", text="首页")])  # 无“搜索”节点，缓存步无法重定位

    actions = engine.decide(goal="发消息", perception=p, skill_name=None, cursor=0, history=[])

    assert actions[0].op == "back"  # 回退到 LLM


def test_llm_non_instruction_falls_back_to_read_screen(monkeypatch):
    # 真机联调实测：真实 LLM 可能返回无法识别为指令的自然语言/空串。
    # 决策层必须兜底为 read_screen（重新观察），保证 WS 循环不中断。
    llm = FakeLLM(["这不是指令，我需要更多信息"])
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    p = _perc([Node(id="n1", text="首页")])

    actions = engine.decide(goal="发消息", perception=p, skill_name=None, cursor=0, history=[])

    assert isinstance(actions, list)
    assert len(actions) == 1
    assert actions[0].op == "read_screen"
    assert actions[0].params == {}
    uuid.UUID(actions[0].actionId)


def test_llm_empty_string_falls_back_to_read_screen():
    llm = FakeLLM([""])
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    p = _perc([Node(id="n1", text="首页")])

    actions = engine.decide(goal="发消息", perception=p, skill_name=None, cursor=0, history=[])

    assert actions[0].op == "read_screen"


def test_decide_returns_action_list(monkeypatch):
    # 文本协议批处理：N 条盲操作 + 最多 1 条 tap/input 收尾。
    # 遇首个 tap/input 下发后本批结束（截断），tap 那条注入 x/y 坐标。
    llm = FakeLLM(["swipe left\nread\ntap 2"])
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    nodes = [
        Node(id="a", text="微信", clickable=True, bounds=(0, 0, 100, 100)),
        Node(id="b", text="qq", clickable=True, bounds=(0, 0, 50, 50)),
        Node(id="c", text="飞书", clickable=True, bounds=(200, 300, 400, 500)),
    ]
    actions = engine.decide(goal="打开飞书", perception=_perc(nodes), skill_name=None, cursor=0, history=[])

    assert isinstance(actions, list)
    assert [a.op for a in actions] == ["swipe", "read_screen", "tap"]
    # tap 是收尾且注入了坐标：nodes[2] bounds=(200,300,400,500) -> 中心 (300,400)
    assert actions[-1].params["x"] == "300"
    assert actions[-1].params["y"] == "400"


def test_decide_non_instruction_falls_back_to_read_screen_single(monkeypatch):
    # LLM 返回完全无法识别为指令的内容 -> decide 返回 [read_screen 单元素]。
    llm = FakeLLM(["blah blah 没有任何合法动词"])
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    p = _perc([Node(id="n1", text="首页")])

    actions = engine.decide(goal="发消息", perception=p, skill_name=None, cursor=0, history=[])

    assert isinstance(actions, list)
    assert len(actions) == 1
    assert actions[0].op == "read_screen"


def test_decide_stops_batch_at_first_tap(monkeypatch):
    # 批处理截断：tap 之后的指令不下发（本批结束重抓帧）。
    llm = FakeLLM(["swipe left\ntap 0\nnext_page\ntap 1"])
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    nodes = [
        Node(id="a", text="飞书", clickable=True, bounds=(0, 0, 100, 100)),
        Node(id="b", text="微信", clickable=True, bounds=(200, 200, 300, 300)),
    ]
    actions = engine.decide(goal="打开飞书", perception=_perc(nodes), skill_name=None, cursor=0, history=[])

    assert [a.op for a in actions] == ["swipe", "tap"]
    assert actions[-1].params["x"] == "50"
    assert actions[-1].params["y"] == "50"


def test_decide_stops_batch_at_first_input(monkeypatch):
    # input 同样收尾截断。
    llm = FakeLLM(["input 0 你好\ntap 0"])
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    nodes = [Node(id="a", text="搜索框", editable=True, bounds=(0, 0, 100, 100))]
    actions = engine.decide(goal="搜索", perception=_perc(nodes), skill_name=None, cursor=0, history=[])

    assert [a.op for a in actions] == ["input"]
    assert actions[0].params["text"] == "你好"


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
    llm = FakeLLM(["back"])

    def _capture(system, user, image_b64=None):
        captured["user"] = user
        return "back"

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
    llm = FakeLLM(["back"])

    def _capture(system, user, image_b64=None):
        captured["user"] = user
        return "back"

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
    llm = FakeLLM(["tap 1"])
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    nodes = [
        Node(id="a", text="微信", clickable=True, bounds=(0, 0, 100, 100)),
        Node(id="b", text="飞书", clickable=True, bounds=(200, 300, 400, 500)),
    ]
    actions = engine.decide(goal="打开飞书", perception=_perc(nodes), skill_name=None, cursor=0, history=[])

    action = actions[-1]
    assert action.op == "tap"
    # 选中 nodes[1] "飞书" bounds=(200,300,400,500) -> 中心 (300, 400)
    assert action.params["x"] == "300"
    assert action.params["y"] == "400"


def test_tap_empty_id_not_resolved(monkeypatch):
    # 节点引用键只认 [n] 下标(id)；文本协议下无 id 的 tap 无法命中,
    # 不注入坐标,保留原 params(此处 id 为空串)。
    llm = FakeLLM(["tap"])
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    nodes = [
        Node(id="a", text="微信", clickable=True, bounds=(0, 0, 100, 100)),
        Node(id="b", text="飞书", clickable=True, bounds=(200, 300, 400, 500)),
    ]
    actions = engine.decide(goal="打开飞书", perception=_perc(nodes), skill_name=None, cursor=0, history=[])

    action = actions[-1]
    assert action.op == "tap"
    assert "x" not in action.params
    assert "y" not in action.params


def test_tap_by_id_out_of_range_keeps_original(monkeypatch):
    # id 越界 -> 解析失败,不注入坐标,保留原 params。
    llm = FakeLLM(["tap 99"])
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    nodes = [Node(id="a", text="飞书", clickable=True, bounds=(200, 300, 400, 500))]
    actions = engine.decide(goal="打开飞书", perception=_perc(nodes), skill_name=None, cursor=0, history=[])

    action = actions[-1]
    assert action.op == "tap"
    assert "x" not in action.params
    assert "y" not in action.params
    assert action.params.get("id") == "99"


def test_tap_by_id_node_without_bounds_keeps_original(monkeypatch):
    # id 命中但该 node 无 bounds -> 不注入坐标,保留原 params。
    llm = FakeLLM(["tap 0"])
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    nodes = [Node(id="a", text="飞书", clickable=True, bounds=None)]
    actions = engine.decide(goal="打开飞书", perception=_perc(nodes), skill_name=None, cursor=0, history=[])

    action = actions[-1]
    assert action.op == "tap"
    assert "x" not in action.params
    assert "y" not in action.params
    assert action.params.get("id") == "0"


def test_tap_unresolvable_keeps_original_params(monkeypatch):
    # 选中节点找不到(空 id) -> 不注入坐标，保留原 params 供端侧兜底
    llm = FakeLLM(["tap"])
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    nodes = [Node(id="a", text="飞书", clickable=True, bounds=(0, 0, 10, 10))]
    actions = engine.decide(goal="打开飞书", perception=_perc(nodes), skill_name=None, cursor=0, history=[])

    action = actions[-1]
    assert "x" not in action.params
    assert "y" not in action.params


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
    assert parse_actions("read") == [{"op": "read_screen"}]


def test_parse_actions_home_first_and_next_page_no_longer_mapped():
    # 复合 op 已废弃：home_first / next_page 不再解析为动作（跳过）。
    assert parse_actions("home_first") == []
    assert parse_actions("next_page") == []


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
    text = "swipe left\nread\ntap 2\ninput 4 hi there\nswipe left\ndone"
    assert parse_actions(text) == [
        {"op": "swipe", "direction": "left"},
        {"op": "read_screen"},
        {"op": "tap", "id": "2"},
        {"op": "input", "id": "4", "text": "hi there"},
        {"op": "swipe", "direction": "left"},
        {"op": "done"},
    ]


# ---- pkg guard: 跑错应用时强制回桌面重开,避免 LLM 顺手 tap 通知/磁贴 ----
def test_pkg_guard_forces_home_first_when_current_pkg_mismatches(monkeypatch):
    # 当前在前台的是微信,目标 app 是飞书 -> 必须直接 home,
    # 完全跳过 LLM(即便节点里有通知/磁贴等 clickable 元素)。
    def _should_not_be_called(system: str, user: str, image_b64=None) -> str:
        raise AssertionError("LLM must not be called when pkg_guard fires")

    llm = FakeLLM(["tap 0"])
    monkeypatch.setattr(llm, "complete", _should_not_be_called)
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    nodes = [
        Node(id="n1", text="微信收到 3 条新消息", clickable=True),
        Node(id="n2", text="张三 回复了你", clickable=True),
    ]
    p = Perception(nodeTree=nodes, pkg="com.tencent.mm", activity="Main", ts=1)

    actions = engine.decide(
        goal="打开飞书给张三发消息",
        perception=p,
        skill_name=None,
        cursor=0,
        history=[],
        target_pkg="com.ss.android.lark",
    )

    assert len(actions) == 1
    assert actions[0].op == "home"
    assert actions[0].params == {}


def test_pkg_guard_skips_when_pkg_matches(monkeypatch):
    # 当前 pkg 与 target_pkg 一致 -> 不触发 guard,正常走到 LLM。
    llm = FakeLLM(["tap 0"])
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    p = Perception(nodeTree=[Node(id="n1", text="首页")], pkg="com.ss.android.lark", activity="Main", ts=1)

    actions = engine.decide(
        goal="打开飞书给张三发消息",
        perception=p,
        skill_name=None,
        cursor=0,
        history=[],
        target_pkg="com.ss.android.lark",
    )

    assert actions[0].op == "tap"


def test_pkg_guard_skips_when_target_pkg_unknown(monkeypatch):
    # 目标 app 无法从 goal 解析(target_pkg="") -> 不触发 guard。
    llm = FakeLLM(["tap 0"])
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    p = Perception(nodeTree=[Node(id="n1", text="首页")], pkg="com.tencent.mm", activity="Main", ts=1)

    actions = engine.decide(
        goal="随便看看",
        perception=p,
        skill_name=None,
        cursor=0,
        history=[],
        target_pkg="",
    )

    assert actions[0].op == "tap"


def test_pkg_guard_minus_one_swipes_right_not_home(monkeypatch):
    # 跑偏且当前在【负一屏】(launcher, workspace 内缩) -> 场景导航吐 swipe right,
    # 而非无脑 home_first_page(否则可能停在负一屏死循环)。
    llm = FakeLLM(["tap 0"])
    monkeypatch.setattr(
        llm, "complete",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM must not be called")),
    )
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    nodes = [
        Node(id="n1", viewIdResourceName="com.android.launcher:id/workspace",
             bounds=(43, 95, 1037, 2279)),
        Node(id="n2", text="小布建议", clickable=True),
    ]
    p = Perception(nodeTree=nodes, pkg="com.android.launcher", activity="Launcher", ts=1)

    actions = engine.decide(
        goal="打开飞书给张三发消息", perception=p, skill_name=None,
        cursor=0, history=[], target_pkg="com.ss.android.lark",
    )

    assert len(actions) == 1
    assert actions[0].op == "swipe"
    assert actions[0].params.get("direction") == "right"


def test_pkg_guard_recent_apps_presses_home(monkeypatch):
    # 跑偏且当前在【最近任务】(overview_panel) -> 场景导航吐 home。
    llm = FakeLLM(["tap 0"])
    monkeypatch.setattr(
        llm, "complete",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM must not be called")),
    )
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    nodes = [Node(id="n1", viewIdResourceName="com.android.launcher:id/overview_panel")]
    p = Perception(nodeTree=nodes, pkg="com.android.launcher", activity="Recents", ts=1)

    actions = engine.decide(
        goal="打开飞书给张三发消息", perception=p, skill_name=None,
        cursor=0, history=[], target_pkg="com.ss.android.lark",
    )

    assert actions[0].op == "home"


def test_pkg_guard_in_app_still_home_first_page(monkeypatch):
    # 跑偏且在别的 App 内(IN_APP) -> home 回桌面(兼容原行为)。
    llm = FakeLLM(["tap 0"])
    monkeypatch.setattr(
        llm, "complete",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("LLM must not be called")),
    )
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    p = Perception(nodeTree=[Node(id="n1", text="微信收到消息", clickable=True)],
                   pkg="com.tencent.mm", activity="Main", ts=1)

    actions = engine.decide(
        goal="打开飞书给张三发消息", perception=p, skill_name=None,
        cursor=0, history=[], target_pkg="com.ss.android.lark",
    )

    assert actions[0].op == "home"


def test_resolve_target_pkg_basic():
    from app.app_goal_resolver import resolve_target_pkg

    assert resolve_target_pkg("打开飞书给张三发消息") == "com.ss.android.lark"
    assert resolve_target_pkg("微信里发消息给李四") == "com.tencent.mm"
    assert resolve_target_pkg("看看通知") is None
    assert resolve_target_pkg("") is None


def test_pkg_guard_stall_escalates_to_llm(monkeypatch):
    # 连续 STALL_THRESHOLD 帧同 scene 同 op（UNKNOWN 反复 home 无效）
    # -> 触发 LLM 脱困，escalation_level 置 1。
    from app.session import Session
    from app.scene import SceneConfig
    calls = {"n": 0}

    def _escape(system, user, image_b64=None):
        calls["n"] += 1
        return "target_scene: HOME"

    llm = FakeLLM(["x"])
    monkeypatch.setattr(llm, "complete", _escape)
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    sess = Session("t", "打开飞书给张三发消息", "d")
    p = Perception(nodeTree=[Node(id="n1", text="未知界面")],
                   pkg="com.tencent.mm", activity="X", ts=1)
    for _ in range(SceneConfig.STALL_THRESHOLD + 1):
        engine.decide(goal=sess.goal, perception=p, skill_name=None, cursor=0,
                      history=[], target_pkg="com.ss.android.lark", guard=sess.guard)
    assert calls["n"] >= 1
    assert sess.guard["escalation_level"] >= 1


def test_parse_target_scene():
    from app.decision import _parse_target_scene
    from app.scene import Scene

    assert _parse_target_scene("target_scene: HOME") == Scene.HOME
    assert _parse_target_scene("胡言乱语\ntarget_scene: MINUS_ONE") == Scene.MINUS_ONE
    assert _parse_target_scene("target_scene: home") == Scene.HOME
    assert _parse_target_scene("target_scene: NOT_A_SCENE") is None
    assert _parse_target_scene("完全没有关键字") is None
    assert _parse_target_scene("") is None


def test_pkg_guard_oscillation_escalates_to_llm(monkeypatch):
    # scene 在滑窗内反复出现(振荡) -> 触发 LLM 脱困，escalation_level 置 1。
    from app.session import Session
    from app.scene import SceneConfig

    calls = {"n": 0}

    def _escape(system, user, image_b64=None):
        calls["n"] += 1
        return "target_scene: HOME"

    llm = FakeLLM(["x"])
    monkeypatch.setattr(llm, "complete", _escape)
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    sess = Session("t", "打开飞书给张三发消息", "d")
    # 交替两种活动/文本使 last_op 变化(避开停滞)，但 scene 反复回到同一 IN_APP
    perceptions = [
        Perception(nodeTree=[Node(id="a", text="界面A")],
                   pkg="com.tencent.mm", activity="A", ts=1),
        Perception(nodeTree=[Node(id="b", text="界面B")],
                   pkg="com.tencent.mm", activity="B", ts=2),
    ]
    for i in range(2 * (SceneConfig.CYCLE_THRESHOLD + 1)):
        engine.decide(goal=sess.goal, perception=perceptions[i % 2], skill_name=None,
                      cursor=0, history=[], target_pkg="com.ss.android.lark",
                      guard=sess.guard)
    assert calls["n"] >= 1
    assert sess.guard["escalation_level"] >= 1


def test_pkg_guard_level2_mechanical_fallback(monkeypatch):
    # 已在 level 1 仍卡 -> 机械降级 fallback_action(不再问 LLM)。
    from app.session import Session
    from app.scene import SceneConfig

    def _escape(system, user, image_b64=None):
        return "target_scene: HOME"

    llm = FakeLLM(["x"])
    monkeypatch.setattr(llm, "complete", _escape)
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    sess = Session("t", "打开飞书给张三发消息", "d")
    p = Perception(nodeTree=[Node(id="n1", text="未知界面")],
                   pkg="com.tencent.mm", activity="X", ts=1)
    last = None
    for _ in range(SceneConfig.STALL_THRESHOLD + 3):
        last = engine.decide(goal=sess.goal, perception=p, skill_name=None, cursor=0,
                             history=[], target_pkg="com.ss.android.lark",
                             guard=sess.guard)
    assert sess.guard["escalation_level"] >= 2


def test_pkg_guard_level2_exhausted_aborts(monkeypatch):
    # 三级脱困全部耗尽 -> abort，reason 前缀 pkg_guard_stuck。
    from app.session import Session
    from app.scene import SceneConfig

    def _escape(system, user, image_b64=None):
        return "target_scene: HOME"

    llm = FakeLLM(["x"])
    monkeypatch.setattr(llm, "complete", _escape)
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    sess = Session("t", "打开飞书给张三发消息", "d")
    p = Perception(nodeTree=[Node(id="n1", text="未知界面")],
                   pkg="com.tencent.mm", activity="X", ts=1)
    last = None
    for _ in range(SceneConfig.STALL_THRESHOLD + 6):
        last = engine.decide(goal=sess.goal, perception=p, skill_name=None, cursor=0,
                             history=[], target_pkg="com.ss.android.lark",
                             guard=sess.guard)
    assert last[0].op == "abort"
    assert last[0].params["reason"].startswith("pkg_guard_stuck")