package com.example.phoneagent.accessibility

import com.example.phoneagent.protocol.NodeDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Test

class ScreenFingerprintTest {

    @Test
    fun same_nodes_produce_equal_fingerprint() {
        val a = listOf(
            NodeDto(id = "n1", text = "搜索", desc = "search", bounds = listOf(0, 0, 100, 50)),
            NodeDto(id = "n2", text = "消息", desc = "msg", bounds = listOf(0, 60, 100, 110)),
        )
        val b = listOf(
            NodeDto(id = "n1", text = "搜索", desc = "search", bounds = listOf(0, 0, 100, 50)),
            NodeDto(id = "n2", text = "消息", desc = "msg", bounds = listOf(0, 60, 100, 110)),
        )

        assertEquals(ScreenFingerprint.of(a), ScreenFingerprint.of(b))
    }

    @Test
    fun different_text_produces_different_fingerprint() {
        val a = listOf(NodeDto(id = "n1", text = "搜索", desc = "d", bounds = listOf(0, 0, 100, 50)))
        val b = listOf(NodeDto(id = "n1", text = "消息", desc = "d", bounds = listOf(0, 0, 100, 50)))

        assertNotEquals(ScreenFingerprint.of(a), ScreenFingerprint.of(b))
    }

    @Test
    fun different_bounds_produces_different_fingerprint() {
        val a = listOf(NodeDto(id = "n1", text = "t", desc = "d", bounds = listOf(0, 0, 100, 50)))
        val b = listOf(NodeDto(id = "n1", text = "t", desc = "d", bounds = listOf(0, 60, 100, 110)))

        assertNotEquals(ScreenFingerprint.of(a), ScreenFingerprint.of(b))
    }

    @Test
    fun empty_list_produces_stable_empty_fingerprint() {
        val first = ScreenFingerprint.of(emptyList())
        val second = ScreenFingerprint.of(emptyList())

        assertEquals("", first)
        assertEquals(first, second)
    }
}