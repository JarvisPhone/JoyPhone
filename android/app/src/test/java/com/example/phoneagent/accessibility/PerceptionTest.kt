// android/app/src/test/java/com/example/phoneagent/accessibility/PerceptionTest.kt
package com.example.phoneagent.accessibility

import org.junit.Assert.assertEquals
import org.junit.Test

class PerceptionTest {
    @Test
    fun keepOnlyVisibleAndTextOrClickableNodes() {
        val input = listOf(
            FlatNode("n1", text = "通讯录", visible = true, clickable = true),
            FlatNode("n2", text = null, visible = true, clickable = false),
            FlatNode("n3", text = "", visible = false, clickable = true),
        )
        val out = PerceptionFilter.filter(input)
        assertEquals(1, out.size)
        assertEquals("n1", out[0].id)
    }
}