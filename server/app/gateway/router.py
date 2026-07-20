# server/app/gateway/router.py
"""上行路由:receive_text -> parse_uplink -> handle_uplink 循环。

parse_uplink 失败(ValueError:非 JSON / 非 object / 未知 type)时下发
TaskAbort(reason="invalid_uplink") 并结束本连接的路由循环;WebSocketDisconnect
不在此捕获,向上抛给 main.py 的连接入口。
"""
from __future__ import annotations

import logging

from app.gateway.connection import Connection, log_up
from app.protocol import TaskAbort, parse_uplink
from app.task.context import TaskStore
from app.task.handlers import HandlerDeps, handle_uplink

logger = logging.getLogger(__name__)


async def route_loop(conn: Connection, store: TaskStore, deps: HandlerDeps) -> None:
    while True:
        raw = await conn.receive_text()
        try:
            uplink = parse_uplink(raw)
        except ValueError as exc:
            logger.warning(
                "invalid uplink device=%s err=%s raw=%.200s",
                conn.device_id, exc, raw,
            )
            log_up("invalid", raw)
            task_id = store.current.task_id if store.current is not None else ""
            await conn.send(TaskAbort(taskId=task_id, reason="invalid_uplink"))
            return
        log_up(uplink.type, raw)
        await handle_uplink(uplink, store, conn, deps)
