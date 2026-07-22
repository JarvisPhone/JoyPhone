package com.example.phoneagent.accessibility

import com.example.phoneagent.protocol.NodeDto
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class AnchorResolverTest {

    private fun node(
        id: String,
        text: String? = null,
        desc: String? = null,
        rid: String? = null,
        clickable: Boolean = true,
        editable: Boolean = false,
    ) = NodeDto(
        id = id,
        text = text,
        desc = desc,
        viewIdResourceName = rid,
        bounds = listOf(0, 0, 100, 100),
        clickable = clickable,
        editable = editable,
    )

    @Test
    fun fromParams_returns_null_when_no_anchor() {
        assertNull(AnchorResolver.fromParams(mapOf("x" to "1", "y" to "2")))
        assertNull(AnchorResolver.fromParams(emptyMap()))
    }

    @Test
    fun fromParams_parses_all_fields() {
        val a = AnchorResolver.fromParams(
            mapOf("match_text" to "发送", "match_rid" to "btn_send", "occurrence" to "1")
        )!!
        assertEquals("发送", a.text)
        assertEquals("btn_send", a.rid)
        assertEquals(1, a.occurrence)
    }

    @Test
    fun text_exact_match_wins_over_generic_container_rid() {
        // 列表行复用同一容器 rid(shortcut_item_container):rid 不得淹没唯一文本行
        val nodes = listOf(
            node("0-0", text = "MoltPulse", rid = "com.x:id/shortcut_item_container"),
            node("0-1", text = "展开", rid = "com.x:id/shortcut_item_container"),
            node("0-2", text = "智研", rid = "com.x:id/shortcut_item_container"),
        )
        val r = AnchorResolver.resolve(nodes, Anchor(text = "展开", rid = "shortcut_item_container", occurrence = null))
        assertEquals("0-1", (r as ResolveResult.Found).node.id)
    }

    @Test
    fun rid_is_fallback_when_no_text_match() {
        // 无文本节点(图标按钮):rid 兑底定位
        val nodes = listOf(
            node("0-0", text = "消息", rid = "com.x:id/tab_msg"),
            node("0-1", text = null, rid = "com.x:id/btn_send"),
        )
        val r = AnchorResolver.resolve(nodes, Anchor(text = null, rid = "btn_send", occurrence = null))
        assertEquals("0-1", (r as ResolveResult.Found).node.id)
    }

    @Test
    fun rid_narrows_duplicate_text_matches() {
        val nodes = listOf(
            node("0-0", text = "发送", rid = "com.x:id/btn_send"),
            node("0-1", text = "发送", rid = "com.x:id/menu_send"),
        )
        val r = AnchorResolver.resolve(nodes, Anchor(text = "发送", rid = "btn_send", occurrence = null))
        assertEquals("0-0", (r as ResolveResult.Found).node.id)
    }

    @Test
    fun text_exact_match() {
        val nodes = listOf(node("0-0", text = "微信"), node("0-1", text = "飞书"))
        val r = AnchorResolver.resolve(nodes, Anchor(text = "飞书", rid = null, occurrence = null))
        assertEquals("0-1", (r as ResolveResult.Found).node.id)
    }

    @Test
    fun desc_match_when_no_text_match() {
        val nodes = listOf(node("0-0", desc = "发消息", editable = true))
        val r = AnchorResolver.resolve(nodes, Anchor(text = "发消息", rid = null, occurrence = null))
        assertEquals("0-0", (r as ResolveResult.Found).node.id)
    }

    @Test
    fun substring_does_not_match_fail_closed() {
        // fail-closed:「飞书」不能子串命中「飞书一键养虾🦞6群」(2026-07-22 错群事故的镜像场景)
        val nodes = listOf(node("0-0", text = "飞书一键养虾🦞6群｜OpenClaw"))
        val r = AnchorResolver.resolve(nodes, Anchor(text = "飞书", rid = null, occurrence = null))
        assertTrue(r is ResolveResult.NotFound)
    }

    @Test
    fun duplicate_labels_without_occurrence_are_ambiguous() {
        val nodes = listOf(node("0-0", text = "发送"), node("0-1", text = "发送"))
        val r = AnchorResolver.resolve(nodes, Anchor(text = "发送", rid = null, occurrence = null))
        assertTrue(r is ResolveResult.Ambiguous)
    }

    @Test
    fun occurrence_picks_nth_match() {
        val nodes = listOf(
            node("0-0", text = "发送"),
            node("0-1", text = "发送"),
            node("0-2", text = "发送"),
        )
        val r = AnchorResolver.resolve(nodes, Anchor(text = "发送", rid = null, occurrence = 2))
        assertEquals("0-2", (r as ResolveResult.Found).node.id)
    }

    @Test
    fun occurrence_out_of_range_is_ambiguous() {
        val nodes = listOf(node("0-0", text = "发送"), node("0-1", text = "发送"))
        val r = AnchorResolver.resolve(nodes, Anchor(text = "发送", rid = null, occurrence = 5))
        assertTrue(r is ResolveResult.Ambiguous)
    }

    @Test
    fun editable_only_filters_pool() {
        val nodes = listOf(
            node("0-0", text = "发消息", editable = false),
            node("0-1", desc = "发消息", editable = true),
        )
        val r = AnchorResolver.resolve(
            nodes, Anchor(text = "发消息", rid = null, occurrence = null), editableOnly = true
        )
        assertEquals("0-1", (r as ResolveResult.Found).node.id)
    }

    @Test
    fun no_match_is_not_found() {
        val nodes = listOf(node("0-0", text = "微信"))
        val r = AnchorResolver.resolve(nodes, Anchor(text = "飞书", rid = null, occurrence = null))
        assertTrue(r is ResolveResult.NotFound)
    }
}
