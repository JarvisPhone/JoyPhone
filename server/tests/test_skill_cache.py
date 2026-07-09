# server/tests/test_skill_cache.py
import json
from pathlib import Path

from app.skill_cache import SkillCache


def _steps():
    return [
        {"op": "tap", "params": {"match_text": "搜索"}},
        {"op": "input", "params": {"text": "$MESSAGE_TARGET"}},
        {"op": "tap", "params": {"match_text": "发送"}},
    ]


def test_get_returns_none_when_empty(tmp_path):
    cache = SkillCache(tmp_path / "c.json")
    assert cache.get("发飞书消息", "com.ss.android.lark") is None


def test_learn_then_get_roundtrip(tmp_path):
    cache = SkillCache(tmp_path / "c.json")
    cache.learn("发飞书消息", "com.ss.android.lark", _steps())

    hit = cache.get("发飞书消息", "com.ss.android.lark")
    assert hit is not None
    assert hit["steps"] == _steps()
    assert hit["hits"] == 0


def test_learn_persists_to_disk(tmp_path):
    path = tmp_path / "c.json"
    SkillCache(path).learn("发飞书消息", "launcher", _steps())

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    assert "发飞书消息|launcher" in data
    assert data["发飞书消息|launcher"]["steps"] == _steps()


def test_reload_from_existing_file(tmp_path):
    path = tmp_path / "c.json"
    SkillCache(path).learn("g", "ctx", _steps())

    reloaded = SkillCache(path)
    assert reloaded.get("g", "ctx")["steps"] == _steps()


def test_mark_miss_removes_entry(tmp_path):
    cache = SkillCache(tmp_path / "c.json")
    cache.learn("g", "ctx", _steps())
    cache.mark_miss("g", "ctx", cursor=1)
    assert cache.get("g", "ctx") is None