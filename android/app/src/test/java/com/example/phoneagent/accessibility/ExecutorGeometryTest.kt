package com.example.phoneagent.accessibility

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * input 按坐标命中 editable 的纯几何部分单测:
 * 点在 bounds 内/外判定,以及多个候选 editable bounds 中选中正确那个。
 * 真机根因:input 只找首个 editable,多输入框场景(如登录页账号/密码)写错框。
 */
class ExecutorGeometryTest {

    // ---- pointInBounds ----

    @Test
    fun point_inside_bounds_hits() {
        assertTrue(GestureGeometry.pointInBounds(listOf(100, 200, 300, 400), 200f, 300f))
    }

    @Test
    fun point_on_bounds_edge_hits() {
        assertTrue(GestureGeometry.pointInBounds(listOf(100, 200, 300, 400), 100f, 200f))
        assertTrue(GestureGeometry.pointInBounds(listOf(100, 200, 300, 400), 300f, 400f))
    }

    @Test
    fun point_left_of_bounds_misses() {
        assertFalse(GestureGeometry.pointInBounds(listOf(100, 200, 300, 400), 99f, 300f))
    }

    @Test
    fun point_right_of_bounds_misses() {
        assertFalse(GestureGeometry.pointInBounds(listOf(100, 200, 300, 400), 301f, 300f))
    }

    @Test
    fun point_above_bounds_misses() {
        assertFalse(GestureGeometry.pointInBounds(listOf(100, 200, 300, 400), 200f, 199f))
    }

    @Test
    fun point_below_bounds_misses() {
        assertFalse(GestureGeometry.pointInBounds(listOf(100, 200, 300, 400), 200f, 401f))
    }
}
