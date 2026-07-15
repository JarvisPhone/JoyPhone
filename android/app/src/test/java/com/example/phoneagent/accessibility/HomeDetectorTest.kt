package com.example.phoneagent.accessibility

import com.example.phoneagent.protocol.NodeDto
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * HomeDetector 归位判据单测。
 *
 * 真机双帧证据(ColorOS 负一屏 ROM)：
 * - 桌面第一屏：workspace 节点 bounds=[0,0,1080,2374]，左边界==0(满屏对齐)
 * - 停在负一屏/中间态：workspace 节点 bounds=[43,95,1037,2279]，左边界>0(被负一屏推挤)
 *
 * 归位成功判据 = 存在 id/workspace 节点且其 bounds 左边界==0。
 */
class HomeDetectorTest {

    private val WORKSPACE_ID = "com.android.launcher:id/workspace"

    @Test
    fun first_page_when_workspace_left_edge_is_zero() {
        val nodes = listOf(
            NodeDto(id = "0-1", text = "时钟", viewIdResourceName = WORKSPACE_ID, bounds = listOf(0, 0, 1080, 2374)),
        )
        assertTrue(HomeDetector.isFirstPage(nodes))
    }

    @Test
    fun not_first_page_when_workspace_left_edge_positive() {
        // 负一屏推挤态：workspace 左边界 43
        val nodes = listOf(
            NodeDto(id = "0-1", text = "时钟", viewIdResourceName = WORKSPACE_ID, bounds = listOf(43, 95, 1037, 2279)),
        )
        assertFalse(HomeDetector.isFirstPage(nodes))
    }

    @Test
    fun not_first_page_when_no_workspace_node() {
        val nodes = listOf(
            NodeDto(id = "x", text = "随便", bounds = listOf(0, 0, 100, 100)),
        )
        assertFalse(HomeDetector.isFirstPage(nodes))
    }

    @Test
    fun not_first_page_when_workspace_bounds_null() {
        val nodes = listOf(
            NodeDto(id = "0-1", viewIdResourceName = WORKSPACE_ID, bounds = null),
        )
        assertFalse(HomeDetector.isFirstPage(nodes))
    }
}