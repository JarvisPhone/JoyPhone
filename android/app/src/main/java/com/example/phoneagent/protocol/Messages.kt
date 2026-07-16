package com.example.phoneagent.protocol

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class NodeDto(
    val id: String,
    val text: String? = null,
    val desc: String? = null,
    val className: String? = null,
    val viewIdResourceName: String? = null,
    val bounds: List<Int>? = null,
    val clickable: Boolean = false,
    val editable: Boolean = false,
)

@Serializable
data class UplinkPerception(
    val type: String = "perception",
    val nodeTree: List<NodeDto>,
    val screenshot: String? = null,
    val pkg: String,
    val activity: String,
    val ts: Long,
)

@Serializable
data class UplinkActionResult(
    val type: String = "action.result",
    val actionId: String,
    val ok: Boolean,
    val atEnd: Boolean = false,
    val error: String? = null,
    val ts: Long = 0,
)

@Serializable
data class UplinkHeartbeat(
    val type: String = "heartbeat",
    val deviceId: String,
    val ts: Long = 0,
)

@Serializable
data class UplinkTaskRequest(
    val type: String = "task.request",
    val goal: String,
)

@Serializable
data class UplinkSampleCapture(
    val type: String = "sample.capture",
    val label: String,
    val nodeTree: List<NodeDto>,
    val pkg: String,
    val activity: String,
    val ts: Long,
    val device: String = "",
)

@Serializable
data class DownAction(
    val type: String = "action",
    val actionId: String,
    val op: String,
    val params: Map<String, String> = emptyMap(),
)

@Serializable
data class DownTaskStart(
    val type: String = "task.start",
    val taskId: String,
    val goal: String,
    val target: String,
)

@Serializable
data class DownTaskDone(
    val type: String = "task.done",
    val taskId: String,
    val result: String,
    val summary: String = "",
)

@Serializable
data class DownTaskAbort(
    val type: String = "task.abort",
    val taskId: String,
    val reason: String,
)

/** 下行:发消息前 Toast 确认请求。云端在检测到「即将点发送」时拦截。 */
@Serializable
data class DownTaskConfirm(
    val type: String = "task.confirm",
    val taskId: String,
    val confirmId: String,
    val target: String,
    val message: String,
    val timeoutMs: Int,
)

/** 上行:Toast 5 秒倒计时结束 / 飞书被切走(由云端感知)后的响应。 */
@Serializable
data class UplinkConfirmResponse(
    val type: String = "task.confirm_response",
    val taskId: String,
    val confirmId: String,
    val approved: Boolean,
    val reason: String = "",
    val ts: Long = 0,
)