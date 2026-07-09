package com.example.phoneagent.net

import android.util.Log
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

    private companion object {
        const val TAG = "PhoneAgentWs"
    }

    private val listener = object : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            Log.i(TAG, "WS onOpen: ${response.code}")
      }

        override fun onMessage(webSocket: WebSocket, text: String) {
            Log.d(TAG, "WS onMessage: $text")
            dispatcher.dispatch(text)
        }

        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            Log.i(TAG, "WS onClosing: $code $reason")
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            Log.e(TAG, "WS onFailure: ${t.message}", t)
        }
    }

    fun connect(deviceId: String) {
        val url = "$baseUrl/ws/$deviceId"
        Log.i(TAG, "WS connecting: $url")
        val req = Request.Builder().url(url).build()
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