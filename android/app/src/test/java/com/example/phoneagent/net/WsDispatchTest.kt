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
            onTaskEnd = { _, _ -> },
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
            onTaskEnd = { _, _ -> },
        )
        d.dispatch("""{"type":"task.start","taskId":"t1","goal":"发消息","target":"dev"}""")
        assertEquals("发消息", goal)
    }

    @Test
    fun dispatch_task_done_invokes_end_callback_with_done_true() {
        var doneFlag: Boolean? = null
        var detailParam: String? = null
        val d = WsDispatcher(
            onTaskStart = { _, _ -> },
            onAction = { },
            onTaskEnd = { done, detail ->
                doneFlag = done
                detailParam = detail
            },
        )
        d.dispatch("""{"type":"task.done","taskId":"t1","result":"ok","summary":"done"}""")
        assertEquals(true, doneFlag)
        assertEquals("ok", detailParam)
    }

    @Test
    fun dispatch_task_abort_invokes_end_callback_with_done_false() {
        var doneFlag: Boolean? = null
        var detailParam: String? = null
        val d = WsDispatcher(
            onTaskStart = { _, _ -> },
            onAction = { },
            onTaskEnd = { done, detail ->
                doneFlag = done
                detailParam = detail
            },
        )
        d.dispatch("""{"type":"task.abort","taskId":"t1","reason":"stuck_loop"}""")
        assertEquals(false, doneFlag)
        assertEquals("stuck_loop", detailParam)
    }

    @Test
    fun dispatch_unknown_type_is_ignored() {
        var touched = false
        val d = WsDispatcher(
            onTaskStart = { _, _ -> touched = true },
            onAction = { touched = true },
            onTaskEnd = { _, _ -> touched = true },
        )
        d.dispatch("""{"type":"event.unknown"}""")
        assertEquals(false, touched)
    }
}
