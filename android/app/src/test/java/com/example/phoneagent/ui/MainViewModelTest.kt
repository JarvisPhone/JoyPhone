package com.example.phoneagent.ui

import com.example.phoneagent.data.AgentStateRepository
import com.example.phoneagent.domain.TaskState
import com.example.phoneagent.domain.TaskUserIntent
import com.example.phoneagent.net.WsClient
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertSame
import org.junit.Test

class MainViewModelTest {

    private fun newViewModel(repo: AgentStateRepository): MainViewModel {
        val wsClient = WsClient(repo, Json { ignoreUnknownKeys = true })
        return MainViewModel(repo, wsClient)
    }

    @Test
    fun onSendGoal_sends_task_request() {
        val repo = AgentStateRepository()
        val vm = newViewModel(repo)

        vm.onSendGoal("打开飞书发消息")

        val events = repo.debug.value.traceEvents
        assertEquals(1, events.size)
        val e = events.first()
        assertEquals("task.request", e.kind)
        assertEquals("打开飞书发消息", e.summary)
    }

    @Test
    fun onSendGoal_marks_sent_goal_intent() {
        val repo = AgentStateRepository()
        val vm = newViewModel(repo)

        vm.onSendGoal("g")

        assertEquals(TaskUserIntent.SentGoal, repo.status.value.userIntent)
    }

    /**
     * cancel race 修:onAbortRunningTask 走 userIntent=Cancelled + 乐观切 Idle,
     * 不再是「无脑上行 + 推 UI」的旧实现。
     */
    @Test
    fun on_abort_running_task_marks_user_intent_cancelled_and_idle() {
        val repo = AgentStateRepository()
        val vm = newViewModel(repo)
        // 假设有 running 任务由模拟下行驱动(view-model 仅读 status,这里直接铺)
        repo.updateTask(TaskState.Running(description = "g", taskId = "t-1"))
        repo.clearUserIntent()  // baseline 清掉,模拟"已在 task.start 时清过"

        vm.onAbortRunningTask()

        // userIntent 已经是 Cancelled,TaskState 已经被切到 Idle
        assertEquals(TaskUserIntent.Cancelled, repo.status.value.userIntent)
        assertSame(TaskState.Idle, repo.status.value.task)
        // trace 有 kind=task.cancel
        assertEquals("task.cancel", repo.debug.value.traceEvents.last { it.kind == "task.cancel" }.kind)
    }

    @Test
    fun on_abort_running_task_without_taskid_does_nothing() {
        val repo = AgentStateRepository()
        val vm = newViewModel(repo)
        // 当前 TaskState 是 Idle,不该发出任何取消
        repo.clearUserIntent()

        vm.onAbortRunningTask()

        assertEquals(TaskUserIntent.None, repo.status.value.userIntent)
        assertEquals(0, repo.debug.value.traceEvents.size)
    }

    /**
     * onResetToIdle 纯 UI 重置,不发任何上行。
     */
    @Test
    fun on_reset_to_idle_clears_intent_and_state() {
        val repo = AgentStateRepository()
        val vm = newViewModel(repo)
        repo.updateTask(TaskState.Failed("boom"))
        repo.setUserIntent(TaskUserIntent.SentGoal)

        vm.onResetToIdle()

        assertEquals(TaskUserIntent.None, repo.status.value.userIntent)
        assertSame(TaskState.Idle, repo.status.value.task)
        assertEquals(0, repo.debug.value.traceEvents.size)
    }
}
