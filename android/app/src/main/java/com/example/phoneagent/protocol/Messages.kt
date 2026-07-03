package com.example.phoneagent.protocol

data class NodeDto(
    val id: String,
    val text: String? = null,
    val desc: String? = null,
    val className: String? = null,
    val bounds: List<Int>? = null,
    val clickable: Boolean = false,
    val editable: Boolean = false,
)

data class UplinkPerception(
    val type: String = "perception",
    val nodeTree: List<NodeDto>,
    val screenshot: String? = null,
    val pkg: String,
    val activity: String,
    val ts: Long,
)

data class DownAction(
    val type: String = "action",
    val actionId: String,
    val op: String,
    val params: Map<String, String> = emptyMap(),
) {
    fun toJson(): String {
        val paramsJson = params.entries.joinToString(",") { "\"${it.key}\":\"${it.value}\"" }
        return "{\"type\":\"$type\",\"actionId\":\"$actionId\",\"op\":\"$op\",\"params\":{$paramsJson}}"
    }
}