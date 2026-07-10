package com.example.phoneagent.protocol

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class NodeDto(
    val id: String,
    val text: String? = null,
    val desc: String? = null,
    val className: String? = null,
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