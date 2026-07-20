# server/app/task/policies.py
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol, Sequence

from app.protocol import Action, Perception
from app.task.context import TaskContext

logger = logging.getLogger(__name__)

VerdictKind = Literal["continue", "terminate", "intercept"]


@dataclass(frozen=True)
class Verdict:
    """策略裁决结果:continue 放行 / terminate 终止任务 / intercept 下发动作。"""

    kind: VerdictKind
    reason: str = ""
    status: str = ""
    actions: list[Action] | None = None


def continue_() -> Verdict:
    return Verdict(kind="continue")


def terminate(reason: str, status: str) -> Verdict:
    return Verdict(kind="terminate", reason=reason, status=status)


def intercept(actions: list[Action]) -> Verdict:
    return Verdict(kind="intercept", actions=actions)


class Policy(Protocol):
    """策略协议:对感知帧与任务上下文做检查,返回裁决。"""

    name: str

    def inspect(self, frame: Perception | None, ctx: TaskContext) -> Verdict: ...


class BudgetPolicy:
    """步数预算:ctx.steps 达到 max_steps 即终止任务。"""

    name = "budget"

    def inspect(self, frame: Perception | None, ctx: TaskContext) -> Verdict:
        if ctx.steps >= ctx.max_steps:
            logger.info(
                "步数预算耗尽: task_id=%s steps=%s max_steps=%s",
                ctx.task_id,
                ctx.steps,
                ctx.max_steps,
            )
            return terminate("budget_exhausted", "aborted")
        return continue_()


class ConfirmTimeoutPolicy:
    """确认超时:AWAITING_CONFIRM 超过阈值即终止任务。"""

    name = "confirm_timeout"

    def inspect(self, frame: Perception | None, ctx: TaskContext) -> Verdict:
        if ctx.fsm.check_awaiting_confirm_timeout(datetime.now()):
            logger.info("确认等待超时: task_id=%s", ctx.task_id)
            return terminate("confirm_timeout", "aborted")
        return continue_()


def run_pipeline(
    policies: Sequence[Policy],
    frame: Perception | None,
    ctx: TaskContext,
) -> Verdict:
    """顺序执行策略,首个非 continue 裁决短路返回;全部通过则 continue。"""
    for policy in policies:
        verdict = policy.inspect(frame, ctx)
        if verdict.kind != "continue":
            logger.info(
                "策略管道短路: task_id=%s policy=%s kind=%s reason=%s",
                ctx.task_id,
                policy.name,
                verdict.kind,
                verdict.reason,
            )
            return verdict
    return continue_()
