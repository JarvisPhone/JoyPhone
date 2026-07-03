import json
from typing import Any

from app.protocol import Action, Perception


class DecisionEngine:
    def __init__(self, llm: Any, skills: Any):
        self.llm = llm
        self.skills = skills

    def decide(self, goal, perception: Perception, skill_name, cursor, history) -> Action:
        step = self.skills.next_step(
            goal=goal,
            perception=perception,
            skill_name=skill_name,
            cursor=cursor,
            history=history,
        )
        if step:
            params = {k: v for k, v in step.items() if k != "op"}
            return Action(actionId="decision", op=step["op"], params=params)

        payload = {
            "goal": goal,
            "perception": perception.model_dump(),
            "skill_name": skill_name,
            "cursor": cursor,
            "history": history,
        }
        raw = self.llm.complete(
            system="decide next UI action",
            user=json.dumps(payload, ensure_ascii=False),
        )
        data = json.loads(raw)
        return Action(actionId="decision", op=data["op"], params=data.get("params", {}))