import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class TaskMetrics:
    task_id: str
    goal: str
    pkg: str
    start_ts: int
    end_ts: Optional[int] = None
    steps: int = 0
    llm_calls: int = 0
    skill_hits: int = 0
    cache_hits: int = 0
    loop_guard_triggered_count: int = 0
    action_ok_count: int = 0
    action_total_count: int = 0
    status: str = "running"
    error: Optional[str] = None

    def duration_s(self) -> Optional[float]:
        if self.end_ts is None:
            return None
        return self.end_ts - self.start_ts

    def action_success_rate(self) -> Optional[float]:
        """动作 ok 比率;action_total_count=0 时 None(未运行)。"""
        if self.action_total_count == 0:
            return None
        return self.action_ok_count / self.action_total_count

    def to_log_line(self) -> str:
        return json.dumps({
            "type": "task_metrics",
            **asdict(self),
            "duration_s": self.duration_s(),
            "timestamp": datetime.now().isoformat(),
        }, ensure_ascii=False)


class MetricsCollector:
    def __init__(self, log_dir: Path | None = None):
        self._log_dir = log_dir or Path(__file__).resolve().parents[2] / "data" / "metrics"
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._tasks: dict[str, TaskMetrics] = {}

    def start_task(self, task_id: str, goal: str, pkg: str = "") -> TaskMetrics:
        metrics = TaskMetrics(
            task_id=task_id,
            goal=goal,
            pkg=pkg,
            start_ts=int(time.time()),
        )
        self._tasks[task_id] = metrics
        self._log(f"Task started: {task_id}")
        return metrics

    def record_step(self, task_id: str) -> None:
        if task_id in self._tasks:
            self._tasks[task_id].steps += 1

    def record_llm_call(self, task_id: str) -> None:
        if task_id in self._tasks:
            self._tasks[task_id].llm_calls += 1

    def record_skill_hit(self, task_id: str) -> None:
        if task_id in self._tasks:
            self._tasks[task_id].skill_hits += 1

    def record_cache_hit(self, task_id: str) -> None:
        if task_id in self._tasks:
            self._tasks[task_id].cache_hits += 1

    def record_loop_guard_trigger(self, task_id: str) -> None:
        if task_id in self._tasks:
            self._tasks[task_id].loop_guard_triggered_count += 1

    def record_action_result(self, task_id: str, ok: bool) -> None:
        if task_id in self._tasks:
            t = self._tasks[task_id]
            t.action_total_count += 1
            if ok:
                t.action_ok_count += 1

    def finish_task(self, task_id: str, status: str, error: Optional[str] = None) -> None:
        if task_id in self._tasks:
            self._tasks[task_id].end_ts = int(time.time())
            self._tasks[task_id].status = status
            self._tasks[task_id].error = error
            self._flush_task(task_id)

    def _flush_task(self, task_id: str) -> None:
        if task_id not in self._tasks:
            return
        metrics = self._tasks[task_id]
        log_line = metrics.to_log_line()
        self._log(log_line)
        self._write_metrics_file(metrics)
        del self._tasks[task_id]

    def _log(self, message: str) -> None:
        log_file = Path(self._log_dir) / "metrics.log"
        with log_file.open("a", encoding="utf-8") as f:
            f.write(message + "\n")

    def _write_metrics_file(self, metrics: TaskMetrics) -> None:
        metrics_file = self._log_dir / f"{metrics.task_id}.json"
        metrics_file.write_text(json.dumps(asdict(metrics), ensure_ascii=False, indent=2))

    def get_active_tasks(self) -> list[TaskMetrics]:
        return list(self._tasks.values())

    def recent(self, limit: int = 10) -> list[dict]:
        """最近 N 个已完成任务的聚合:扫 metrics.log 末尾。

        metrics.log 每行格式:{type:task_metrics, task_id, ...} 或 "Task started: ..."
        聚合后排除 type 外的行,按时间戳排序取末 N。
        """
        log_file = Path(self._log_dir) / "metrics.log"
        if not log_file.exists():
            return []
        results: list[dict] = []
        try:
            with log_file.open("r", encoding="utf-8") as f:
                # 文件可能较大,只读末尾 64KB 足够取末 N 条
                f.seek(0, 2)
                size = f.tell()
                f.seek(max(0, size - 64 * 1024))
                buf = f.read()
        except OSError:
            return []
        for line in buf.splitlines():
            line = line.strip()
            if not line or not line.startswith("{"):
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") != "task_metrics":
                continue
            results.append({
                "task_id": obj.get("task_id"),
                "goal": obj.get("goal"),
                "pkg": obj.get("pkg"),
                "status": obj.get("status"),
                "duration_s": obj.get("duration_s"),
                "steps": obj.get("steps"),
                "llm_calls": obj.get("llm_calls"),
                "cache_hits": obj.get("cache_hits"),
                "skill_hits": obj.get("skill_hits"),
                "loop_guard_triggered_count": obj.get("loop_guard_triggered_count", 0),
                "action_ok_count": obj.get("action_ok_count", 0),
                "action_total_count": obj.get("action_total_count", 0),
                "action_success_rate": (
                    obj.get("action_ok_count", 0) / obj.get("action_total_count", 1)
                    if obj.get("action_total_count", 0) > 0 else None
                ),
                "error": obj.get("error"),
                "timestamp": obj.get("timestamp"),
            })
        # 末尾 = 最近;只取末 N
        return results[-limit:]


_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector
