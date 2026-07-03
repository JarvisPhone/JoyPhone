import json
import uuid

from app.llm import LLM
from app.protocol import Action, Perception
from app.skills import SkillLibrary


class DecisionEngine:
    def __init__(self, llm: LLM, skills: SkillLibrary):
        self._llm = llm
        self._skills = skills

    def decide(
        self,
        goal: str,
        perception: Perception,
        skill_name: str | None,
        cursor: int,
        history: list[dict],
    ) -> Action:
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