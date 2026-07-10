package com.example.phoneagent.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.phoneagent.data.AgentStateRepository
import com.example.phoneagent.domain.AgentStatus
import com.example.phoneagent.domain.DebugInfo
import com.example.phoneagent.domain.TraceDirection
import com.example.phoneagent.domain.TraceEvent
import com.example.phoneagent.net.WsClient
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.combine
import kotlinx.coroutines.flow.stateIn
import javax.inject.Inject

data class AgentUiState(
    val status: AgentStatus = AgentStatus(),
    val debug: DebugInfo = DebugInfo(),
    val debugUnlocked: Boolean = false,
)

@HiltViewModel
class MainViewModel @Inject constructor(
    private val repo: AgentStateRepository,
    private val wsClient: WsClient,
) : ViewModel() {

    private companion object {
        const val UNLOCK_THRESHOLD = 7
        const val TEST_GOAL = "在飞书里切换到「飞书个人账户」，点击左下角的「消息」，上下滑动找到群「Android AI 开发组」，点进去停留在发送消息的页面"
    }

    private val _debugUnlocked = MutableStateFlow(false)
    private var titleTapCount = 0

    val uiState: StateFlow<AgentUiState> =
        combine(repo.status, repo.debug, _debugUnlocked) { status, debug, unlocked ->
            AgentUiState(status = status, debug = debug, debugUnlocked = unlocked)
        }.stateIn(
            scope = viewModelScope,
            started = SharingStarted.WhileSubscribed(5000),
            initialValue = AgentUiState(),
        )

    /** 连点标题：达阈值解锁调试视图。 */
    fun onTitleTap() {
        titleTapCount++
        if (titleTapCount >= UNLOCK_THRESHOLD) {
            _debugUnlocked.value = true
        }
    }

    /** 收起调试视图并重置计数。 */
    fun onHideDebug() {
        _debugUnlocked.value = false
        titleTapCount = 0
    }

    /** 点击「运行测试任务」：通过 WS 上行 task.request 指定目标，触发云端下发 task.start。 */
    fun onRunTestTask() {
        wsClient.sendTaskRequest(TEST_GOAL)
        repo.appendTrace(
            TraceEvent(
                ts = System.currentTimeMillis(),
                direction = TraceDirection.UP,
                kind = "task.request",
                summary = TEST_GOAL,
            )
        )
    }
}