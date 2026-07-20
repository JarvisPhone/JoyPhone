"""场景层基础:AppProfile 数据模型、ScenarioPack 协议、场景选择。

AppProfile 是纯数据(pydantic BaseModel),承载单个 app 的 UI 识别特征
(title rid 关键词 / 发送按钮关键词 / 输入框 hint),替代旧
chat_title_helpers 的模块级硬编码;aliases 归位旧 app_goal_resolver
别名表中的应用条目。

ScenarioPack 是结构协议(typing.Protocol):一个场景 = 意图匹配 +
目标解析 + 技能模板 + 前后置策略 + UI profile。task.request 到达时
遍历注册的 pack 取 matches() 最高分装配 TaskContext;全 0 返回 None,
走纯 LLM 通用模式(内核安全策略仍在),不硬失败。
"""
from __future__ import annotations

from typing import Any, Protocol, Sequence

from pydantic import BaseModel


class AppProfile(BaseModel):
    """单个 app 的 UI 识别特征(纯数据,不含逻辑)。"""

    pkg: str
    aliases: list[str]
    title_rid_keywords: list[str]
    send_button_keywords: list[str]
    search_hints: list[str]
    message_input_hints: list[str]


class ScenarioPack(Protocol):
    """场景包协议:结构化约束,不做 isinstance 检查。"""

    name: str

    def matches(self, goal: str) -> float:
        """意图匹配得分,0 = 不命中。"""
        ...

    def resolve_target(self, goal: str) -> Any:
        """解析目标对象(app pkg + 目标标识符 + bindings)。"""
        ...

    def skills(self) -> list:
        """场景技能模板列表。"""
        ...

    def pre_policies(self) -> list:
        """决策前策略列表。"""
        ...

    def post_policies(self) -> list:
        """决策后策略列表。"""
        ...

    def ui_profile(self, pkg: str) -> AppProfile:
        """按 pkg 取 L2 UI 识别特征。"""
        ...


def select_scenario(packs: Sequence[ScenarioPack], goal: str) -> ScenarioPack | None:
    """取 matches() 最高分的 pack;全部 0 分(或无 pack)返回 None。"""
    best: ScenarioPack | None = None
    best_score = 0.0
    for pack in packs:
        score = pack.matches(goal)
        if score > best_score:
            best = pack
            best_score = score
    return best
