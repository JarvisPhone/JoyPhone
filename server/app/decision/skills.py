"""技能参数绑定层。

SkillTemplate 携带 ``{param}`` 占位符,BoundSkill.bind 用 bindings 替换后
得到可直接逐步执行的 BoundSkill;替换后仍有字段含 ``{`` 说明参数缺失,
整个绑定返回 None,避免把占位符原文下发到设备端。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal, Optional

from app.protocol import Node

CursorState = Literal["pending", "issued", "verified", "failed"]

_BIND_FIELDS = ("input_text", "match_text", "text", "desc")


@dataclass
class SkillCursor:
    index: int = 0
    state: CursorState = "pending"

    def advance(self) -> None:
        self.index += 1
        self.state = "pending"

    def fail(self) -> None:
        self.state = "failed"


@dataclass
class SkillStep:
    op: str
    text: Optional[str] = None
    desc: Optional[str] = None
    view_id: Optional[str] = None
    class_name: Optional[str] = None
    index: Optional[int] = None
    input_text: Optional[str] = None
    # verify_title 步骤需要:期望的顶部标题子串(用于和当前
    # perception 顶部标题做匹配校验)。仅当 op == "verify_title" 时有意义。
    match_text: Optional[str] = None

    def to_dict(self) -> dict:
        d: dict[str, str | int] = {"op": self.op}
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
        if self.match_text is not None:
            d["match_text"] = self.match_text
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
            match_text=d.get("match_text"),
        )


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

    if step.op == "input" and nodes[node_index].editable:
        return True

    return False


@dataclass
class SkillTemplate:
    name: str
    params: list[str]
    app: str
    keywords: list[str]
    steps: list[SkillStep] = field(default_factory=list)


@dataclass
class BoundSkill:
    name: str
    app: str
    steps: list[SkillStep]

    @classmethod
    def bind(cls, tpl: SkillTemplate, bindings: dict[str, str]) -> "BoundSkill | None":
        bound_steps: list[SkillStep] = []
        for step in tpl.steps:
            values = {
                "input_text": step.input_text,
                "match_text": step.match_text,
                "text": step.text,
                "desc": step.desc,
            }
            for key, val in bindings.items():
                placeholder = "{" + key + "}"
                for f in _BIND_FIELDS:
                    v = values[f]
                    if v is not None:
                        values[f] = v.replace(placeholder, val)
            for f in _BIND_FIELDS:
                v = values[f]
                if v is not None and "{" in v:
                    logging.getLogger("phoneagent.skills").warning(
                        "[SKILL_BIND_MISSING_PARAM] skill=%s field=%s 参数未绑定，放弃技能",
                        tpl.name, f,
                    )
                    return None
            bound_steps.append(SkillStep(
                op=step.op,
                text=values["text"],
                desc=values["desc"],
                view_id=step.view_id,
                class_name=step.class_name,
                index=step.index,
                input_text=values["input_text"],
                match_text=values["match_text"],
            ))
        return cls(name=tpl.name, app=tpl.app, steps=bound_steps)

    def next_step(self, nodes: list[Node], index: int) -> Optional[dict]:
        if index < 0 or index >= len(self.steps):
            return None

        step = self.steps[index]

        # verify_title 步骤不下发 UI 动作,只让上游做标题校验。
        # 返回标记 dict(op="verify_title", expected_title=...),由决策层
        # 在校验后推进 cursor 或回退。
        if step.op == "verify_title":
            if not step.match_text:
                logging.getLogger("phoneagent.skills").warning(
                    "[VERIFY_TITLE_NO_TARGET] skill=%s cursor=%s verify_title 步骤缺少 match_text",
                    self.name, index,
                )
                return None
            return {"op": "verify_title", "expected_title": step.match_text}

        if step.index is not None and step.index < len(nodes):
            return step.to_dict()

        for i in range(len(nodes)):
            if match_node(step, nodes, i):
                return step.to_dict()

        logging.getLogger("phoneagent.skills").warning(
            "[SKILL_NO_MATCH] skill=%s cursor=%s step_op=%s 当前帧无节点匹配，回落 LLM 决策",
            self.name, index, step.op,
        )
        return None
