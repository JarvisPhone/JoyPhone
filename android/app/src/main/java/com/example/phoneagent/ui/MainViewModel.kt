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
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import javax.inject.Inject

data class AgentUiState(
    val status: AgentStatus = AgentStatus(),
    val debug: DebugInfo = DebugInfo(),
    val debugUnlocked: Boolean = false,
    val sampleCountdown: Int = 0,
    val sampleHint: String = "",
)

@HiltViewModel
class MainViewModel @Inject constructor(
    private val repo: AgentStateRepository,
    private val wsClient: WsClient,
) : ViewModel() {

    private companion object {
        const val UNLOCK_THRESHOLD = 7
        const val TEST_GOAL = "打开飞书，给群「Android AI 开发组」发一条消息"
        const val SAMPLE_DELAY_SECONDS = 10
    }

    private val _debugUnlocked = MutableStateFlow(false)
    private val _sampleCountdown = MutableStateFlow(0)
    private val _sampleHint = MutableStateFlow("")
    private var titleTapCount = 0

    val uiState: StateFlow<AgentUiState> =
        combine(
            repo.status, repo.debug, _debugUnlocked, _sampleCountdown, _sampleHint,
        ) { status, debug, unlocked, countdown, hint ->
            AgentUiState(
                status = status, debug = debug, debugUnlocked = unlocked,
                sampleCountdown = countdown, sampleHint = hint,
            )
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

    /** 点击「开始采样」:校验 label,发采样请求,启动 UI 倒计时提示。 */
    fun onCaptureSample(label: String) {
        val trimmed = label.trim()
        if (trimmed.isEmpty()) {
            _sampleHint.value = "请先填场景标签"
            return
        }
        val ok = repo.requestSample(trimmed, SAMPLE_DELAY_SECONDS)
        if (!ok) {
            _sampleHint.value = "无障碍服务未连接,无法采样"
            return
        }
        viewModelScope.launch {
            _sampleHint.value = "切到目标场景,倒计时结束自动抓帧"
            for (s in SAMPLE_DELAY_SECONDS downTo 1) {
                _sampleCountdown.value = s
                delay(1000L)
            }
            _sampleCountdown.value = 0
            _sampleHint.value = "已触发抓帧「$trimmed」"
        }
    }
}
