package com.example.phoneagent.net

import com.example.phoneagent.protocol.DownAction
import com.example.phoneagent.protocol.DownHeartbeatAck
import com.example.phoneagent.protocol.DownTaskConfirm
import com.example.phoneagent.protocol.DownTaskDone
import com.example.phoneagent.protocol.DownTaskStart
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/**
 * 下行消息分发器：按 type 字段路由到回调。抽出为独立类以便纯单测。
 * onTaskEnd 的参数：done -> result，abort -> "abort:<reason>"。
 */
class WsDispatcher(
    private val onTaskStart: (goal: String, taskId: String) -> Unit,
    private val onAction: (DownAction) -> Unit,
    private val onTaskEnd: (reason: String) -> Unit,
    private val onTaskConfirm: (DownTaskConfirm) -> Unit = {},
) {
    private val json = Json { ignoreUnknownKeys = true }

    fun dispatch(text: String) {
        val type = runCatching {
            json.parseToJsonElement(text).jsonObject["type"]?.jsonPrimitive?.content
        }.getOrNull() ?: return

        when (type) {
            "task.start" -> {
                val m = json.decodeFromString<DownTaskStart>(text)
                onTaskStart(m.goal, m.taskId)
            }
            "action" -> onAction(json.decodeFromString<DownAction>(text))
            "task.done" -> {
                val m = json.decodeFromString<DownTaskDone>(text)
                onTaskEnd(m.result)
            }
            "task.abort" -> onTaskEnd("abort")
            "task.confirm" -> {
                val m = json.decodeFromString<DownTaskConfirm>(text)
                onTaskConfirm(m)
            }
            "heartbeat.ack" -> {
                // 心跳应答:仅解析保持 JSON 容错,端侧无需处理
                runCatching { json.decodeFromString<DownHeartbeatAck>(text) }
            }
            else -> Unit
        }
    }
}