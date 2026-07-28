package com.example.phoneagent.domain

/** WS 连接状态。 */
enum class ConnectionState { DISCONNECTED, CONNECTING, CONNECTED, RECONNECTING }

/**
 * 用户对当前任务的主观意图（与下行协议状态解耦）。
 *
 * 设计目的：client 端任务状态本质上是「协议下行驱动的 TaskState」与「用户上行
 * 触发的意图」的混合。两者可能短暂不一致（如 cancel race：
 * 端侧乐观更新 Idle 但下行 task.abort 到达），引入本枚举避免 TaskState
 * 字段被多个语义挤占。
 *
 * 状态语义：
 * - [None]   没有任何用户意图；UI 由下行协议 TaskState 主导
 * - [SentGoal] 上行 task.request 后、收到 task.start 前的瞬态；UI 显示「等待开始」
 * - [Cancelled] 用户主动取消，UI 已切 Idle；收到下行 task.done / task.abort 后
 *   由 Repo 消费并清回 [None]，防止 cancel race 把 UI 推回 Failed
 */
sealed interface TaskUserIntent {
    data object None : TaskUserIntent
    data object SentGoal : TaskUserIntent
    data object Cancelled : TaskUserIntent
}

/** 任务执行状态(由下行协议决定)。 */
sealed interface TaskState {
    data object Idle : TaskState
    /** 执行中:携带 taskId 供「中止」按钮发起 task.cancel 时使用(2026-07-26 加)。 */
    data class Running(val description: String, val taskId: String = "") : TaskState
    data class Done(val summary: String) : TaskState
    data class Failed(val reason: String) : TaskState
}

/**
 * 面向用户的聚合状态。
 *
 * UI 合成规则([combineTaskDisplay])：
 *   TaskUserIntent.Cancelled → 显示 "Idle (cancelled)" (取消已发,不显示 Done/Failed)
 *   否则                          → 显示 TaskState 原值
 *
 * 这样取消 race 中下行 task.abort 到达 Repo 时,被 Cancelled 吸收
 * (Repo.consumeUserIntent 后清回 None),绝不污染 TaskState。
 */
data class AgentStatus(
    val accessibilityGranted: Boolean = false,
    val connection: ConnectionState = ConnectionState.DISCONNECTED,
    val task: TaskState = TaskState.Idle,
    val userIntent: TaskUserIntent = TaskUserIntent.None,
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