package com.example.phoneagent.net

import com.example.phoneagent.protocol.DownAction
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class WsDispatchTest {

    @Test
    fun dispatch_action_invokes_action_callback() {
        var gotAction: DownAction? = null
        val d = WsDispatcher(
            onTaskStart = { _, _ -> },
            onAction = { gotAction = it },
            onTaskEnd = { _ -> },
        )
        d.dispatch("""{"type":"action","actionId":"a1","op":"tap","params":{"match_text":"搜索"}}""")

        assertEquals("a1", gotAction?.actionId)
        assertEquals("搜索", gotAction?.params?.get("match_text"))
    }

    @Test
    fun dispatch_task_start_invokes_start_callback() {
        var goal: String? = null
        val d = WsDispatcher(
            onTaskStart = { g, _ -> goal = g },
            onAction = { },
            onTaskEnd = { },
        )
        d.dispatch("""{"type":"task.start","taskId":"t1","goal":"发消息","target":"dev"}""")
        assertEquals("发消息", goal)
    }

    @Test
    fun dispatch_task_done_invokes_end_callback() {
        var reason: String? = null
        val d = WsDispatcher(
            onTaskStart = { _, _ -> },
            onAction = { },
            onTaskEnd = { reason = it },
        )
        d.dispatch("""{"type":"task.done","taskId":"t1","result":"ok","summary":"done"}""")
        assertEquals("ok", reason)
    }

    @Test
    fun dispatch_unknown_type_is_ignored() {
        var touched = false
        val d = WsDispatcher(
            onTaskStart = { _, _ -> touched = true },
            onAction = { touched = true },
            onTaskEnd = { touched = true },
        )
        d.dispatch("""{"type":"event.unknown"}""")
        assertEquals(false, touched)
    }
}