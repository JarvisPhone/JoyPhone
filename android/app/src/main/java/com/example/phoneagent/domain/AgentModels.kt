package com.example.phoneagent.domain

/** WS 连接状态。 */
enum class ConnectionState { DISCONNECTED, CONNECTING, CONNECTED, RECONNECTING }

/** 任务执行状态。 */
sealed interface TaskState {
    data object Idle : TaskState
    data class Running(val description: String) : TaskState
}

/** 面向用户的聚合状态。 */
data class AgentStatus(
    val accessibilityGranted: Boolean = false,
    val connection: ConnectionState = ConnectionState.DISCONNECTED,
    val task: TaskState = TaskState.Idle,
)

/** 单条动作流水（调试用）。 */
data class ActionLog(
    val ts: Long,
    val op: String,
    val ok: Boolean,
    val detail: String = "",
)

/** 单条 WS 底层事件（调试用）。 */
data class WsEventLog(
    val ts: Long,
    val event: String,
    val detail: String = "",
)

/** 事件流方向：上行↑ / 下行↓ / 本地信息· */
enum class TraceDirection { UP, DOWN, INFO }

/** 统一收发事件（app 内实时日志流用）。 */
data class TraceEvent(
    val ts: Long,
    val direction: TraceDirection,
    val kind: String,
    val summary: String = "",
)

/** 调试专用信息（后门才展示）。 */
data class DebugInfo(
    val wsUrl: String = "",
    val deviceId: String = "",
    val recentActions: List<ActionLog> = emptyList(),
    val wsEvents: List<WsEventLog> = emptyList(),
    val reconnectAttempts: Int = 0,
    val traceEvents: List<TraceEvent> = emptyList(),
)