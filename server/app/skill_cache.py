# server/app/skill_cache.py
from __future__ import annotations

import json
import time
from pathlib import Path


def _make_key(goal: str, context: str) -> str:
    return f"{goal}|{context}"


class SkillCache:
    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._data: dict[str, dict] = {}
        if self._path.exists():
            self._data = json.loads(self._path.read_text(encoding="utf-8"))

    def get(self, goal: str, context: str) -> dict | None:
        return self._data.get(_make_key(goal, context))

    def learn(self, goal: str, context: str, steps: list[dict]) -> None:
        key = _make_key(goal, context)
        now = int(time.time())
        existing = self._data.get(key)
        self._data[key] = {
            "key": key,
            "steps": steps,
            "hits": existing["hits"] if existing else 0,
            "created_ts": existing["created_ts"] if existing else now,
            "updated_ts": now,
        }
        self._flush()

    def mark_miss(self, goal: str, context: str, cursor: int) -> None:
        # 某步失效：整条失效等待重新学习（MVP 策略）
        self._data.pop(_make_key(goal, context), None)
        self._flush()

    def _flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
        )