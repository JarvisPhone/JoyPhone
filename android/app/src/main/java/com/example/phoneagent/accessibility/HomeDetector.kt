package com.example.phoneagent.accessibility

import com.example.phoneagent.protocol.NodeDto

/**
 * 桌面归位判据(纯函数，可单测)。
 *
 * ColorOS 负一屏 ROM 真机双帧证据：
 * - 桌面第一屏：launcher workspace 节点 bounds 左边界==0(满屏对齐 [0,0,1080,2374])
 * - 停在负一屏/中间态：workspace 节点被负一屏往右推挤，左边界>0(如 [43,95,1037,2279])
 *
 * 负一屏本身是 launcher 内嵌的独立渲染层，不进无障碍节点树，无法直接识别；
 * 但「是否已到桌面第一屏」可通过 workspace 满屏对齐 100% 可靠判定，从而绕开负一屏识别。
 */
object HomeDetector {

    private const val WORKSPACE_SUFFIX = ":id/workspace"

    /** 是否已归位到桌面第一屏：存在 id/workspace节点且其 bounds 左边界==0。 */
    fun isFirstPage(nodes: List<NodeDto>): Boolean {
        val workspace = nodes.firstOrNull {
            it.viewIdResourceName?.endsWith(WORKSPACE_SUFFIX) == true
        } ?: return false
        val left = workspace.bounds?.getOrNull(0) ?: return false
        return left == 0
    }
}