from __future__ import annotations

from app.protocol import Node

_SKILLS = {
    "feishu_send": [
        {"match_text": "通讯录", "op": "tap"},
        {"match_text": "搜索", "op": "tap"},
        {"match_text": "", "op": "input"},
        {"match_text": "发送", "op": "tap"},
    ]
}


class SkillLibrary:
    @staticmethod
    def next_step(skill_name: str, nodes: list[Node], cursor: int):
        steps = _SKILLS.get(skill_name)
        if steps is None:
            return None

        if cursor < 0 or cursor >= len(steps):
            return None

        step = steps[cursor]
        match_text = step["match_text"]

        if match_text == "":
            return step

        for node in nodes:
            text = node.text or ""
            if match_text in text:
                return step

        return None