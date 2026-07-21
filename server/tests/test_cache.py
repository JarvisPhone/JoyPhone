# server/tests/test_cache.py
"""技能缓存:泛化清洗 + 候选计数转正 + 占位符绑定。"""
from app.decision.cache import SkillCache, bind_params, generalize_steps
from app.infra.config import Config

LARK = "com.ss.android.lark"


def _step(op, params=None, pkg=LARK, ok=True, action_id="a"):
    return {"op": op, "params": params or {}, "pkg": pkg, "actionId": action_id, "ok": ok}


# ---- generalize_steps ----


def test_generalize_keeps_only_in_app_ok_steps():
    steps = [
        _step("home", pkg="com.android.launcher"),          # 桌面段丢弃
        _step("tap", {"match_text": "飞书"}, pkg="com.android.launcher"),
        _step("tap", {"match_text": "搜索"}, ok=True),       # 保留
        _step("tap", {"match_text": "联系人"}, ok=False),    # 失败丢弃
        _step("read_screen", ok=None),                       # 占位动作剔除
    ]
    out = generalize_steps(steps, LARK)
    assert out == [{"op": "tap", "params": {"match_text": "搜索"}}]


def test_generalize_drops_navigation_and_coordinate_only_taps():
    steps = [
        _step("back"),
        _step("wait", {"ms": "500"}),
        _step("tap", {"id": "26", "x": "909", "y": "1680"}),  # 坐标-only 机械步骤丢弃
        _step("tap", {"desc": "发送"}),                        # desc 也可作锚点
        _step("swipe", {"direction": "up"}),                   # app 内滚动保留
    ]
    out = generalize_steps(steps, LARK)
    assert out == [
        {"op": "tap", "params": {"match_text": "发送"}},
        {"op": "swipe", "params": {"direction": "up"}},
    ]


def test_generalize_parameterizes_binding_values():
    steps = [
        _step("input", {"text": "张三"}),
        _step("input", {"text": "明天见"}),
    ]
    out = generalize_steps(steps, LARK, {"contact": "张三"})
    assert out[0]["params"]["text"] == "{contact}"
    assert out[1]["params"]["text"] == "明天见"  # 非绑定值保持字面量


def test_generalize_empty_target_pkg_returns_empty():
    assert generalize_steps([_step("tap", {"match_text": "x"})], "") == []


# ---- bind_params ----


def test_bind_params_substitutes_and_rejects_unbound():
    assert bind_params({"text": "{contact}"}, {"contact": "张三"}) == {"text": "张三"}
    assert bind_params({"text": "{contact}"}, {}) is None
    assert bind_params({"text": "literal"}, {}) == {"text": "literal"}


# ---- record_success 候选计数 ----


def _valid_steps():
    return [
        {"op": "tap", "params": {"match_text": "搜索"}},
        {"op": "input", "params": {"text": "{contact}"}},
        {"op": "tap", "params": {"match_text": "发送"}},
    ]


def test_candidate_promotes_after_threshold(tmp_path):
    cache = SkillCache(tmp_path / "c.json")
    goal, ctx = "给张三发飞书", LARK + "|unknown"
    for i in range(Config.SKILL_LEARN_THRESHOLD):
        assert cache.get(goal, ctx) is None  # 未转正前不参与回放
        cache.record_success(goal, ctx, _valid_steps())
    entry = cache.get(goal, ctx)
    assert entry is not None and entry["status"] == "active"
    assert entry["steps"] == _valid_steps()


def test_candidate_resets_on_different_trajectory(tmp_path):
    cache = SkillCache(tmp_path / "c.json")
    goal, ctx = "g", LARK + "|unknown"
    cache.record_success(goal, ctx, _valid_steps())
    cache.record_success(goal, ctx, [{"op": "tap", "params": {"match_text": "别的"}}])
    # 不一致 -> 替换候选,计数归零重来
    assert cache.get(goal, ctx) is None
    raw = cache._data["%s|%s" % (goal, ctx)]
    assert raw["count"] == 1 and raw["status"] == "candidate"


def test_record_success_rejects_dangerous_steps(tmp_path):
    cache = SkillCache(tmp_path / "c.json")
    goal, ctx = "给测试群发消息", LARK + "|unknown"
    cache.record_success(goal, ctx, [{"op": "tap", "params": {"match_text": "群设置"}}])
    assert cache._data == {}


def test_active_entry_not_rewritten_by_further_success(tmp_path):
    cache = SkillCache(tmp_path / "c.json")
    goal, ctx = "g", LARK + "|unknown"
    for _ in range(Config.SKILL_LEARN_THRESHOLD):
        cache.record_success(goal, ctx, _valid_steps())
    cache.record_success(goal, ctx, [{"op": "tap", "params": {"match_text": "新轨迹"}}])
    assert cache.get(goal, ctx)["steps"] == _valid_steps()


def test_mark_miss_drops_entry(tmp_path):
    cache = SkillCache(tmp_path / "c.json")
    goal, ctx = "g", LARK + "|unknown"
    for _ in range(Config.SKILL_LEARN_THRESHOLD):
        cache.record_success(goal, ctx, _valid_steps())
    cache.mark_miss(goal, ctx, 0)
    assert cache.get(goal, ctx) is None
