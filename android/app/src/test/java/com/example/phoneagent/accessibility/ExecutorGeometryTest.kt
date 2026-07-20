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

    // ---- indexOfBoundsContaining:多个 editable 选正确那个 ----

    @Test
    fun containing_index_picks_matching_bounds_among_many() {
        val candidates = listOf(
            listOf(0, 0, 500, 100),     // 顶部输入框
            listOf(0, 200, 500, 300),   // 中部输入框
            listOf(0, 400, 500, 500),   // 底部输入框
        )
        assertEquals(1, GestureGeometry.indexOfBoundsContaining(candidates, 250f, 250f))
    }

    @Test
    fun containing_index_returns_first_when_point_in_none() {
        val candidates = listOf(
            listOf(0, 0, 100, 100),
            listOf(200, 200, 300, 300),
        )
        assertEquals(null, GestureGeometry.indexOfBoundsContaining(candidates, 150f, 150f))
    }

    @Test
    fun containing_index_empty_candidates_returns_null() {
        assertEquals(null, GestureGeometry.indexOfBoundsContaining(emptyList(), 10f, 10f))
    }

    @Test
    fun containing_index_first_match_wins_when_overlapping() {
        val candidates = listOf(
            listOf(0, 0, 500, 500),
            listOf(100, 100, 200, 200),
        )
        assertEquals(0, GestureGeometry.indexOfBoundsContaining(candidates, 150f, 150f))
    }
}
