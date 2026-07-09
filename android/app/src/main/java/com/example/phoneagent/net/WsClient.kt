package com.example.phoneagent.net

import com.example.phoneagent.protocol.DownAction
import com.example.phoneagent.protocol.UplinkActionResult
import com.example.phoneagent.protocol.UplinkPerception
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener

class WsClient(
    private val baseUrl: String,
    onTaskStart: (goal: String, taskId: String) -> Unit,
    onAction: (DownAction) -> Unit,
    onTaskEnd: (reason: String) -> Unit,
) {
    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }
    private val client = OkHttpClient()
    private var ws: WebSocket? = null
    private val dispatcher = WsDispatcher(onTaskStart, onAction, onTaskEnd)

    private val listener = object : WebSocketListener() {
        override fun onMessage(webSocket: WebSocket, text: String) {
            dispatcher.dispatch(text)
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            // 连接失败：交由上层通过重连策略处理（MVP 暂仅记录）
        }
    }

    fun connect(deviceId: String) {
        val req = Request.Builder().url("$baseUrl/ws/$deviceId").build()
        ws = client.newWebSocket(req, listener)
    }

    fun sendPerception(p: UplinkPerception) {
        ws?.send(json.encodeToString(p))
    }

    fun sendActionResult(actionId: String, ok: Boolean, error: String? = null) {
        ws?.send(json.encodeToString(UplinkActionResult(actionId = actionId, ok = ok, error = error)))
    }

    fun close() {
        ws?.close(1000, "bye")
    }
}