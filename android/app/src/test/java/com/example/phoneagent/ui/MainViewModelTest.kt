package com.example.phoneagent.ui

import com.example.phoneagent.data.AgentStateRepository
import com.example.phoneagent.domain.TraceDirection
import com.example.phoneagent.net.WsClient
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class MainViewModelTest {

    private fun newViewModel(repo: AgentStateRepository): MainViewModel {
        // WsClient 未 start，内部 ws=null，send 为安全 no-op，可在纯单测中使用。
        val wsClient = WsClient(repo, Json { ignoreUnknownKeys = true })
        return MainViewModel(repo, wsClient)
    }

    @Test
    fun onTestButton_appends_upstream_trace_with_debug_oneshot_goal() {
        val repo = AgentStateRepository()
        val vm = newViewModel(repo)

        vm.onTestButton()

        val events = repo.debug.value.traceEvents
        assertEquals(1, events.size)
        val e = events.first()
        assertEquals(TraceDirection.UP, e.direction)
        assertEquals("task.request", e.kind)
        assertTrue("goal 应带只读调试前缀", e.summary.contains("DEBUG-ONESHOT"))
    }
}