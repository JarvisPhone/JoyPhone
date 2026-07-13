package com.example.phoneagent.accessibility

import com.example.phoneagent.protocol.NodeDto

/**
 * 屏幕指纹：把节点列表映射为可比较字符串，用于判断翻屏前后是否同屏(到底检测)。
 *
 * 分隔符碰撞修复：text/desc 来自任意 UI 文本，可能含 ~ | , 等字符。
 * 若用普通分隔符拼接，不同屏幕可能产生相同指纹而误判 atEnd。
 * 这里对每个可变长字段做「长度前缀化」编码——先写字段字符长度再写内容，
 * 长度用固定分隔符隔开。由于长度精确界定每个字段边界，内容里出现任何字符都不会碰撞。
 * 同时用 -1 长度显式表示 null，从而区分 null 与空串
 */
object ScreenFingerprint {
    fun of(nodes: List<NodeDto>): String =
        nodes.joinToString("") { node ->
            val boundsStr = node.bounds?.joinToString(",")
            encode(node.text) + encode(node.desc) + encode(boundsStr)
        }

    /** 长度前缀化：null -> "-1:"；否则 "<charLen>:<value>"。 */
    private fun encode(value: String?): String {
        if (value == null) return "-1:"
        return "${value.length}:$value"
    }
}