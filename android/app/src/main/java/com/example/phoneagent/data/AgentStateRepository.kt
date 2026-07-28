package com.example.phoneagent.data

import com.example.phoneagent.domain.ActionLog
import com.example.phoneagent.domain.AgentStatus
import com.example.phoneagent.domain.ConnectionState
import com.example.phoneagent.domain.DebugInfo
import com.example.phoneagent.domain.SampleRequest
import com.example.phoneagent.domain.TaskState
import com.example.phoneagent.domain.TaskUserIntent
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

    /**
     * 标记一条用户意图(无 taskId / taskId 无关):
     * - viewmodel.onSendGoal → SentGoal
     * - viewmodel.onCancelTask(taskId) → Cancelled
     *
     * Cancelled 不绑定 taskId: 在[TaskState.Running]状态时由 ViewModel 自己校验,
     * 确保 cancel 是针对当前 task;一旦置位,直到 consumeUserIntent 才清。
     */
    fun setUserIntent(intent: TaskUserIntent) {
        _status.update { it.copy(userIntent = intent) }
    }

    /**
     * 消费一条 Intent:Cancelled 等可消费意图置 None,SentGoal 等保持不变。
     * - 返回 true 表示该 intent 被消费掉 (Cancelled 一次性)
     * - 返回 false 表示 intent 未变或不该被消费
     *
     * 由下行协议处理器调用:收到 task.done / task.abort 后第一时间消费 Cancelled,
     * 防止 cancel race 把 TaskState 推回 Failed。
     */
    fun consumeUserIntent(intent: TaskUserIntent): Boolean {
        if (intent !is TaskUserIntent.Cancelled) return false
        val current = _status.value.userIntent
        if (current !is TaskUserIntent.Cancelled) return false
        _status.update { it.copy(userIntent = TaskUserIntent.None) }
        return true
    }

    /** 清空所有用户意图(Done/Failed 时由服务切回 Idle 同步清)。 */
    fun clearUserIntent() {
        _status.update { it.copy(userIntent = TaskUserIntent.None) }
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