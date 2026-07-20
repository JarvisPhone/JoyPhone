"""决策结果类型。

actions 禁止为空:空 actions 的决策在下行时会让设备端无所适从,
在构造期就断言掉,让 bug 暴露在服务端而非真机上。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.protocol import Action

DecisionSource = Literal["cache", "skill", "pkg_guard", "llm"]


@dataclass
class Decision:
    actions: list[Action]
    source: DecisionSource
    meta: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        assert self.actions, "Decision.actions must not be empty"
