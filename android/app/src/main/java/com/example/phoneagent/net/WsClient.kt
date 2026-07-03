package com.example.phoneagent.net

import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.WebSocket
import okhttp3.WebSocketListener

class WsClient(
    private val baseUrl: String,
    private val listener: WebSocketListener,
) {
    private val client = OkHttpClient()
    private var ws: WebSocket? = null

    fun connect(deviceId: String) {
        val req = Request.Builder().url("$baseUrl/ws/$deviceId").build()
        ws = client.newWebSocket(req, listener)
    }

    fun send(text: String) {
        ws?.send(text)
    }

    fun close() {
        ws?.close(1000, "bye")
    }
}