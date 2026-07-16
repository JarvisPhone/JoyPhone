package com.example.phoneagent.data

import com.example.phoneagent.domain.ActionLog
import com.example.phoneagent.domain.AgentStatus
import com.example.phoneagent.domain.ConnectionState
import com.example.phoneagent.domain.DebugInfo
import com.example.phoneagent.domain.SampleRequest
import com.example.phoneagent.domain.TaskState
import com.example.phoneagent.domain.TraceEvent
import com.example.phoneagent.domain.WsEventLog
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asSharedFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import javax.inject.Inject
import javax.inject.Singleton

/** Service 与 UI 的唯一状态桥梁。@Singleton 由 Hilt 保证进程内单例。 */
@Singleton
class AgentStateRepository @Inject constructor() {

    private companion object {
        const val MAX_LOG = 50
    }

    private val _status = MutableStateFlow(AgentStatus())
    val status: StateFlow<AgentStatus> = _status.asStateFlow()

    private val _debug = MutableStateFlow(DebugInfo())
    val debug: StateFlow<DebugInfo> = _debug.asStateFlow()

    fun updateAccessibility(granted: Boolean) {
        _status.update { it.copy(accessibilityGranted = granted) }
    }

    fun updateConnection(state: ConnectionState) {
        _status.update { it.copy(connection = state) }
    }

    fun updateTask(state: TaskState) {
        _status.update { it.copy(task = state) }
    }

    fun setDebugMeta(wsUrl: String, deviceId: String) {
        _debug.update { it.copy(wsUrl = wsUrl, deviceId = deviceId) }
    }

    fun setReconnectAttempts(n: Int) {
        _debug.update { it.copy(reconnectAttempts = n) }
    }

    fun appendActionLog(log: ActionLog) {
        _debug.update { it.copy(recentActions = (it.recentActions + log).takeLast(MAX_LOG)) }
    }

    fun appendWsEvent(log: WsEventLog) {
        _debug.update { it.copy(wsEvents = (it.wsEvents + log).takeLast(MAX_LOG)) }
    }

    fun appendTrace(event: TraceEvent) {
        _debug.update { it.copy(traceEvents = (it.traceEvents + event).takeLast(MAX_LOG)) }
    }

    // ---- 采样请求信号:UI -> Service。用 replay=0 的 SharedFlow,只通知在线的 Service。----
    private val _sampleRequests = MutableSharedFlow<SampleRequest>(extraBufferCapacity = 4)
    val sampleRequests: SharedFlow<SampleRequest> = _sampleRequests.asSharedFlow()

    /** UI 侧调用:发出一次采样请求。返回 false 表示当前无订阅者(Service 未连接)。 */
    fun requestSample(label: String, delaySeconds: Int): Boolean =
        _sampleRequests.tryEmit(SampleRequest(label, delaySeconds))
}