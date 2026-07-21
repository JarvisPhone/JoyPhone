package com.example.phoneagent.net

import com.example.phoneagent.data.AgentStateRepository
import com.example.phoneagent.domain.ConnectionState
import com.example.phoneagent.domain.WsEventLog
import com.example.phoneagent.protocol.DownAction
import com.example.phoneagent.protocol.DownTaskConfirm
import com.example.phoneagent.protocol.UplinkActionResult
import com.example.phoneagent.protocol.UplinkConfirmResponse
import com.example.phoneagent.protocol.UplinkPerception
import com.example.phoneagent.protocol.UplinkSampleCapture
import com.example.phoneagent.protocol.UplinkTaskRequest
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import javax.inject.Inject
import javax.inject.Singleton

/**
 * WebSocket 客户端：连接状态写入 Repository，onFailure 触发有限重试。
 * 下行消息仍经 WsDispatcher 分发到 Service 注入的回调。
 */
@Singleton
class WsClient @Inject constructor(
    private val repo: AgentStateRepository,
    private val json: Json,
) {
    private companion object {
        const val MAX_RETRY = 5
        const val RETRY_DELAY_MS = 3000L
        const val PROTOCOL_VERSION = 2
    }

    private val client = OkHttpClient()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var ws: WebSocket? = null
    private var dispatcher: WsDispatcher? = null

    private var baseUrl: String = ""
    private var deviceId: String = ""
    private var retryCount = 0
    private var manuallyClosed = false

    /** 由 Service 注入下行回调后调用。 */
    fun start(
        baseUrl: String,
        deviceId: String,
        onTaskStart: (goal: String, taskId: String) -> Unit,
        onAction: (DownAction) -> Unit,
        onTaskEnd: (reason: String) -> Unit,
        onTaskConfirm: (DownTaskConfirm) -> Unit = {},
    ) {
        require(deviceId.isNotBlank()) { "deviceId cannot be blank" }
        this.baseUrl = baseUrl
        this.deviceId = deviceId
        this.dispatcher = WsDispatcher(onTaskStart, onAction, onTaskEnd, onTaskConfirm)
        manuallyClosed = false
        retryCount = 0
        repo.setDebugMeta(baseUrl, deviceId)
        connect()
    }

    private fun connect() {
        repo.updateConnection(
            if (retryCount == 0) ConnectionState.CONNECTING else ConnectionState.RECONNECTING
        )
        repo.appendWsEvent(WsEventLog(now(), "connecting", "$baseUrl/ws/$deviceId?v=$PROTOCOL_VERSION"))
        val req = Request.Builder().url("$baseUrl/ws/$deviceId?v=$PROTOCOL_VERSION").build()
        ws = client.newWebSocket(req, listener)
    }

    private val listener = object : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            retryCount = 0
            repo.setReconnectAttempts(0)
            repo.updateConnection(ConnectionState.CONNECTED)
            repo.appendWsEvent(WsEventLog(now(), "onOpen", "code=${response.code}"))
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            dispatcher?.dispatch(text)
        }

        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            repo.updateConnection(ConnectionState.DISCONNECTED)
            repo.appendWsEvent(WsEventLog(now(), "onClosing", "$code $reason"))
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            repo.appendWsEvent(WsEventLog(now(), "onFailure", t.message ?: "unknown"))
            scheduleRetry()
        }
    }

    private fun scheduleRetry() {
        if (manuallyClosed) return
        if (retryCount >= MAX_RETRY) {
            repo.updateConnection(ConnectionState.DISCONNECTED)
            repo.appendWsEvent(WsEventLog(now(), "retry", "达上限 $MAX_RETRY，停止重连"))
            return
        }
        retryCount++
        repo.setReconnectAttempts(retryCount)
        repo.updateConnection(ConnectionState.RECONNECTING)
        scope.launch {
            delay(RETRY_DELAY_MS)
            if (!manuallyClosed) connect()
        }
    }

    fun sendPerception(p: UplinkPerception) {
        ws?.send(json.encodeToString(p))
    }

    fun sendActionResult(actionId: String, ok: Boolean, seq: Int, error: String? = null) {
        ws?.send(json.encodeToString(UplinkActionResult(actionId = actionId, ok = ok, seq = seq, error = error)))
    }

    fun sendTaskRequest(goal: String) {
        ws?.send(json.encodeToString(UplinkTaskRequest(goal = goal)))
    }

    /** 发送探针采样帧。采样与决策解耦,不影响任务链路。 */
    fun sendSampleCapture(msg: UplinkSampleCapture) {
        ws?.send(json.encodeToString(msg))
    }

    /** 发送 Toast 确认响应。approved=true 表示 5 秒内未切走 / 用户已确认,false 表示取消。 */
    fun sendConfirmResponse(taskId: String, confirmId: String, approved: Boolean, reason: String = "") {
        ws?.send(
            json.encodeToString(
                UplinkConfirmResponse(
                    taskId = taskId,
                    confirmId = confirmId,
                    approved = approved,
                    reason = reason,
                    ts = System.currentTimeMillis(),
                )
            )
        )
    }

    fun close() {
        manuallyClosed = true
        ws?.close(1000, "bye")
        ws = null
        repo.updateConnection(ConnectionState.DISCONNECTED)
    }

    private fun now() = System.currentTimeMillis()
}