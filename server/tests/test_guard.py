"""Uplink 入口守卫 matches_current_task / current_task_or_none 的纯单测。

不需要走真实 TaskStore/handler,用 duck-typed stub 验逻辑即可。
"""
from types import SimpleNamespace

from app.task.context import TaskStore
from app.task.guard import current_task_or_none, matches_current_task


# --- 辅助:构造 taskId-bearing uplink stub ---


def _uplink(task_id: str | None = "t-1"):
    return SimpleNamespace(type="x", taskId=task_id)


def _no_task_id_uplink():
    """无 taskId 字段的上行(perception / sample / newMessage / device.hello)。"""
    return SimpleNamespace(type="perception")


# ---- matches_current_task ----


def test_no_task_id_attribute_passes():
    """心跳 / perception 等无 taskId 上行 → True,不检查 store。"""
    store = TaskStore()  # 空 store
    assert matches_current_task(_no_task_id_uplink(), store) is True


def test_empty_task_id_passes():
    """taskId 为空串视为无字段 → True,放过。"""
    store = TaskStore()
    assert matches_current_task(_uplink(task_id=""), store) is True


def test_store_empty_returns_false_and_logs(caplog):
    """store 为空 → False + 警告日志。"""
    import logging
    store = TaskStore()
    with caplog.at_level(logging.WARNING, logger="app.task.guard"):
        result = matches_current_task(_uplink(task_id="t-1"), store)
    assert result is False
    assert "TASK_ID_STALE" in caplog.text
    assert "store empty" in caplog.text


def test_task_id_match_returns_true():
    """store 上有 task 且 taskId 一致 → True。"""
    store = TaskStore()
    ctx = store.new_task(goal="g")
    assert matches_current_task(_uplink(task_id=ctx.task_id), store) is True


def test_task_id_mismatch_returns_false_and_logs(caplog):
    """旧 taskId 上行 → False + 警告日志,不污染新 ctx。"""
    import logging
    store = TaskStore()
    new_ctx = store.new_task(goal="g")
    with caplog.at_level(logging.WARNING, logger="app.task.guard"):
        result = matches_current_task(_uplink(task_id="t-stale"), store)
    assert result is False
    assert "TASK_ID_STALE" in caplog.text
    assert "taskId mismatch" in caplog.text
    # 新 ctx 仍在 store 上,未被污染
    assert store.current is new_ctx


# ---- current_task_or_none ----


def test_current_task_or_none_match_returns_ctx():
    store = TaskStore()
    ctx = store.new_task(goal="g")
    assert current_task_or_none(_uplink(task_id=ctx.task_id), store) is ctx


def test_current_task_or_none_mismatch_returns_none():
    store = TaskStore()
    store.new_task(goal="g")
    assert current_task_or_none(_uplink(task_id="t-stale"), store) is None


def test_current_task_or_none_empty_store_returns_none():
    store = TaskStore()
    assert current_task_or_none(_uplink(task_id="t-1"), store) is None


def test_current_task_or_none_passes_through_for_non_taskid_uplink():
    """无 taskId uplink 透传 store.current(可能为 None,调用方 None-guard)。"""
    store_empty = TaskStore()
    store_with_ctx = TaskStore()
    ctx = store_with_ctx.new_task(goal="g")
    assert current_task_or_none(_no_task_id_uplink(), store_empty) is None
    assert current_task_or_none(_no_task_id_uplink(), store_with_ctx) is ctx
