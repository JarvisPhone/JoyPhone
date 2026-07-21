package com.example.phoneagent.net

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
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
import dagger.hilt.android.qualifiers.ApplicationContext
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
import kotlin.random.Random

/**
 * WebSocket 客户端：连接状态写入 Repository，支持无限重试 + 指数退避。
 * 下行消息仍经 WsDispatcher 分发到 Service 注入的回调。
 */
@Singleton
class WsClient @Inject constructor(
    private val repo: AgentStateRepository,
    private val json: Json,
    @ApplicationContext private val context: Context? = null,
) {
    private companion object {
        const val INITIAL_RETRY_DELAY_MS = 3000L
        const val MAX_RETRY_DELAY_MS = 60000L
        const val JITTER_FACTOR = 0.3
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
    private var retryJobStarted = false

    private var networkCallback: ConnectivityManager.NetworkCallback? = null
    private var isNetworkAvailable = true

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

        // 双连接防护：先关闭旧 socket
        ws?.close(1000, "restart")
        ws = null

        this.baseUrl = baseUrl
        this.deviceId = deviceId
        this.dispatcher = WsDispatcher(onTaskStart, onAction, onTaskEnd, onTaskConfirm)
        manuallyClosed = false
        retryCount = 0
        retryJobStarted = false
        repo.setDebugMeta(baseUrl, deviceId)

        // 注册网络状态监听
        registerNetworkCallback()

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
            retryJobStarted = false
            repo.setReconnectAttempts(0)
            repo.updateConnection(ConnectionState.CONNECTED)
            repo.appendWsEvent(WsEventLog(now(), "onOpen", "code=${response.code}"))
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            dispatcher?.dispatch(text)
        }

        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            repo.appendWsEvent(WsEventLog(now(), "onClosing", "$code $reason"))
            // 除非手动关闭，否则触发重连
            if (!manuallyClosed) {
                repo.updateConnection(ConnectionState.RECONNECTING)
                scheduleRetry()
            } else {
                repo.updateConnection(ConnectionState.DISCONNECTED)
            }
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            repo.appendWsEvent(WsEventLog(now(), "onFailure", t.message ?: "unknown"))
            // 防止重复触发重连
            if (!retryJobStarted) {
                scheduleRetry()
            }
        }
    }

    /**
     * 指数退避 + 抖动: 3s → 6s → 12s ... 封顶 60s
     * 无限重试，直到手动 close() 或成功连接
     */
    private fun scheduleRetry() {
        if (manuallyClosed) return
        if (retryJobStarted) return

        retryJobStarted = true
        retryCount++
        repo.setReconnectAttempts(retryCount)
        repo.updateConnection(ConnectionState.RECONNECTING)

        // 计算延迟: min(60s, 3s * 2^retryCount) + 抖动
        val baseDelay = minOf(
            INITIAL_RETRY_DELAY_MS * (1L shl (retryCount - 1)),
            MAX_RETRY_DELAY_MS
        )
        val jitter = (baseDelay * JITTER_FACTOR * Random.nextDouble()).toLong()
        val delay = baseDelay + jitter

        repo.appendWsEvent(WsEventLog(now(), "retry", "count=$retryCount delay=${delay}ms"))

        scope.launch {
            delay(delay)
            if (!manuallyClosed) {
                retryJobStarted = false
                connect()
            }
        }
    }

    /**
     * 网络恢复时立即重连（如果有待重试任务则取消当前延迟，立即重连）
     */
    private fun onNetworkAvailable() {
        if (manuallyClosed) return
        if (isNetworkAvailable) return

        isNetworkAvailable = true
        repo.appendWsEvent(WsEventLog(now(), "network", "available, triggering reconnect"))

        // 重置退避计数器，网络恢复后从最短延迟开始
        retryCount = 0
        repo.setReconnectAttempts(0)

        // 如果正在等待重试，立即触发
        if (retryJobStarted) {
            retryJobStarted = false
            connect()
        }
    }

    private fun onNetworkLost() {
        isNetworkAvailable = false
        repo.appendWsEvent(WsEventLog(now(), "network", "lost"))
    }

    private fun registerNetworkCallback() {
        if (context == null) return
        unregisterNetworkCallback()

        val connectivityManager = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        networkCallback = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) {
                onNetworkAvailable()
            }

            override fun onLost(network: Network) {
                onNetworkLost()
            }

            override fun onCapabilitiesChanged(
                network: Network,
                networkCapabilities: NetworkCapabilities,
            ) {
                val hasInternet = networkCapabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                if (hasInternet && !isNetworkAvailable) {
                    onNetworkAvailable()
                }
            }
        }

        val request = NetworkRequest.Builder()
            .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
            .build()
        connectivityManager.registerNetworkCallback(request, networkCallback!!)

        // 检查初始网络状态
        val activeNetwork = connectivityManager.activeNetwork
        val capabilities = connectivityManager.getNetworkCapabilities(activeNetwork)
        isNetworkAvailable = capabilities?.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) == true
    }

    private fun unregisterNetworkCallback() {
        networkCallback?.let { callback ->
            try {
                context?.let {
                    val connectivityManager = it.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
                    connectivityManager.unregisterNetworkCallback(callback)
                }
            } catch (_: Exception) {
                // 已注销或未注册
            }
            networkCallback = null
        }
    }

    /** 检查是否需要重连（仅在 DISCONNECTED 且非 manuallyClosed 时触发） */
    fun reconnectIfNeeded() {
        if (manuallyClosed) return
        val currentState = repo.status.value.connection
        if (currentState != ConnectionState.CONNECTED) {
            repo.appendWsEvent(WsEventLog(now(), "reconnectIfNeeded", "state=$currentState, triggering connect"))
            retryCount = 0
            retryJobStarted = false
            connect()
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
        retryJobStarted = false
        ws?.close(1000, "bye")
        ws = null
        unregisterNetworkCallback()
        repo.updateConnection(ConnectionState.DISCONNECTED)
    }

    /** 销毁客户端，释放资源 */
    fun destroy() {
        close()
        dispatcher = null
    }

    private fun now() = System.currentTimeMillis()
}