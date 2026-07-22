package com.example.phoneagent.accessibility

import com.example.phoneagent.protocol.NodeDto

/**
 * 语义锚点:tap/input 的定位依据。
 *
 * 云端不再下发坐标(坐标随帧过期会点歪,2026-07-22 错群事故根因),
 * 端侧执行瞬间按锚点在「当前实时树」上重新定位,fail-closed:
 * 匹配不到/有歧义直接报错,绝不模糊猜测(子串匹配会误中同名磁贴/群名,禁用)。
 */
data class Anchor(val text: String?, val rid: String?, val occurrence: Int?)

sealed interface ResolveResult {
    data class Found(val node: NodeDto) : ResolveResult
    data object NotFound : ResolveResult
    data class Ambiguous(val count: Int) : ResolveResult
}

object AnchorResolver {

    /** 从 action params 提取锚点;match_text/match_rid 都没有返回 null(视为 anchor_missing)。 */
    fun fromParams(params: Map<String, String>): Anchor? {
        val text = params["match_text"]?.trim().orEmpty()
        val rid = params["match_rid"]?.trim().orEmpty()
        if (text.isEmpty() && rid.isEmpty()) return null
        val occurrence = params["occurrence"]?.trim()?.toIntOrNull()
        return Anchor(text.ifEmpty { null }, rid.ifEmpty { null }, occurrence)
    }

    /**
     * 解析阶梯(与云端 scenario/ui.resolve_anchor_node 同一语义):
     *   1. rid 尾段精确匹配
     *   2. text 精确匹配
     *   3. desc 精确匹配
     * 单层多命中时用 occurrence 选取,无 occurrence 判 Ambiguous。
     * editableOnly=true 时只在 editable 节点中解析(input 用)。
     */
    fun resolve(nodes: List<NodeDto>, anchor: Anchor, editableOnly: Boolean = false): ResolveResult {
        val pool = if (editableOnly) nodes.filter { it.editable } else nodes
        val matches: List<NodeDto> = when {
            anchor.rid != null ->
                pool.filter { it.viewIdResourceName?.substringAfterLast('/') == anchor.rid }
            anchor.text != null -> {
                val byText = pool.filter { it.text?.trim() == anchor.text }
                byText.ifEmpty { pool.filter { it.desc?.trim() == anchor.text } }
            }
            else -> emptyList()
        }
        if (matches.isEmpty()) return ResolveResult.NotFound
        if (matches.size == 1) return ResolveResult.Found(matches[0])
        val occ = anchor.occurrence
        if (occ != null && occ in matches.indices) return ResolveResult.Found(matches[occ])
        return ResolveResult.Ambiguous(matches.size)
    }
}
