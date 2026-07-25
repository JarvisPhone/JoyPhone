# server/app/infra/logging.py
"""统一应用进程日志:命令行简要 + 文件详细,互不干扰。

设计动机(2026-07-25):
- 现状:server 端 50+ 处 logger.info,但 main.py 没调 basicConfig —— 全部
  走 WARNING 默认,应用层 info 全部被吞。uvicorn 启动后只在 stdout 显示
  框架日志,看不到任务流。
- 现状:connection.py 的 log_up/log_down 把完整 JSON 字符串(sometimes 几 KB)
  原样落 comm.log,每行一个 JSON 串,人眼读 / grep 都难。
- 设计:拆两路 handler
    * console:单行概要,长消息自动截断 200 char,运行 dev 看任务流
    * file:   JSONL 含 ts/level/logger/msg,事后 jq 查 bug
- 通信专用日志(comm.log)保留两份:
    * comm.log.jsonl    原始 JSON(grep + jq 用,机器可读)
    * comm.log.summary  一行概要(人眼可读)
"""
from __future__ import annotations

import json
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


# 长消息截断阈值(console 专用,避免一行炸开)
_CONSOLE_MAX_LEN = 200


class ConciseConsoleFormatter(logging.Formatter):
    """单行概要:LEVEL | logger.name | message;长消息截断到 200 char。"""

    def format(self, record: logging.LogRecord) -> str:
        msg = record.getMessage()
        if record.exc_info:
            exc = self.formatException(record.exc_info)
            msg = f"{msg} | exc={exc}"
        if len(msg) > _CONSOLE_MAX_LEN:
            msg = msg[:_CONSOLE_MAX_LEN] + f"...(truncated,total={len(msg)})"
        return f"{record.levelname:5s} | {record.name:30s} | {msg}"


class DetailedFileFormatter(logging.Formatter):
    """JSONL:每行一个 JSON 对象,字段含 ts/level/logger/msg。"""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.%fZ"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # 文件路径 + 行号,便于定位
        if record.pathname:
            payload["src"] = f"{record.pathname}:{record.lineno}"
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(
    level: int = logging.INFO,
    log_dir: Path | None = None,
) -> Path:
    """统一初始化 root logger:stdout 概要 + 文件详细。

    同一 logger 上挂两个 handler,各自走自己的 formatter。
    多次调用幂等:已有 handler 不重复挂。

    Returns:
        实际日志目录路径(供调用方参考,例如写通信日志时复用)。
    """
    if log_dir is None:
        log_dir = Path("logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    # 清掉旧 handler(避免 uvicorn 或 reload 重复挂)
    for h in list(root.handlers):
        root.removeHandler(h)
    root.setLevel(level)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(ConciseConsoleFormatter())
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        log_dir / "server.jsonl",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(DetailedFileFormatter())
    root.addHandler(file_handler)

    # 让 connection.py 的 phoneagent.comm / phoneagent.llmraw 也能输出到 stdout
    # (它们自己挂了 RotatingFileHandler,默认 propagate=False,这里不动)
    return log_dir.resolve()
