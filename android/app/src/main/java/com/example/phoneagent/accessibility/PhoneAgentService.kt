package com.example.phoneagent.accessibility

import android.accessibilityservice.AccessibilityService
import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import com.example.phoneagent.data.AgentStateRepository
import com.example.phoneagent.domain.ActionLog
import com.example.phoneagent.domain.TaskState
import com.example.phoneagent.domain.TraceDirection
import com.example.phoneagent.domain.TraceEvent
import com.example.phoneagent.net.WsClient
import com.example.phoneagent.protocol.UplinkPerception
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

@AndroidEntryPoint
class PhoneAgentService : AccessibilityService() {

    companion object {
        const val WS_URL = "ws://10.253.61.158:8000"
        private const val DEBOUNCE_MS = 400L
        private const val TAG = "PhoneAgent"
        /** 与 MainViewModel.DEBUG_ONESHOT_GOAL 保持一致：只读单帧调试标记。 */
        private const val DEBUG_ONESHOT_PREFIX = "[DEBUG-ONESHOT]"
        /** 只读调试：点按钮后延迟抓帧，留时间手动导航到目标 App 页面。 */
        private const val DEBUG_CAPTURE_DELAY_MS = 10000L
    }

    @Inject lateinit var wsClient: WsClient
    @Inject lateinit var repo: AgentStateRepository

    private lateinit var executor: Executor
    private val handler = Handler(Looper.getMainLooper())
    private var pendingReport: Runnable? = null
    @Volatile private var taskActive: Boolean = false
    /** 只读调试模式：上报一帧并跑云侧决策记日志，但端侧不执行返回动作。 */
    @Volatile private var readOnlyMode: Boolean = false

    override fun onServiceConnected() {
        super.onServiceConnected()
        executor = Executor(service = this, context = applicationContext)
        repo.updateAccessibility(true)
        val deviceId = Settings.Secure.getString(contentResolver, Settings.Secure.ANDROID_ID) ?: "device"
        wsClient.start(
            baseUrl = WS_URL,
            deviceId = deviceId,
            onTaskStart = { goal, _ ->
                readOnlyMode = goal.startsWith(DEBUG_ONESHOT_PREFIX)
                taskActive = true
                Log.i(TAG, "↓ task.start goal=$goal → taskActive=true readOnly=$readOnlyMode")
                repo.appendTrace(TraceEvent(System.currentTimeMillis(), TraceDirection.DOWN, "task.start", goal))
                repo.updateTask(TaskState.Running(goal))
                if (readOnlyMode) {
                    // 只读单帧：不回桌面，延迟抓帧，留时间手动导航到目标 App 页面。
                    Log.i(TAG, "[READ-ONLY] ${DEBUG_CAPTURE_DELAY_MS}ms 后抓帧，请手动打开目标 App 页面")
                    handler.postDelayed({
                        reportScreen()
                        taskActive = false
                        Log.i(TAG, "[READ-ONLY] 单帧已上报，taskActive=false，后续 action 只记录不执行")
                    }, DEBUG_CAPTURE_DELAY_MS)
                } else {
                    reportScreen()
                }
            },
            onAction = { action ->
                Log.i(TAG, "↓ action ${action.op} ${action.params} (taskActive=$taskActive readOnly=$readOnlyMode)")
                repo.appendTrace(TraceEvent(System.currentTimeMillis(), TraceDirection.DOWN, "action", "${action.op} ${action.params}"))
                if (readOnlyMode) {
                    // 只读调试：不执行，仅回报忽略，供云侧结束本次调试帧。
                    Log.i(TAG, "[READ-ONLY] 忽略执行 action ${action.op}，仅记录")
                    repo.appendTrace(TraceEvent(System.currentTimeMillis(), TraceDirection.INFO, "action.skipped", "${action.op} (readOnly)"))
                    wsClient.sendActionResult(action.actionId, ok = true, atEnd = true)
                } else {
                    val result = executor.execute(action.op, action.params)
                    Log.i(TAG, "↑ action.result ${action.op} ok=${result.ok} atEnd=${result.atEnd}")
                    repo.appendTrace(TraceEvent(System.currentTimeMillis(), TraceDirection.UP, "action.result", "${action.op} ok=${result.ok} atEnd=${result.atEnd}"))
                    wsClient.sendActionResult(action.actionId, result.ok, result.atEnd)
                    repo.appendActionLog(ActionLog(System.currentTimeMillis(), action.op, result.ok))
                    if (action.op == "read_screen") reportScreen()
                }
            },
            onTaskEnd = { reason ->
                taskActive = false
                readOnlyMode = false
                Log.i(TAG, "↓ task.end reason=$reason → taskActive=false")
                repo.appendTrace(TraceEvent(System.currentTimeMillis(), TraceDirection.DOWN, "task.end", reason))
                repo.updateTask(TaskState.Idle)
            },
        )
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (!taskActive) return
        pendingReport?.let { handler.removeCallbacks(it) }
        val r = Runnable { reportScreen() }
        pendingReport = r
        handler.postDelayed(r, DEBOUNCE_MS)
    }

    private fun reportScreen() {
        val root = rootInActiveWindow ?: return
        val nodes = NodeFlattener.flatten(root)
        val perception = UplinkPerception(
            nodeTree = nodes,
            pkg = root.packageName?.toString() ?: "",
            activity = "",
            ts = System.currentTimeMillis(),
        )
        wsClient.sendPerception(perception)
        Log.i(TAG, "↑ perception pkg=${perception.pkg} nodes=${nodes.size} (taskActive=$taskActive)")
        repo.appendTrace(TraceEvent(System.currentTimeMillis(), TraceDirection.UP, "perception", "pkg=${perception.pkg} nodes=${nodes.size}"))
    }

    override fun onInterrupt() {
        wsClient.close()
    }

    override fun onUnbind(intent: Intent?): Boolean {
        repo.updateAccessibility(false)
        wsClient.close()
        return super.onUnbind(intent)
    }

    override fun onDestroy() {
        pendingReport?.let { handler.removeCallbacks(it) }
        repo.updateAccessibility(false)
        wsClient.close()
        super.onDestroy()
    }
}