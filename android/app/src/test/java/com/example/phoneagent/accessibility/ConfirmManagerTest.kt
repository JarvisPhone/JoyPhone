package com.example.phoneagent.accessibility

import com.example.phoneagent.protocol.DownTaskConfirm
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ConfirmManagerTest {

    private data class Sent(
        val taskId: String,
        val confirmId: String,
        val approved: Boolean,
        val reason: String,
    )

    private class FakeScheduler {
        val scheduled = mutableListOf<Pair<Runnable, Long>>()
        val removed = mutableListOf<Runnable>()

        val postDelayed: (Runnable, Long) -> Unit = { r, delayMs -> scheduled.add(r to delayMs) }
        val removeCallbacks: (Runnable) -> Unit = { r ->
            removed.add(r)
            scheduled.removeAll { it.first == r }
        }
    }

    private fun confirm(
        taskId: String = "t1",
        confirmId: String = "c1",
        timeoutMs: Int = 5000,
    ) = DownTaskConfirm(
        taskId = taskId,
        confirmId = confirmId,
        target = "张三",
        message = "hello",
        timeoutMs = timeoutMs,
    )

    private fun fixture(): Triple<ConfirmManager, FakeScheduler, MutableList<Sent>> {
        val scheduler = FakeScheduler()
        val sent = mutableListOf<Sent>()
        val traces = mutableListOf<String>()
        val manager = ConfirmManager(
            sendResponse = { t, c, a, r -> sent.add(Sent(t, c, a, r)) },
            postDelayed = scheduler.postDelayed,
            removeCallbacks = scheduler.removeCallbacks,
            onTrace = { traces.add(it) },
        )
        return Triple(manager, scheduler, sent)
    }

    @Test
    fun timeout_sends_auto_approve_once() {
        val (manager, scheduler, sent) = fixture()
        manager.onConfirm(confirm(taskId = "t9", confirmId = "c9", timeoutMs = 3000))

        assertEquals(1, scheduler.scheduled.size)
        assertEquals(3000L, scheduler.scheduled[0].second)

        scheduler.scheduled[0].first.run()

        assertEquals(1, sent.size)
        assertEquals(Sent("t9", "c9", true, "toast_timeout_auto_confirm"), sent[0])

        // 再次触发同一 runnable(竞态)不应重复发送
        scheduler.scheduled[0].first.run()
        assertEquals(1, sent.size)
    }

    @Test
    fun onTaskEnd_cancels_pending_timeout() {
        val (manager, scheduler, sent) = fixture()
        manager.onConfirm(confirm())
        val runnable = scheduler.scheduled[0].first

        manager.onTaskEnd()

        assertTrue(scheduler.scheduled.isEmpty())
        assertTrue(scheduler.removed.contains(runnable))
        // 即使 handler 竞态下仍执行了 runnable,也不应发送
        runnable.run()
        assertTrue(sent.isEmpty())
    }

    @Test
    fun onDestroy_clears_pending() {
        val (manager, scheduler, sent) = fixture()
        manager.onConfirm(confirm())
        val runnable = scheduler.scheduled[0].first

        manager.onDestroy()

        assertTrue(scheduler.scheduled.isEmpty())
        runnable.run()
        assertTrue(sent.isEmpty())
    }

    @Test
    fun new_confirm_replaces_previous_and_reschedules() {
        val (manager, scheduler, sent) = fixture()
        manager.onConfirm(confirm(taskId = "t1", confirmId = "c1"))
        val first = scheduler.scheduled[0].first
        manager.onConfirm(confirm(taskId = "t2", confirmId = "c2"))

        // 旧回调已被移除,只保留新的一次调度
        assertTrue(scheduler.removed.contains(first))
        assertEquals(1, scheduler.scheduled.size)

        scheduler.scheduled[0].first.run()
        assertEquals(listOf(Sent("t2", "c2", true, "toast_timeout_auto_confirm")), sent)
    }

    @Test
    fun timeout_without_pending_sends_nothing() {
        val (_, scheduler, sent) = fixture()
        // 没有任何 onConfirm,直接触发(防御性)
        assertTrue(sent.isEmpty())
        assertTrue(scheduler.scheduled.isEmpty())
    }
}
