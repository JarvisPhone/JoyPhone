# server/app/decision/cache.py
"""技能缓存:多次验证 + 泛化沉淀,不再是「一次 done 就固化机械步骤」。

沉淀侧(record_success):
  - applied_steps 先经 generalize_steps 清洗(只留 in-app + ack ok + 语义锚点),
    入口相关的导航动作(home/back/read_screen/wait)一律剔除——每次进入 app
    的落地页可能不同,那些是当次偶然产物,不是通用路径;
  - 泛化轨迹作为「候选」(candidate)按 (goal, context) 暂存;同 key 再次成功
    且泛化序列完全一致才 count+1,达到 Config.SKILL_LEARN_THRESHOLD 才转正
    (active);不一致用最新候选替换、计数归零;
  - context 由任务层给出,含入口状态分类(如 "com.ss.android.lark|target_chat"),
    不同入口页各学各的路径。

回放侧(get + engine._cache_step):
  - 只有 active entry 参与回放;
  - 步骤里的 {placeholder} 由 engine 用当场 bindings 绑定后下发。
"""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

from app.infra.config import Config

logger = logging.getLogger("phoneagent.skill_cache")


def _make_key(goal: str, context: str) -> str:
    return f"{goal}|{context}"


# 全局文件锁，用于保护并发写入
_lock = threading.Lock()

# 入口/导航类动作:与「这次从哪个页面进入 app」强相关,泛化时剔除。
_NAV_OPS = frozenset({"home", "back", "read_screen", "wait"})


def generalize_steps(
    steps: list[dict],
    target_pkg: str,
    bindings: dict[str, str] | None = None,
) -> list[dict]:
    """把一次成功任务的 applied_steps 清洗为可沉淀的通用轨迹。

    规则:
      - 只保留 pkg == target_pkg 的 in-app 步骤(桌面导航段丢弃);
      - 只保留 ack ok 的步骤(失败/未对账的动作不沉淀);
      - 剔除导航/占位动作(home/back/read_screen/wait);
      - tap 只保留语义锚点(match_text/text/desc),坐标-only 的机械步骤丢弃;
      - input 文本若等于 bindings 里的值(如联系人名)则参数化为 {placeholder};
      - 返回 [] 表示无可学内容(调用方应跳过沉淀)。
    """
    if not target_pkg:
        return []
    bindings = bindings or {}
    out: list[dict] = []
    for s in steps:
        if s.get("pkg") != target_pkg:
            continue
        if s.get("ok") is not True:
            continue
        op = s.get("op", "")
        params = s.get("params", {}) or {}
        if op in _NAV_OPS:
            continue
        if op == "tap":
            anchor = params.get("match_text") or params.get("text") or params.get("desc")
            if not anchor:
                continue
            out.append({"op": "tap", "params": {"match_text": str(anchor)}})
        elif op == "input":
            text = str(params.get("text") or params.get("input_text") or "")
            if not text:
                continue
            for key, val in bindings.items():
                if val and text == val:
                    text = "{%s}" % key
                    break
            out.append({"op": "input", "params": {"text": text}})
        elif op == "swipe":
            direction = params.get("direction")
            if direction:
                out.append({"op": "swipe", "params": {"direction": str(direction)}})
    return out


def bind_params(params: dict, bindings: dict[str, str]) -> dict | None:
    """回放时把步骤参数里的 {placeholder} 用当场 bindings 绑定。

    绑定后仍含 "{" 说明参数缺失,返回 None(调用方放弃本次回放)。
    """
    out: dict[str, str] = {}
    for k, v in params.items():
        text = str(v)
        for key, val in bindings.items():
            text = text.replace("{%s}" % key, val)
        if "{" in text:
            return None
        out[k] = text
    return out


class SkillCache:
    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._data: dict[str, dict] = {}
        if self._path.exists():
            self._data = json.loads(self._path.read_text(encoding="utf-8"))

    def get(self, goal: str, context: str) -> dict | None:
        """只返回已转正(active)的 entry;候选不参与回放。"""
        entry = self._data.get(_make_key(goal, context))
        if entry is None or entry.get("status") != "active":
            return None
        return entry

    def record_success(self, goal: str, context: str, steps: list[dict]) -> None:
        """记录一次成功轨迹(须已泛化);达到次数门槛才转正为可回放 entry。"""
        if not steps:
            return
        if not self._validate_steps(goal, steps):
            logger.warning(
                "[CACHE_REJECT] goal=%r context=%r 步骤序列含可疑操作,清除候选",
                goal, context,
            )
            self._data.pop(_make_key(goal, context), None)
            self._flush()
            return

        key = _make_key(goal, context)
        now = int(time.time())
        existing = self._data.get(key)

        if existing is not None and existing.get("status") == "active":
            # 已转正:轨迹已被多次验证,后续成功不改变内容(MVP 不做版本演进)
            return

        if existing is not None and existing.get("steps") == steps:
            count = int(existing.get("count", 0)) + 1
            created_ts = existing.get("created_ts", now)
        else:
            if existing is not None:
                logger.info(
                    "[CACHE_CANDIDATE_RESET] key=%r 轨迹与候选不一致,替换并重新计数",
                    key,
                )
            count = 1
            created_ts = now

        if count >= Config.SKILL_LEARN_THRESHOLD:
            self._data[key] = {
                "key": key,
                "status": "active",
                "steps": steps,
                "count": count,
                "hits": 0,
                "created_ts": created_ts,
                "updated_ts": now,
            }
            logger.info(
                "[CACHE_PROMOTE] key=%r 连续成功 %d 次,转正为可回放技能(%d 步)",
                key, count, len(steps),
            )
        else:
            self._data[key] = {
                "key": key,
                "status": "candidate",
                "steps": steps,
                "count": count,
                "created_ts": created_ts,
                "updated_ts": now,
            }
            logger.info(
                "[CACHE_CANDIDATE] key=%r 候选计数 %d/%d",
                key, count, Config.SKILL_LEARN_THRESHOLD,
            )
        self._flush()

    # 危险子串:命中即视为「探索群设置 / 错群 input」类操作。
    _DANGER_TAP_TEXT_SUBSTRINGS: tuple[str, ...] = (
        "群设置", "群公告", "群管理", "设置", "group_setting", "settings",
    )

    def _validate_steps(self, goal: str, steps: list[dict]) -> bool:
        """粗筛:步骤里若存在「进入群设置页」类可疑 tap / 目标名 input,直接 False。"""
        for s in steps:
            op = s.get("op", "")
            params = s.get("params", {}) or {}
            txt = (params.get("match_text") or params.get("text") or "") or ""
            if op == "tap" and any(d in txt for d in self._DANGER_TAP_TEXT_SUBSTRINGS):
                logger.warning(
                    "[CACHE_REJECT_STEP] tap match_text=%r 命中危险子串,判定为群设置探索",
                    txt,
                )
                return False
            # input 文本是目标名片段,是典型进错群后再搜索的探索特征。
            if op == "input" and txt:
                stripped_goal = goal.replace(" ", "")
                stripped_text = txt.replace(" ", "")
                if (
                    stripped_text
                    and not stripped_text.startswith("{")
                    and len(stripped_text) >= 4
                    and stripped_text in stripped_goal
                ):
                    logger.warning(
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
