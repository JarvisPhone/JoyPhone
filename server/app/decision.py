import json
import uuid

from app.llm import LLM
from app.protocol import Action, Perception
from app.skill_cache import SkillCache
from app.skills import SkillLibrary


class DecisionEngine:
    def __init__(self, llm: LLM, skills: SkillLibrary, cache: SkillCache | None = None):
        self._llm = llm
        self._skills = skills
        self._cache = cache

    def _cache_step(self, goal: str, perception: Perception, cursor: int) -> dict | None:
        if self._cache is None:
            return None
        entry = self._cache.get(goal, perception.pkg)
        if entry is None or cursor >= len(entry["steps"]):
            return None
        step = entry["steps"][cursor]
        match_text = step.get("params", {}).get("match_text", "")
        if match_text and not any(match_text in (n.text or "") for n in perception.nodeTree):
            return None  # 无法重定位 -> 回退
        return step

    def decide(
        self,
        goal: str,
        perception: Perception,
        skill_name: str | None,
        cursor: int,
        history: list[dict],
    ) -> Action:
        step = self._cache_step(goal, perception, cursor)
        if step is not None:
            return Action(actionId=str(uuid.uuid4()), op=step["op"], params=step.get("params", {}))

        if skill_name:
            step = self._skills.next_step(skill_name, perception.nodeTree, cursor)
            if step is not None:
                params = {k: v for k, v in step.items() if k != "op"}
                return Action(actionId=str(uuid.uuid4()), op=step["op"], params=params)

        payload = {
            "goal": goal,
            "nodes": [n.model_dump(exclude_none=True) for n in perception.nodeTree],
            "history": history,
        }
        raw = self._llm.complete(
            system="decide next UI action",
            user=json.dumps(payload, ensure_ascii=False),
        )
        data = json.loads(raw)
        return Action(actionId=str(uuid.uuid4()), op=data["op"], params=data.get("params", {}))