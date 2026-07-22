# server/app/main.py
"""create_app:装配 engine/scenario_packs/metrics,挂载 /ws/{device_id}。

TaskStore 按 device_id 共享、跨连接存活:WS 只是传输层,断线重连是
移动网络常态,任务状态不能随连接生死(2026-07-22 真机事故:confirm
瞬间断连重连,confirm_response 落到新连接的空 store 被静默丢弃,
任务永久挂死)。env:
  PHONEAGENT_FAKE_LLM   JSON 列表,注入 FakeLLM 固定响应序列(回放/测试用)
  PHONEAGENT_MAX_STEPS  每任务步数预算,默认 Config.MAX_STEPS_DEFAULT
  SKILL_CACHE_PATH      技能缓存文件路径,默认 data/skill_cache.json
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from fastapi import FastAPI, WebSocket
from starlette.websockets import WebSocketDisconnect

from app.decision import DecisionEngine, SkillCache
from app.decision.llm import FakeLLM, build_llm
from app.gateway.connection import Connection
from app.gateway.router import route_loop
from app.infra.config import Config
from app.infra.metrics import get_metrics_collector
from app.protocol import PROTOCOL_VERSION
from app.scenario.send_message import SendMessagePack
from app.task.context import TaskStore
from app.task.handlers import HandlerDeps

logger = logging.getLogger(__name__)


def _build_llm():
    fake = os.getenv("PHONEAGENT_FAKE_LLM")
    if fake:
        return FakeLLM(json.loads(fake))
    return build_llm()


def create_app() -> FastAPI:
    app = FastAPI()
    max_steps = int(os.getenv("PHONEAGENT_MAX_STEPS", str(Config.MAX_STEPS_DEFAULT)))
    engine = DecisionEngine(
        llm=_build_llm(),
        cache=SkillCache(Path(os.getenv("SKILL_CACHE_PATH", "data/skill_cache.json"))),
        replay_enabled=Config.REPLAY_ENABLED,
    )
    deps = HandlerDeps(
        engine=engine,
        scenario_packs=[SendMessagePack()],
        metrics=get_metrics_collector(),
        max_steps=max_steps,
    )
    # 按设备共享 TaskStore:同一 device_id 重连后任务现场仍在,
    # confirm_response / action.result / perception 可跨连接续传。
    stores: dict[str, TaskStore] = {}

    @app.websocket("/ws/{device_id}")
    async def ws_gateway(websocket: WebSocket, device_id: str) -> None:
        raw_v = websocket.query_params.get("v")
        try:
            client_version = int(raw_v) if raw_v is not None else None
        except ValueError:
            client_version = None
        if client_version != PROTOCOL_VERSION:
            logger.warning(
                "WS 拒绝:协议版本不符 device=%s v=%s expect=%s",
                device_id, raw_v, PROTOCOL_VERSION,
            )
            await websocket.close(code=4402)
            return
        conn = Connection(websocket, device_id)
        await conn.accept()
        store = stores.setdefault(device_id, TaskStore())
        try:
            await route_loop(conn, store, deps)
        except WebSocketDisconnect:
            logger.info("WS disconnected device=%s", device_id)
        finally:
            await conn.close()

    return app
