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

    @Test
    fun truncate_keeps_short_text_unchanged() {
        assertEquals("你好", NodeFlattener.truncate("你好"))
    }

    @Test
    fun truncate_cuts_long_text_with_ellipsis() {
        val long = "一".repeat(30)
        val out = NodeFlattener.truncate(long)!!
        assertEquals(NodeFlattener.MAX_TEXT_LEN + 1, out.length) // 20 字 + 省略号
        assertEquals("…", out.substring(out.length - 1))
    }

    @Test
    fun truncate_null_returns_null() {
        assertEquals(null, NodeFlattener.truncate(null))
    }

    @Test
    fun should_keep_true_for_interactive_flags() {
        assertEquals(true, NodeFlattener.shouldKeep(clickable = true, editable = false, scrollable = false, checkable = false, hasDesc = false))
        assertEquals(true, NodeFlattener.shouldKeep(clickable = false, editable = true, scrollable = false, checkable = false, hasDesc = false))
        assertEquals(true, NodeFlattener.shouldKeep(clickable = false, editable = false, scrollable = true, checkable = false, hasDesc = false))
        assertEquals(true, NodeFlattener.shouldKeep(clickable = false, editable = false, scrollable = false, checkable = true, hasDesc = false))
    }

    @Test
    fun should_keep_true_when_has_content_description() {
        assertEquals(true, NodeFlattener.shouldKeep(clickable = false, editable = false, scrollable = false, checkable = false, hasDesc = true))
    }

    @Test
    fun should_keep_false_for_plain_text_leaf() {
        // 纯文本叶子（不可交互、无 desc）被丢弃
        assertEquals(false, NodeFlattener.shouldKeep(clickable = false, editable = false, scrollable = false, checkable = false, hasDesc = false))
    }

    // --- viewIdToLabel ---

    @Test
    fun view_id_to_label_takes_last_segment_after_slash_and_replaces_underscore() {
        assertEquals("contacts tab", NodeFlattener.viewIdToLabel("com.ss.android.lark:id/contacts_tab"))
    }

    @Test
    fun view_id_to_label_without_slash_replaces_underscore_on_whole_string() {
        assertEquals("contacts tab", NodeFlattener.viewIdToLabel("contacts_tab"))
    }

    @Test
    fun view_id_to_label_null_returns_null() {
        assertEquals(null, NodeFlattener.viewIdToLabel(null))
    }

    @Test
    fun view_id_to_label_blank_returns_null() {
        assertEquals(null, NodeFlattener.viewIdToLabel("   "))
    }

    // --- pickLabel 四级兜底：text -> desc -> descendant -> viewIdToLabel ---

    @Test
    fun pick_label_returns_text_when_present() {
        assertEquals("联系人", NodeFlattener.pickLabel("联系人", "desc", "descendant", "com.x:id/contacts_tab"))
    }

    @Test
    fun pick_label_returns_desc_when_text_blank() {
        assertEquals("desc", NodeFlattener.pickLabel("  ", "desc", "descendant", "com.x:id/contacts_tab"))
    }

    @Test
    fun pick_label_returns_descendant_when_text_and_desc_blank() {
        assertEquals("descendant", NodeFlattener.pickLabel(null, null, "descendant", "com.x:id/contacts_tab"))
    }

    @Test
    fun pick_label_returns_view_id_label_when_first_three_blank() {
        assertEquals("contacts tab", NodeFlattener.pickLabel(null, "", "  ", "com.x:id/contacts_tab"))
    }

    @Test
    fun pick_label_returns_null_when_all_blank() {
        assertEquals(null, NodeFlattener.pickLabel(null, null, null, null))
    }
}