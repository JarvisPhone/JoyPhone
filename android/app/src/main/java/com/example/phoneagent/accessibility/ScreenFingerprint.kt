package com.example.phoneagent.accessibility

import com.example.phoneagent.protocol.NodeDto

object ScreenFingerprint {
    fun of(nodes: List<NodeDto>): String =
        nodes.joinToString("|") { node ->
            "${node.text}~${node.desc}~${node.bounds?.joinToString(",") ?: ""}"
        }
}