package com.example.phoneagent.accessibility

import org.junit.Assert.assertEquals
import org.junit.Test

class NodeFlattenerTest {

    @Test
    fun rect_to_bounds_list_is_ltrb() {
        // 使用纯 Int 重载，避免依赖 android.graphics.Rect（JVM 单测下 not-mocked）。
        // Rect(l,t,r,b) 对应 rectToBounds(rect) 内部即 rectToBounds(left,top,right,bottom)。
        assertEquals(listOf(10, 20, 110, 80), NodeFlattener.rectToBounds(10, 20, 110, 80))
    }

    @Test
    fun make_id_is_stable_for_same_index_path() {
        assertEquals("0-2-1", NodeFlattener.makeId(listOf(0, 2, 1)))
    }

    @Test
    fun make_id_root_is_zero() {
        assertEquals("0", NodeFlattener.makeId(listOf(0)))
    }
}