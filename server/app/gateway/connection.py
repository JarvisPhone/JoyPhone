# server/app/gateway/connection.py
"""WebSocket 连接封装 + 通信日志(自 app.comm_log 迁入)。

Connection 是 handle_uplink 的 Conn 实现:send(model) 内部 log_down 后
websocket.send_text;receive_text 的 WebSocketDisconnect 由调用方
(gateway/router.py)处理。log_up/log_down/log_llm_req/log_llm_resp 与
_reset_for_test 原样迁自旧 comm_log.py。
"""
from __future__ import annotations

import json
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
_comm_summary_logger = _make_logger("phoneagent.comm.summary", "comm.log.summary")
_llm_logger = _make_logger("phoneagent.llmraw", "llm.log")


def _ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _summary_of(msg_type: str, payload: str) -> str:
    """从 JSON 字符串提取关键字段,生成单行可读摘要。

    失败兜底:返回 msg_type + 截断原始字符串(避免破坏日志格式)。
    """
    try:
        obj = json.loads(payload)
    except (ValueError, TypeError):
        return f"{msg_type} <invalid json> {payload[:120]}"

    if msg_type == "perception":
        nodes = obj.get("nodes") or []
        return f"perception pkg={obj.get('pkg', '')} activity={obj.get('activity', '')} nodes={len(nodes)}"
    if msg_type == "action.result":
        return f"action.result ok={obj.get('ok')} error={obj.get('error', '')} actionId={obj.get('actionId', '')}"
    if msg_type == "task.start":
        return f"task.start taskId={obj.get('taskId', '')} goal={obj.get('goal', '')[:60]}"
    if msg_type == "action":
        params = obj.get("params") or {}
        return f"action op={obj.get('op', '')} match_text={params.get('match_text', '')[:40]}"
    if msg_type == "task.end":
        return f"task.end done={obj.get('done')} detail={obj.get('detail', '')[:60]}"
    if msg_type == "task.confirm":
        return f"task.confirm target={obj.get('target', '')} msg={obj.get('message', '')[:60]}"
    if msg_type == "device.hello":
        caps = obj.get("capabilities") or {}
        return f"device.hello deviceId={obj.get('deviceId', '')} caps={','.join(sorted(caps.keys()))}"
    if msg_type == "event.newMessage":
        return f"event.newMessage from={obj.get('from', '')} text={obj.get('text', '')[:60]}"
    # 其它类型:msg_type + 长度,避免刷屏
    return f"{msg_type} (fields={list(obj.keys())[:6]})"


def log_up(msg_type: str, content: str) -> None:
    _comm_logger.info("%s|UP|%s|%s", _ts(), msg_type, content)
    _comm_summary_logger.info("%s UP %s", _ts(), _summary_of(msg_type, content))


def log_down(msg_type: str, content: str) -> None:
    _comm_logger.info("%s|DOWN|%s|%s", _ts(), msg_type, content)
    _comm_summary_logger.info("%s DOWN %s", _ts(), _summary_of(msg_type, content))


def log_llm_req(content: str) -> None:
    _llm_logger.info("%s|LLM-REQ|%s", _ts(), content)


def log_llm_resp(content: str) -> None:
    _llm_logger.info("%s|LLM-RESP|%s", _ts(), content)


def _reset_for_test(dir_path) -> None:
    """测试用:重建 handler 指向指定目录。"""
    global _comm_logger, _comm_summary_logger, _llm_logger
    os.environ["PHONEAGENT_LOG_DIR"] = str(dir_path)
    for name in ("phoneagent.comm", "phoneagent.comm.summary", "phoneagent.llmraw"):
        lg = logging.getLogger(name)
        for h in list(lg.handlers):
            lg.removeHandler(h)
            h.close()
    _comm_logger = _make_logger("phoneagent.comm", "comm.log")
    _comm_summary_logger = _make_logger("phoneagent.comm.summary", "comm.log.summary")
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
