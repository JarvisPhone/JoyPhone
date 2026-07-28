package com.example.phoneagent.accessibility

import org.junit.Assert.assertEquals
import org.junit.Test

class GestureGeometryTest {

    @Test
    fun center_of_bounds_is_midpoint() {
        val (cx, cy) = GestureGeometry.centerOf(listOf(0, 0, 100, 60))
        assertEquals(50f, cx, 0.001f)
        assertEquals(30f, cy, 0.001f)
    }

    @Test
    fun center_of_offset_bounds() {
        val (cx, cy) = GestureGeometry.centerOf(listOf(200, 400, 260, 460))
        assertEquals(230f, cx, 0.001f)
        assertEquals(430f, cy, 0.001f)
    }

    @Test
    fun default_swipe_up_moves_from_lower_to_upper() {
        val s = GestureGeometry.defaultSwipeUp(width = 1080, height = 1920)
        assertEquals(540f, s.startX, 0.001f)
        assert(s.startY > s.endY)
        assertEquals(540f, s.endX, 0.001f)
    }

    @Test
    fun parse_swipe_params_reads_four_coords() {
        val s = GestureGeometry.fromParams(
            mapOf("x1" to "100", "y1" to "800", "x2" to "100", "y2" to "200")
        )
        assertEquals(100f, s!!.startX, 0.001f)
        assertEquals(800f, s.startY, 0.001f)
        assertEquals(200f, s.endY, 0.001f)
    }

    @Test
    fun parse_swipe_params_missing_returns_null() {
        assertEquals(null, GestureGeometry.fromParams(mapOf("x1" to "100")))
    }

    // ---- 语义 direction → 轨迹(2026-07-28 修:云端下发 direction 端侧要真的翻页) ----
    // 真机根因:云端 swipe {direction: "left"} 端侧原来只认 x1/y1/x2/y2,
    // 读不到就回落 defaultSwipeUp 上滑,桌面 pager 拿到垂直手势不换页只做动画,
    // home_locate 空翻 5 次后 app_not_found abort。修复后 direction=left 真的
    // 从右向左水平划,pager 翻到下一页。

    @Test
    fun direction_left_moves_finger_right_to_left_at_mid_height() {
        val s = GestureGeometry.fromDirection("left", width = 1080, height = 2400)!!
        assert(s.startX > s.endX)
        // 水平轨迹,y 起止相等 → Executor 会给 400ms 时长
        assertEquals(s.startY, s.endY, 0.001f)
        assertEquals(1200f, s.startY, 0.001f)
        // 起止落在 15%/85%,避开系统全屏手势敏感区
        assertEquals(918f, s.startX, 0.001f)
        assertEquals(162f, s.endX, 0.001f)
    }

    @Test
    fun direction_right_moves_finger_left_to_right() {
        val s = GestureGeometry.fromDirection("right", width = 1080, height = 2400)!!
        assert(s.startX < s.endX)
        assertEquals(s.startY, s.endY, 0.001f)
    }

    @Test
    fun direction_up_moves_finger_bottom_to_top_at_mid_width() {
        val s = GestureGeometry.fromDirection("up", width = 1080, height = 2400)!!
        assertEquals(540f, s.startX, 0.001f)
        assertEquals(540f, s.endX, 0.001f)
        assert(s.startY > s.endY)
    }

    @Test
    fun direction_down_moves_finger_top_to_bottom() {
        val s = GestureGeometry.fromDirection("down", width = 1080, height = 2400)!!
        assertEquals(540f, s.startX, 0.001f)
        assertEquals(540f, s.endX, 0.001f)
        assert(s.startY < s.endY)
    }

    @Test
    fun direction_case_insensitive() {
        assertEquals(
            GestureGeometry.fromDirection("left", 1080, 2400),
            GestureGeometry.fromDirection("LEFT", 1080, 2400),
        )
    }

    @Test
    fun direction_null_or_blank_returns_null() {
        assertEquals(null, GestureGeometry.fromDirection(null, 1080, 2400))
        assertEquals(null, GestureGeometry.fromDirection("", 1080, 2400))
        assertEquals(null, GestureGeometry.fromDirection("  ", 1080, 2400))
    }

    @Test
    fun direction_unknown_returns_null_for_fallback() {
        assertEquals(null, GestureGeometry.fromDirection("diagonal", 1080, 2400))
    }

    // ---- tap 坐标下发：云侧把选中节点解析为 x/y 中心坐标，端侧优先按坐标点击 ----
    // 真机根因：端侧 tap 只认 match_text 全屏子串匹配，误命中负一屏磁贴进错 app。
    // 修复后云侧下发 params{x,y}，端侧直接点该坐标，比子串匹配可靠。

    @Test
    fun tap_point_reads_x_y_coords() {
        val p = GestureGeometry.tapPointFromParams(mapOf("x" to "300", "y" to "400"))
        assertEquals(300f, p!!.first, 0.001f)
        assertEquals(400f, p.second, 0.001f)
    }

    @Test
    fun tap_point_missing_x_returns_null() {
        assertEquals(null, GestureGeometry.tapPointFromParams(mapOf("y" to "400")))
    }

    @Test
    fun tap_point_missing_y_returns_null() {
        assertEquals(null, GestureGeometry.tapPointFromParams(mapOf("x" to "300")))
    }

    @Test
    fun tap_point_empty_params_returns_null() {
        assertEquals(null, GestureGeometry.tapPointFromParams(mapOf("match_text" to "飞书")))
    }

    @Test
    fun tap_point_invalid_number_returns_null() {
        assertEquals(null, GestureGeometry.tapPointFromParams(mapOf("x" to "abc", "y" to "400")))
    }
}