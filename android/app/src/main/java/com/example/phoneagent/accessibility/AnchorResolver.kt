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
     *   1. text 精确匹配(最具业务语义,列表行通常唯一)
     *   2. desc 精确匹配
     *   3. rid 尾段精确匹配(仅文本层全空时兜底——列表行常复用同一容器 rid,
     *      rid 先行会把唯一文本行淹没在 N 个同 rid 兄弟里)
     *   文本层多命中且 rid 存在时,用 rid 在候选内收窄;
     *   仍多命中用 occurrence 选取,无 occurrence 判 Ambiguous。
     * editableOnly=true 时只在 editable 节点中解析(input 用)。
     */
    fun resolve(nodes: List<NodeDto>, anchor: Anchor, editableOnly: Boolean = false): ResolveResult {
        val pool = if (editableOnly) nodes.filter { it.editable } else nodes
        var candidates: List<NodeDto> = emptyList()
        if (anchor.text != null) {
            candidates = pool.filter { it.text?.trim() == anchor.text }
            if (candidates.isEmpty()) candidates = pool.filter { it.desc?.trim() == anchor.text }
        }
        if (candidates.isEmpty() && anchor.rid != null) {
            candidates = pool.filter { it.viewIdResourceName?.substringAfterLast('/') == anchor.rid }
        } else if (anchor.rid != null) {
            // rid 一致性约束(fail-closed):云端说的是「文本 X 且 rid Y 的节点」,
            // 文本命中但 rid 不符的是另一个节点(聊天页标题 vs 列表行同名),
            // 收窄为空必须 NotFound,绝不回落到 rid 不符的候选(真机八轮:
            // 名单行锚点在聊天页命中标题栏误入群设置)。
            candidates = candidates.filter { it.viewIdResourceName?.substringAfterLast('/') == anchor.rid }
        }
        if (candidates.isEmpty()) return ResolveResult.NotFound
        if (candidates.size == 1) return ResolveResult.Found(candidates[0])
        val occ = anchor.occurrence
        if (occ != null && occ in candidates.indices) return ResolveResult.Found(candidates[occ])
        return ResolveResult.Ambiguous(candidates.size)
    }
}
