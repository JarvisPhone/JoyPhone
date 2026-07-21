# server/app/gateway/connection.py
"""WebSocket 连接封装 + 通信日志(自 app.comm_log 迁入)。

Connection 是 handle_uplink 的 Conn 实现:send(model) 内部 log_down 后
websocket.send_text;receive_text 的 WebSocketDisconnect 由调用方
(gateway/router.py)处理。log_up/log_down/log_llm_req/log_llm_resp 与
_reset_for_test 原样迁自旧 comm_log.py。
"""
from __future__ import annotations

import logging
import os
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Protocol

from starlette.websockets import WebSocket

logger = logging.getLogger(__name__)


class JsonModel(Protocol):
    """可经 to_json() 序列化下行的协议模型。"""

    def to_json(self) -> str: ...


def _log_dir() -> Path:
    d = Path(os.getenv("PHONEAGENT_LOG_DIR",
                        Path(__file__).resolve().parents[2] / "logs"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _make_logger(name: str, filename: str) -> logging.Logger:
    lg = logging.getLogger(name)
    lg.setLevel(logging.INFO)
    lg.propagate = False
    if not lg.handlers:
        h = RotatingFileHandler(
            _log_dir() / filename, maxBytes=10 * 1024 * 1024,
            backupCount=5, encoding="utf-8",
        )
        h.setFormatter(logging.Formatter("%(message)s"))
        lg.addHandler(h)
    return lg


_comm_logger = _make_logger("phoneagent.comm", "comm.log")
_llm_logger = _make_logger("phoneagent.llmraw", "llm.log")


def _ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def log_up(msg_type: str, content: str) -> None:
    _comm_logger.info("%s|UP|%s|%s", _ts(), msg_type, content)


def log_down(msg_type: str, content: str) -> None:
    _comm_logger.info("%s|DOWN|%s|%s", _ts(), msg_type, content)


def log_llm_req(content: str) -> None:
    _llm_logger.info("%s|LLM-REQ|%s", _ts(), content)


def log_llm_resp(content: str) -> None:
    _llm_logger.info("%s|LLM-RESP|%s", _ts(), content)


def _reset_for_test(dir_path) -> None:
    """测试用:重建 handler 指向指定目录。"""
    global _comm_logger, _llm_logger
    os.environ["PHONEAGENT_LOG_DIR"] = str(dir_path)
    for name in ("phoneagent.comm", "phoneagent.llmraw"):
        lg = logging.getLogger(name)
        for h in list(lg.handlers):
            lg.removeHandler(h)
            h.close()
    _comm_logger = _make_logger("phoneagent.comm", "comm.log")
    _llm_logger = _make_logger("phoneagent.llmraw", "llm.log")


class Connection:
    """单设备 WebSocket 连接:accept/收发封装,send 内部 log_down。"""

    def __init__(self, websocket: WebSocket, device_id: str):
        self._ws = websocket
        self.device_id = device_id

    async def accept(self) -> None:
        await self._ws.accept()
        logger.info("WS connected device=%s", self.device_id)

    async def receive_text(self) -> str:
        return await self._ws.receive_text()

    async def send(self, model: JsonModel) -> None:
        payload = model.to_json()
        log_down(getattr(model, "type", "?"), payload)
        await self._ws.send_text(payload)

    async def close(self) -> None:
        try:
            await self._ws.close()
        except RuntimeError:
            pass
