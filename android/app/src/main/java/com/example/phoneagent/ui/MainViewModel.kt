package com.example.phoneagent.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.phoneagent.data.AgentStateRepository
import com.example.phoneagent.domain.AgentStatus
import com.example.phoneagent.domain.DebugInfo
import com.example.phoneagent.domain.TaskState
import com.example.phoneagent.domain.TaskUserIntent
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
        const val SAMPLE_DELAY_SECONDS = 10
    }

    private val _debugUnlocked = MutableStateFlow(false)
    private val _sampleCountdown = MutableStateFlow(0)
    private val _sampleHint = MutableStateFlow("")
    private var titleTapCount = 0
    private var sampleSeq = 0

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

    /**
     * 用户在输入框输入任务目标并点击发送。
     * 通过 WS 上行 task.request，触发云端下发 task.start。
     *
     * 同时把 userIntent 标记为 SentGoal:UI 此时显示"等待开始",在收到下行
     * task.start 前 TaskState 仍为 Idle/SentGoal 之前的值。SentGoal 仅在
     * 收到下行 task.done/abort 时被 clearUserIntent 兜底清除(防 SentGoal 残留)。
     */
    fun onSendGoal(goal: String) {
        val trimmed = goal.trim()
        if (trimmed.isEmpty()) return
        repo.setUserIntent(TaskUserIntent.SentGoal)
        wsClient.sendTaskRequest(trimmed)
        repo.appendTrace(
            TraceEvent(
                ts = System.currentTimeMillis(),
                direction = TraceDirection.UP,
                kind = "task.request",
                summary = trimmed,
            )
        )
    }

    /** 点击「开始采样」:自动生成自增序号 label,发采样请求,启动 UI 倒计时提示。 */
    fun onCaptureSample() {
        val label = "sample_%03d".format(++sampleSeq)
        val ok = repo.requestSample(label, SAMPLE_DELAY_SECONDS)
        if (!ok) {
            _sampleHint.value = "无障碍服务未连接,无法采样"
            return
        }
        viewModelScope.launch {
            _sampleHint.value = "采样中 $label,切到目标场景,倒计时结束自动抓帧"
            for (s in SAMPLE_DELAY_SECONDS downTo 1) {
                _sampleCountdown.value = s
                delay(1000L)
            }
            _sampleCountdown.value = 0
            _sampleHint.value = "已触发抓帧「$label」"
        }
    }

    /**
     * 用户点击「中止运行中任务」按钮(只对 TaskState.Running 状态可点,UI 层保证)。
     *
     * 走 userIntent = Cancelled + 乐观切 Idle,下行 task.abort 到达时由
     * PhoneAgentService.onTaskEnd 通过 consumeUserIntent 吸收,UI 不会推到 Failed。
     */
    fun onAbortRunningTask(reason: String = "user_cancel") {
        val taskId = currentTaskId() ?: return
        repo.setUserIntent(TaskUserIntent.Cancelled)
        repo.updateTask(TaskState.Idle)
        wsClient.sendTaskCancel(taskId, reason)
        repo.appendTrace(
            TraceEvent(
                ts = System.currentTimeMillis(),
                direction = TraceDirection.UP,
                kind = "task.cancel",
                summary = "taskId=$taskId reason=$reason",
            )
        )
    }

    /**
     * 用户点「重新输入」按钮(对 Done/Failed 状态可点)。
     * 纯 UI 重置,不发任何上行:让用户继续输入下一个任务目标。
     */
    fun onResetToIdle() {
        repo.clearUserIntent()
        repo.updateTask(TaskState.Idle)
    }

    private fun currentTaskId(): String? {
        // 直读 repo 而非 uiState:UiState 是 combine 的产物,SharingStarted.WhileSubscribed
        // 在测试/无订阅者场景下返回 initialValue(空 TaskState),导致 currentTaskId() 误判。
        val st = repo.status.value.task
        return when (st) {
            is TaskState.Running -> st.taskId.takeIf { it.isNotBlank() }
            else -> null
        }
    }
}
