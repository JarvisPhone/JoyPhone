"""TaskMetrics / MetricsCollector 新字段 + recent() 聚合测试。

覆盖 2026-07-26 P2 expansion Task 3 + Task 4:
- loop_guard_triggered_count / action_ok_count / action_total_count 字段
- record_loop_guard_trigger / record_action_result API
- action_success_rate 派生属性
- recent(limit) 聚合 metrics.log 末端
"""
import json
from pathlib import Path

from app.infra.metrics import MetricsCollector, TaskMetrics


def test_task_metrics_defaults_loop_guard_and_action_fields():
    m = TaskMetrics(task_id="t1", goal="x", pkg="com.x", start_ts=0)
    assert m.loop_guard_triggered_count == 0
    assert m.action_ok_count == 0
    assert m.action_total_count == 0


def test_action_success_rate_none_when_no_actions():
    m = TaskMetrics(task_id="t1", goal="x", pkg="com.x", start_ts=0)
    assert m.action_success_rate() is None


def test_action_success_rate_calculation():
    m = TaskMetrics(task_id="t1", goal="x", pkg="com.x", start_ts=0)
    m.action_total_count = 4
    m.action_ok_count = 3
    assert m.action_success_rate() == 0.75


def test_metrics_collector_records_loop_guard_trigger(tmp_path):
    c = MetricsCollector(log_dir=tmp_path)
    m = c.start_task("t1", goal="x", pkg="com.x")
    c.record_loop_guard_trigger("t1")
    c.record_loop_guard_trigger("t1")
    assert c._tasks["t1"].loop_guard_triggered_count == 2


def test_metrics_collector_records_action_result_ok(tmp_path):
    c = MetricsCollector(log_dir=tmp_path)
    c.start_task("t1", goal="x", pkg="com.x")
    c.record_action_result("t1", ok=True)
    c.record_action_result("t1", ok=True)
    c.record_action_result("t1", ok=False)
    t = c._tasks["t1"]
    assert t.action_total_count == 3
    assert t.action_ok_count == 2


def test_metrics_collector_records_unknown_task_id_silently(tmp_path):
    """未注册 task_id 调 record_* 不抛(防御性,避免端侧 uplink 异常挂掉服务)。"""
    c = MetricsCollector(log_dir=tmp_path)
    c.record_loop_guard_trigger("nonexistent")
    c.record_action_result("nonexistent", ok=True)
    assert "nonexistent" not in c._tasks


def test_recent_returns_empty_when_no_log(tmp_path):
    c = MetricsCollector(log_dir=tmp_path)
    assert c.recent(limit=10) == []


def test_recent_parses_finished_task_lines(tmp_path):
    c = MetricsCollector(log_dir=tmp_path)
    c.start_task("t1", goal="g1", pkg="com.x")
    c.record_step("t1")
    c.record_loop_guard_trigger("t1")
    c.record_action_result("t1", ok=True)
    c.record_action_result("t1", ok=False)
    c.finish_task("t1", "completed")

    items = c.recent(limit=10)
    assert len(items) == 1
    it = items[0]
    assert it["task_id"] == "t1"
    assert it["status"] == "completed"
    assert it["loop_guard_triggered_count"] == 1
    assert it["action_ok_count"] == 1
    assert it["action_total_count"] == 2
    assert it["action_success_rate"] == 0.5
    assert it["steps"] == 1


def test_recent_handles_corrupt_log_line(tmp_path):
    """metrics.log 含非 JSON / 非 task_metrics 行应跳过,不抛。"""
    c = MetricsCollector(log_dir=tmp_path)
    c.start_task("t1", goal="g1", pkg="com.x")
    c.finish_task("t1", "completed")
    # 写一行无效行
    log = tmp_path / "metrics.log"
    log.write_text(log.read_text() + "this is not json\n")

    items = c.recent(limit=10)
    # 无效行跳过,只剩 1 条有效
    assert len(items) == 1


def test_recent_respects_limit(tmp_path):
    c = MetricsCollector(log_dir=tmp_path)
    for i in range(5):
        c.start_task(f"t{i}", goal="g", pkg="com.x")
        c.finish_task(f"t{i}", "completed")
    items = c.recent(limit=3)
    assert len(items) == 3
    # 末尾 3 条 task_id 应是 t2, t3, t4(按写入顺序)
    assert [it["task_id"] for it in items] == ["t2", "t3", "t4"]