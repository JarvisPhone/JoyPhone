package com.example.phoneagent.data

import com.example.phoneagent.domain.TraceDirection
import com.example.phoneagent.domain.TraceEvent
import org.junit.Assert.assertEquals
import org.junit.Test

class AgentStateRepositoryTest {

    @Test
    fun appendTrace_adds_event() {
        val repo = AgentStateRepository()
        repo.appendTrace(TraceEvent(ts = 1L, direction = TraceDirection.UP, kind = "task.request", summary = "goal"))
        val events = repo.debug.value.traceEvents
        assertEquals(1, events.size)
        assertEquals("task.request", events.first().kind)
        assertEquals(TraceDirection.UP, events.first().direction)
        assertEquals("goal", events.first().summary)
    }

    @Test
    fun appendTrace_keeps_last_50() {
        val repo = AgentStateRepository()
        repeat(60) { i ->
            repo.appendTrace(TraceEvent(ts = i.toLong(), direction = TraceDirection.INFO, kind = "k", summary = "s$i"))
        }
        val events = repo.debug.value.traceEvents
        assertEquals(50, events.size)
        assertEquals("s10", events.first().summary)
        assertEquals("s59", events.last().summary)
    }
}