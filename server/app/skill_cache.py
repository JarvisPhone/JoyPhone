# server/app/skill_cache.py
from __future__ import annotations

import json
import threading
import time
from pathlib import Path


def _make_key(goal: str, context: str) -> str:
    return f"{goal}|{context}"


# 全局文件锁，用于保护并发写入
_lock = threading.Lock()


class SkillCache:
    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._data: dict[str, dict] = {}
        if self._path.exists():
            self._data = json.loads(self._path.read_text(encoding="utf-8"))

    def get(self, goal: str, context: str) -> dict | None:
        return self._data.get(_make_key(goal, context))

    def learn(self, goal: str, context: str, steps: list[dict]) -> None:
        # [BUG FIX] 学习前做静态校验:发现步骤序列里有「疑似错群操作」
        # (input 到一个非搜索/消息框的位置、或 tap 进入群设置页的坐标)
        # 直接拒绝写入,避免失败路径被固化进 cache 后污染下次回放。
        if not self._validate_steps(goal, steps):
            import logging
            logging.getLogger("phoneagent.skill_cache").warning(
                "[CACHE_REJECT] goal=%r context=%r 步骤序列含可疑操作,拒绝 learn",
                goal, context,
            )
            self._data.pop(_make_key(goal, context), None)
            self._flush()
            return
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

    # 危险子串:命中即视为「探索群设置 / 错群 input」类操作。
    _DANGER_TAP_TEXT_SUBSTRINGS: tuple[str, ...] = (
        "群设置", "群公告", "群管理", "设置", "group_setting", "settings",
    )
    _DANGER_INPUT_TEXT_PREFIXES: tuple[str, ...] = (
        # LLM 把目标群名当搜索词往输入框塞的特征:input 文本 == 目标名(== goal 中的人名片段)
    )

    def _validate_steps(self, goal: str, steps: list[dict]) -> bool:
        """粗筛:步骤里若存在「进入群设置页」类可疑 tap,直接 False。"""
        import logging
        for s in steps:
            op = s.get("op", "")
            params = s.get("params", {}) or {}
            txt = (params.get("match_text") or params.get("text") or "") or ""
            if op == "tap" and any(d in txt for d in self._DANGER_TAP_TEXT_SUBSTRINGS):
                logging.getLogger("phoneagent.skill_cache").warning(
                    "[CACHE_REJECT_STEP] tap match_text=%r 命中危险子串,判定为群设置探索",
                    txt,
                )
                return False
            # [BUG FIX] input 步骤里出现「再搜一遍目标名」是典型进错群后的探索特征。
            # 检测条件:input 文本 == goal 里抽出的人名/群名片段(目标明确是发消息,不该再把目标当搜索词)。
            if op == "input" and txt:
                stripped_goal = goal.replace(" ", "")
                stripped_text = txt.replace(" ", "")
                if stripped_text and len(stripped_text) >= 4 and stripped_text in stripped_goal:
                    # input 文本是目标名片段,但任务目标要求"发消息"。这是典型进错群后
                    # 再去搜索目标群的探索动作,禁止 learn 这次失败路径。
                    logging.getLogger("phoneagent.skill_cache").warning(
                        "[CACHE_REJECT_STEP] input text=%r 是目标名片段,疑似错群探索",
                        txt,
                    )
                    return False
        return True

    def mark_miss(self, goal: str, context: str, cursor: int) -> None:
        # 某步失效：整条失效等待重新学习（MVP 策略）
        self._data.pop(_make_key(goal, context), None)
        self._flush()

    def _flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with _lock:
            self._path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
            )