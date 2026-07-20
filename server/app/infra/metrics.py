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
    status: str = "running"
    error: Optional[str] = None

    def duration_s(self) -> Optional[float]:
        if self.end_ts is None:
            return None
        return self.end_ts - self.start_ts

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


_metrics_collector: Optional[MetricsCollector] = None


def get_metrics_collector() -> MetricsCollector:
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = MetricsCollector()
    return _metrics_collector
