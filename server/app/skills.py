from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from app.protocol import Node


@dataclass
class SkillStep:
    op: str
    text: Optional[str] = None
    desc: Optional[str] = None
    view_id: Optional[str] = None
    class_name: Optional[str] = None
    index: Optional[int] = None
    input_text: Optional[str] = None

    def to_dict(self) -> dict:
        d = {"op": self.op}
        if self.text is not None:
            d["text"] = self.text
        if self.desc is not None:
            d["desc"] = self.desc
        if self.view_id is not None:
            d["view_id"] = self.view_id
        if self.class_name is not None:
            d["class_name"] = self.class_name
        if self.index is not None:
            d["index"] = self.index
        if self.input_text is not None:
            d["input_text"] = self.input_text
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "SkillStep":
        return cls(
            op=d.get("op", "tap"),
            text=d.get("text"),
            desc=d.get("desc"),
            view_id=d.get("view_id"),
            class_name=d.get("class_name"),
            index=d.get("index"),
            input_text=d.get("input_text"),
        )


@dataclass
class Skill:
    name: str
    app: str
    description: str
    steps: list[SkillStep] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)


_FEISHU_SKILLS = {
    "feishu_send_message": Skill(
        name="feishu_send_message",
        app="com.ss.android.lark",
        description="在飞书发送消息",
        keywords=["飞书", "发送", "消息", "发给", "发给"],
        steps=[
            SkillStep(op="tap", desc="搜索"),
            SkillStep(op="tap", text="搜索"),
            SkillStep(op="input", input_text="{contact}"),
            SkillStep(op="tap", text="发送"),
        ],
    ),
    "feishu_search_contact": Skill(
        name="feishu_search_contact",
        app="com.ss.android.lark",
        description="在飞书搜索联系人",
        keywords=["搜索", "找", "联系人", "找人"],
        steps=[
            SkillStep(op="tap", desc="搜索"),
            SkillStep(op="input", input_text="{query}"),
        ],
    ),
}


class SkillMatcher:
    @staticmethod
    def match_node(step: SkillStep, nodes: list[Node], node_index: int) -> bool:
        if step.index is not None and step.index == node_index:
            return True

        if step.view_id is not None and nodes[node_index].viewIdResourceName:
            if step.view_id in (nodes[node_index].viewIdResourceName or ""):
                return True

        if step.class_name is not None and nodes[node_index].className:
            if step.class_name in (nodes[node_index].className or ""):
                return True

        if step.text:
            node_text = nodes[node_index].text or ""
            if step.text in node_text:
                return True

        if step.desc:
            node_desc = nodes[node_index].desc or ""
            if step.desc in node_desc:
                return True

        return False


class SkillLibrary:
    def __init__(self):
        self._skills: dict[str, Skill] = _FEISHU_SKILLS.copy()
        self._index_by_app: dict[str, list[str]] = {}
        self._reindex()

    def _reindex(self) -> None:
        self._index_by_app.clear()
        for name, skill in self._skills.items():
            if skill.app not in self._index_by_app:
                self._index_by_app[skill.app] = []
            self._index_by_app[skill.app].append(name)

    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill
        self._reindex()

    def get(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def select(self, goal: str, pkg: str) -> Optional[str]:
        goal_lower = goal.lower()
        candidates = self._index_by_app.get(pkg, [])

        for name in candidates:
            skill = self._skills[name]
            for keyword in skill.keywords:
                if keyword.lower() in goal_lower:
                    return name

        return None

    def next_step(self, skill_name: str, nodes: list[Node], cursor: int) -> Optional[dict]:
        skill = self._skills.get(skill_name)
        if skill is None:
            return None

        if cursor < 0 or cursor >= len(skill.steps):
            return None

        step = skill.steps[cursor]

        if step.index is not None and step.index < len(nodes):
            result = step.to_dict()
            if step.input_text:
                result["input_text"] = step.input_text
            return result

        for i, node in enumerate(nodes):
            if SkillMatcher.match_node(step, nodes, i):
                result = step.to_dict()
                if step.input_text:
                    result["input_text"] = step.input_text
                return result

        logging.getLogger("phoneagent.skills").warning(
            "[SKILL_NO_MATCH] skill=%s cursor=%s step_op=%s 当前帧无节点匹配，回落 LLM 决策",
            skill_name, cursor, step.op,
        )
        return None
