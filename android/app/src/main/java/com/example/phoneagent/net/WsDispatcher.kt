package com.example.phoneagent.net

import com.example.phoneagent.protocol.DownAction
import com.example.phoneagent.protocol.DownTaskAbort
import com.example.phoneagent.protocol.DownTaskConfirm
import com.example.phoneagent.protocol.DownTaskDone
import com.example.phoneagent.protocol.DownTaskStart
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/**
 * 下行消息分发器：按 type 字段路由到回调。抽出为独立类以便纯单测。
 *
 * onTaskEnd 签名 (done, taskId, detail):
 * - done=true (task.done) → 服务端主动完成任务
 * - done=false (task.abort) → 服务端终止任务,detail 为 reason
 * - taskId 必传:即使被 user cancel 吃掉,UI 也要先看 Service 的 TaskState
 *   当前如何,再由 Repo.consumeUserIntent 决定要不要把 UI 拉回 Idle
 */
class WsDispatcher(
    private val onTaskStart: (goal: String, taskId: String) -> Unit,
    private val onAction: (DownAction) -> Unit,
    private val onTaskEnd: (done: Boolean, taskId: String, detail: String) -> Unit,
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
                onTaskEnd(true, m.taskId, m.result)
            }
            "task.abort" -> {
                val m = json.decodeFromString<DownTaskAbort>(text)
                onTaskEnd(false, m.taskId, m.reason)
            }
            "task.confirm" -> {
                val m = json.decodeFromString<DownTaskConfirm>(text)
                onTaskConfirm(m)
            }
            "heartbeat.ack" -> {
                // 心跳应答:端侧无需处理,静默忽略
            }
            else -> Unit
        }
    }
}