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
import kotlinx.coroutines.Job
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
 * WebSocket 客户端：连接状态写入 Repository，无限重试 + 指数退避（带抖动）。
 * 下行消息仍经 WsDispatcher 分发到 Service 注入的回调。
 *
 * 并发约定：
 * - listener 内所有回调先做 stale 检查（webSocket !== ws 直接丢弃），
 *   旧 socket 的事件不得污染当前连接状态；
 * - 重试只有一个在途 Job（retryJob），"立即重连"通过取消该 Job 实现，
 *   不存在 boolean 标志无法取消 delay 的问题。
 */
@Singleton
class WsClient @Inject constructor(
    private val repo: AgentStateRepository,
    private val json: Json,
    @ApplicationContext private val context: Context? = null,
) {
    companion object {
        const val INITIAL_RETRY_DELAY_MS = 3000L
        const val MAX_RETRY_DELAY_MS = 60000L
        const val JITTER_FACTOR = 0.3
        const val PROTOCOL_VERSION = 2

        /** 退避移位上限：3s * 2^5 = 96s，与 MAX_RETRY_DELAY_MS 取小后稳定封顶在 60s；封顶避免移位溢出。 */
        private const val BACKOFF_SHIFT_CAP = 5

        /**
         * 指数退避基础延迟（不含抖动）: 3s → 6s → 12s → 24s → 48s → 60s 封顶。
         * retryCount 从 1 开始，任意大的值都安全（不会移位/乘法溢出）。
         */
        fun backoffDelayMs(retryCount: Int): Long {
            val shift = (retryCount - 1).coerceIn(0, BACKOFF_SHIFT_CAP)
            return minOf(INITIAL_RETRY_DELAY_MS shl shift, MAX_RETRY_DELAY_MS)
        }
    }

    private val client = OkHttpClient()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    /** 当前活跃 socket；listener 以此判定 stale。 */
    private var ws: WebSocket? = null
    private var dispatcher: WsDispatcher? = null
    /** 唯一在途的重试 Job；"立即重连" = 取消它 + connect()。 */
    private var retryJob: Job? = null

    private var baseUrl: String = ""
    private var deviceId: String = ""
    private var retryCount = 0
    private var manuallyClosed = false

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
        this.baseUrl = baseUrl
        this.deviceId = deviceId
        this.dispatcher = WsDispatcher(onTaskStart, onAction, onTaskEnd, onTaskConfirm)
        manuallyClosed = false
        retryCount = 0
        retryJob?.cancel()
        retryJob = null
        // 双连接防护：旧 socket 关闭，其后续事件由 listener 的 stale 检查丢弃
        ws?.close(1000, "restart")
        ws = null
        repo.setDebugMeta(baseUrl, deviceId)
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

        /** 非当前活跃 socket 的事件一律丢弃（并顺手关闭），防止旧连接污染状态。 */
        private fun isStale(webSocket: WebSocket): Boolean {
            if (webSocket === ws) return false
            webSocket.close(1000, "stale")
            return true
        }

        override fun onOpen(webSocket: WebSocket, response: Response) {
            if (isStale(webSocket)) return
            retryCount = 0
            retryJob?.cancel()
            retryJob = null
            repo.setReconnectAttempts(0)
            repo.updateConnection(ConnectionState.CONNECTED)
            repo.appendWsEvent(WsEventLog(now(), "onOpen", "code=${response.code}"))
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            if (isStale(webSocket)) return
            dispatcher?.dispatch(text)
        }

        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            if (isStale(webSocket)) return
            repo.appendWsEvent(WsEventLog(now(), "onClosing", "$code $reason"))
            // 应答 close 帧，完成关闭握手
            webSocket.close(code, null)
            if (!manuallyClosed) scheduleRetry()
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            if (isStale(webSocket)) return
            repo.appendWsEvent(WsEventLog(now(), "onFailure", t.message ?: "unknown"))
            scheduleRetry()
        }
    }

    /** 指数退避无限重试，直到手动 close() 或连接成功。 */
    private fun scheduleRetry() {
        if (manuallyClosed) return
        if (retryJob?.isActive == true) return

        retryCount++
        repo.setReconnectAttempts(retryCount)
        repo.updateConnection(ConnectionState.RECONNECTING)

        val baseDelay = backoffDelayMs(retryCount)
        val jitter = (baseDelay * JITTER_FACTOR * Random.nextDouble()).toLong()
        val delayMs = baseDelay + jitter
        repo.appendWsEvent(WsEventLog(now(), "retry", "count=$retryCount delay=${delayMs}ms"))

        retryJob = scope.launch {
            delay(delayMs)
            if (!manuallyClosed) connect()
        }
    }

    /**
     * 立即重连：取消在途退避、重置退避计数、关闭旧 socket（可能半开）后新建连接。
     * 网络恢复 / onResume 触发。
     */
    private fun retryNow(reason: String) {
        if (manuallyClosed) return
        // start() 未调用过(无障碍服务未绑定/未注入回调)时 baseUrl 为空,
        // 此时 MainActivity.onResume / 网络回调触发的重连无意义且 connect() 必崩
        if (baseUrl.isBlank()) return
        retryJob?.cancel()
        retryJob = null
        retryCount = 0
        repo.setReconnectAttempts(0)
        ws?.close(1000, reason)
        ws = null
        repo.appendWsEvent(WsEventLog(now(), "retryNow", reason))
        connect()
    }

    /** 检查是否需要重连（已连接时 no-op；未连接且非手动关闭时立即重连）。 */
    fun reconnectIfNeeded() {
        if (manuallyClosed) return
        val currentState = repo.status.value.connection
        if (currentState == ConnectionState.CONNECTED) return
        retryNow("reconnectIfNeeded state=$currentState")
    }

    private fun onNetworkAvailable() {
        if (isNetworkAvailable) return
        isNetworkAvailable = true
        // 网络刚恢复时 socket 可能处于半开状态，直接重建
        retryNow("network available")
    }

    private fun onNetworkLost() {
        isNetworkAvailable = false
        repo.appendWsEvent(WsEventLog(now(), "network", "lost"))
    }

    private fun registerNetworkCallback() {
        val ctx = context ?: return
        unregisterNetworkCallback()
        val connectivityManager = ctx.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager ?: return

        val callback = object : ConnectivityManager.NetworkCallback() {
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
                if (hasInternet) onNetworkAvailable()
            }
        }

        try {
            val request = NetworkRequest.Builder()
                .addCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET)
                .build()
            connectivityManager.registerNetworkCallback(request, callback)
            networkCallback = callback

            val capabilities = connectivityManager.getNetworkCapabilities(connectivityManager.activeNetwork)
            isNetworkAvailable = capabilities?.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) == true
        } catch (e: SecurityException) {
            repo.appendWsEvent(WsEventLog(now(), "network", "register callback failed: ${e.message}"))
        }
    }

    private fun unregisterNetworkCallback() {
        val callback = networkCallback ?: return
        networkCallback = null
        val ctx = context ?: return
        try {
            val connectivityManager = ctx.getSystemService(Context.CONNECTIVITY_SERVICE) as? ConnectivityManager
            connectivityManager?.unregisterNetworkCallback(callback)
        } catch (_: Exception) {
            // 已注销或未注册
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
        retryJob?.cancel()
        retryJob = null
        ws?.close(1000, "bye")
        ws = null
        unregisterNetworkCallback()
        repo.updateConnection(ConnectionState.DISCONNECTED)
    }

    /** 销毁客户端，释放资源。 */
    fun destroy() {
        close()
        dispatcher = null
    }

    private fun now() = System.currentTimeMillis()
}
