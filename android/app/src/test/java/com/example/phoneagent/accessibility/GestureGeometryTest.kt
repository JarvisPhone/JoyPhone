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
}