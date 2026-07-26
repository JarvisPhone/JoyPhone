"""_learn_cache 沉淀机制测试:覆盖 2026-07-26 P2 expansion Task 5。

核心契约:沉淀(record_success → 转正)与回放(REPLAY_ENABLED)是两个独立机制。
即使 Config.REPLAY_ENABLED = False(LLM 链路未稳定期),沉淀仍应工作。
"""
from pathlib import Path

from app.decision.cache import SkillCache, generalize_steps
from app.infra.config import Config
from app.task.context import TaskContext


def _make_ctx_with_steps(applied_steps: list[dict], target_pkg: str = "com.test.app") -> TaskContext:
    """构造一个最小 TaskContext,applied_steps 已含成功轨迹。"""
    ctx = TaskContext(
        task_id="t-test",
        goal="测试沉淀",
        target_pkg=target_pkg,
    )
    ctx.applied_steps = applied_steps
    return ctx


def test_replay_enabled_default_is_false():
    """baseline 约束:Config.REPLAY_ENABLED 默认 False(LLM 链路未稳定期)。"""
    assert Config.REPLAY_ENABLED is False


def test_generalize_steps_keeps_in_app_anchor_steps():
    """只保留 in-app(命中 target_pkg)+ tap 锚点 + 不可导航的步骤。"""
    steps = [
        # in-app 锚点 tap → 保留
        {"op": "tap", "pkg": "com.test.app", "params": {"match_text": "发送"},
         "ok": True},
        # home 导航 → 剔除
        {"op": "home", "pkg": "com.test.app", "params": {}, "ok": True},
        # 桌面层 → 剔除(pkg 不匹配)
        {"op": "tap", "pkg": "com.android.launcher", "params": {"match_text": "图标"},
         "ok": True},
        # ack fail → 剔除
        {"op": "tap", "pkg": "com.test.app", "params": {"match_text": "X"},
         "ok": False},
        # tap 没锚点 → 剔除
        {"op": "tap", "pkg": "com.test.app", "params": {"x": "1", "y": "2"},
         "ok": True},
    ]
    out = generalize_steps(steps, "com.test.app")
    assert len(out) == 1
    assert out[0] == {"op": "tap", "params": {"match_text": "发送"}}


def test_generalize_steps_parametrizes_input_bindings():
    """input 文本若匹配 bindings[key] → 参数化为 {placeholder}。"""
    steps = [
        {"op": "input", "pkg": "com.test.app",
         "params": {"text": "张三"}, "ok": True},
    ]
    bindings = {"contact": "张三"}
    out = generalize_steps(steps, "com.test.app", bindings=bindings)
    assert out == [{"op": "input", "params": {"text": "{contact}"}}]


def test_cache_record_success_independent_of_replay_enabled(tmp_path: Path):
    """核心契约:即使 REPLAY_ENABLED=False,record_success 仍能写入 candidate/active。

    REPLAY_ENABLED 只控制「回放」(engine._cache_step 命中 active),
    不控制「沉淀」(cache.record_success)。
    """
    assert Config.REPLAY_ENABLED is False  # baseline 假设
    cache = SkillCache(tmp_path / "cache.json")
    # 在 REPLAY_ENABLED=False 时模拟 _learn_cache 路径
    steps = [
        {"op": "tap", "pkg": "com.test.app", "params": {"match_text": "目标"},
         "ok": True},
    ]
    cache.record_success("测试 goal", "com.test.app|target", steps)
    # 第一次成功 → candidate
    entry = cache.get("测试 goal", "com.test.app|target")
    assert entry is None  # active 才是回放目标,candidate 不可 get
    # 验证 file 已写入(无论 REPLAY_ENABLED)
    assert (tmp_path / "cache.json").exists()
    data = json.loads((tmp_path / "cache.json").read_text())
    assert len(data) == 1
    assert data[list(data.keys())[0]]["status"] == "candidate"


def test_cache_promotes_to_active_after_threshold(tmp_path: Path):
    """达到 SKILL_LEARN_THRESHOLD 次连续成功后转正为 active,可参与回放。"""
    cache = SkillCache(tmp_path / "cache.json")
    steps = [
        {"op": "tap", "pkg": "com.test.app", "params": {"match_text": "目标"},
         "ok": True},
    ]
    # 连续成功 N 次(N = SKILL_LEARN_THRESHOLD)
    for _ in range(Config.SKILL_LEARN_THRESHOLD):
        cache.record_success("测试 goal", "ctx", steps)
    # 转正后 get 应返回
    entry = cache.get("测试 goal", "ctx")
    assert entry is not None
    assert entry["status"] == "active"


def test_cache_marks_miss_on_step_signature_change(tmp_path: Path):
    """轨迹与候选不一致 → 替换候选、计数归零,不再继续累加。"""
    cache = SkillCache(tmp_path / "cache.json")
    steps_v1 = [{"op": "tap", "pkg": "com.test.app",
                 "params": {"match_text": "v1"}, "ok": True}]
    steps_v2 = [{"op": "tap", "pkg": "com.test.app",
                 "params": {"match_text": "v2"}, "ok": True}]
    cache.record_success("g", "ctx", steps_v1)  # candidate count=1
    cache.record_success("g", "ctx", steps_v2)  # 不一致 → 替换,count=1
    # 不会转正,get 返回 None
    assert cache.get("g", "ctx") is None
    # 再连续 record v2 两次
    cache.record_success("g", "ctx", steps_v2)  # count=2
    cache.record_success("g", "ctx", steps_v2)  # count=3 = 阈值 → active
    assert cache.get("g", "ctx") is not None


def test_cache_rejects_danger_substrings(tmp_path: Path):
    """群设置等危险锚点直接拒绝沉淀。"""
    cache = SkillCache(tmp_path / "cache.json")
    steps = [
        {"op": "tap", "pkg": "com.test.app",
         "params": {"match_text": "群设置"}, "ok": True},
    ]
    cache.record_success("g", "ctx", steps)
    # 危险步骤被 _validate_steps 拒 → _data.pop + _flush,file 可能空但 entry 一定无
    if (tmp_path / "cache.json").exists():
        data = json.loads((tmp_path / "cache.json").read_text() or "{}")
        # 不应留下任何 cache entry
        assert data == {}
    # 即便 file 不存在,get 也应返回 None
    assert cache.get("g", "ctx") is None


# json import used by test_cache_record_success_independent_of_replay_enabled
import json