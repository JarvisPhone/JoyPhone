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
    fun special_chars_do_not_collide() {
        // 旧实现用 ~ | , 做分隔符，UI 文本含这些字符会产生碰撞误判 atEnd。
        // 场景 a：text="a|b" desc=""；场景 b：text="a" desc="b" —— 旧实现拼出相同��段。
        val a = listOf(NodeDto(id = "n1", text = "a|b", desc = "", bounds = listOf(0, 0, 10, 10)))
        val b = listOf(NodeDto(id = "n1", text = "a", desc = "b", bounds = listOf(0, 0, 10, 10)))
        assertNotEquals(ScreenFingerprint.of(a), ScreenFingerprint.of(b))

        // 场景：text 含 ~ 与 desc 边界混淆
        val c = listOf(NodeDto(id = "n1", text = "x~y", desc = "z", bounds = listOf(0, 0, 10, 10)))
        val d = listOf(NodeDto(id = "n1", text = "x", desc = "y~z", bounds = listOf(0, 0, 10, 10)))
        assertNotEquals(ScreenFingerprint.of(c), ScreenFingerprint.of(d))

        // 场景：逗号在 text 中与 bounds 分隔符混淆
        val e = listOf(NodeDto(id = "n1", text = "1,2", desc = null, bounds = listOf(3, 4, 10, 10)))
        val f = listOf(NodeDto(id = "n1", text = "1", desc = null, bounds = listOf(2, 3, 4, 10)))
        assertNotEquals(ScreenFingerprint.of(e), ScreenFingerprint.of(f))
    }

    @Test
    fun null_desc_differs_from_empty_desc() {
        val a = listOf(NodeDto(id = "n1", text = "t", desc = null, bounds = listOf(0, 0, 10, 10)))
        val b = listOf(NodeDto(id = "n1", text = "t", desc = "", bounds = listOf(0, 0, 10, 10)))
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