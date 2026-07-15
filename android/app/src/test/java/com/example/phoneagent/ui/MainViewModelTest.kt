package com.example.phoneagent.ui

import com.example.phoneagent.data.AgentStateRepository
import com.example.phoneagent.net.WsClient
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Test

class MainViewModelTest {

    private fun newViewModel(repo: AgentStateRepository): MainViewModel {
        val wsClient = WsClient(repo, Json { ignoreUnknownKeys = true })
        return MainViewModel(repo, wsClient)
    }

    @Test
    fun onRunTestTask_sends_task_request() {
        val repo = AgentStateRepository()
        val vm = newViewModel(repo)

        vm.onRunTestTask()

        val events = repo.debug.value.traceEvents
        assertEquals(1, events.size)
        val e = events.first()
        assertEquals("task.request", e.kind)
    }
}
