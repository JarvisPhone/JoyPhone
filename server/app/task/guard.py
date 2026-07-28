# server/app/task/guard.py
"""Uplink 入口守卫:检测 taskId 是否与当前 store 任务一致。

集中所有 taskId-bearing uplink 的「找当前任务」防御逻辑,避免每个 handler
复制粘贴同一段 ctx mismatch 检查。

典型场景:设备断连瞬间发 task.cancel,服务端未收到。重连后用旧 taskId
上行 → 服务端 store 上已是新 task → silent noop,不污染新任务。
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from app.task.context import TaskContext, TaskStore


class _TaskIdAware(Protocol):
    """任何携带 taskId 字段的上行消息都自动实现该协议(duck-typing)。"""

    taskId: str


def _extract_task_id(uplink: object) -> str | None:
    """安全提取 taskId:无 taskId 字段或 taskId 为空都返回 None。"""
    raw = getattr(uplink, "taskId", None)
    if not raw:  # None / 空串 / 0
        return None
    return str(raw)


def current_task_or_none(
    uplink: object, store: "TaskStore"
) -> "TaskContext | None":
    """taskId-bearing uplink 用:校验通过则返回 store.current,否则 None。

    - 携带 taskId 且与 store 上 ctx 一致 → 返回 store.current(TaskContext)
    - 携带 taskId 且 store 为空 / taskId 不一致 → 返回 None (silent noop)
    - 非 taskId-bearing uplink(心跳 / perception / sample / action.result 等)
      → 透传 store.current(可能 None,调用方自行 None-guard)

    pyright 类型提示依赖 store 是 TaskStore。
    """
    task_id = _extract_task_id(uplink)
    ctx = store.current

    if task_id is None:
        return ctx  # 非 taskId-bearing,透传 — 调用方 None-guard

    if ctx is None:
        logger.warning(
            "[TASK_ID_STALE] store empty, ignore uplink=%s task_id=%s",
            type(uplink).__name__, task_id,
        )
        return None

    if ctx.task_id != task_id:
        logger.warning(
            "[TASK_ID_STALE] taskId mismatch, ignore uplink=%s got=%s current=%s",
            type(uplink).__name__, task_id, ctx.task_id,
        )
        return None

    return ctx


def matches_current_task(uplink: object, store: "TaskStore") -> bool:
    """taskId 一致性布尔判定(给 taskId-bearing uplink 入口用)。

    语义:
    - 无 taskId uplink(心跳 / perception / sample / action.result) → True
      (这些 uplink 本就不需要 task 上下文,函数体内 ctx is None 防御仍保留)
    - 携带 taskId 且 ctx 匹配 → True
    - 携带 taskId 且 store 空 / 不匹配 → False (silent noop)

    注:matches 接受 ctx=None 返回 True 的非 taskId uplink 是有意设计 —
    这样 helper 调用方不需要感知「我手里是不是 taskId-bearing 的消息」。
    与 current_task_or_none() 语义分离:后者关心 ctx,前者关心 pass-or-noop。
    """
    task_id = _extract_task_id(uplink)
    if task_id is None:
        return True
    ctx = store.current
    if ctx is None:
        logger.warning(
            "[TASK_ID_STALE] store empty, ignore uplink=%s task_id=%s",
            type(uplink).__name__, task_id,
        )
        return False
    if ctx.task_id != task_id:
        logger.warning(
            "[TASK_ID_STALE] taskId mismatch, ignore uplink=%s got=%s current=%s",
            type(uplink).__name__, task_id, ctx.task_id,
        )
        return False
    return True
