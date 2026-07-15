package com.example.phoneagent.accessibility

import android.accessibilityservice.AccessibilityService
import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import android.widget.Toast
import com.example.phoneagent.data.AgentStateRepository
import com.example.phoneagent.domain.ActionLog
import com.example.phoneagent.domain.TaskState
import com.example.phoneagent.domain.TraceDirection
import com.example.phoneagent.domain.TraceEvent
import com.example.phoneagent.net.WsClient
import com.example.phoneagent.protocol.DownTaskConfirm
import com.example.phoneagent.protocol.UplinkPerception
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

@AndroidEntryPoint
class PhoneAgentService : AccessibilityService() {

    companion object {
        const val WS_URL = "ws://10.253.61.158:8000"
        private const val DEBOUNCE_MS = 400L
        private const val TAG = "PhoneAgent"
    }

    @Inject lateinit var wsClient: WsClient
    @Inject lateinit var repo: AgentStateRepository

    private lateinit var executor: Executor
    private val handler = Handler(Looper.getMainLooper())
    private var pendingReport: Runnable? = null
    @Volatile private var taskActive: Boolean = false

    /** Toast 确认窗口:5 秒倒计时,到点自动 approved=true。
     *  期间若云端检测到飞书被切走,会主动发 task.abort,我们无需做额外处理。
     */
    private val confirmTimeoutRunnable = Runnable {
        val pending = pendingConfirm
        if (pending != null) {
            Log.i(TAG, "[CONFIRM_TIMEOUT] confirmId=${pending.confirmId} → auto approved=true")
            wsClient.sendConfirmResponse(
                taskId = pending.taskId,
                confirmId = pending.confirmId,
                approved = true,
                reason = "toast_timeout_auto_confirm",
            )
            repo.appendTrace(
                TraceEvent(System.currentTimeMillis(), TraceDirection.UP, "task.confirm_response", "approved=true(toast_timeout)")
            )
            pendingConfirm = null
        }
    }
    @Volatile private var pendingConfirm: DownTaskConfirm? = null

    override fun onServiceConnected() {
        super.onServiceConnected()
        executor = Executor(service = this, context = applicationContext)
        repo.updateAccessibility(true)
        val deviceId = Settings.Secure.getString(contentResolver, Settings.Secure.ANDROID_ID) ?: "device"
        wsClient.start(
            baseUrl = WS_URL,
            deviceId = deviceId,
            onTaskStart = { goal, _ ->
                taskActive = true
                Log.i(TAG, "↓ task.start goal=$goal → taskActive=true")
                repo.appendTrace(TraceEvent(System.currentTimeMillis(), TraceDirection.DOWN, "task.start", goal))
                repo.updateTask(TaskState.Running(goal))
                reportScreen()
            },
            onAction = { action ->
                Log.i(TAG, "↓ action ${action.op} ${action.params} (taskActive=$taskActive)")
                repo.appendTrace(TraceEvent(System.currentTimeMillis(), TraceDirection.DOWN, "action", "${action.op} ${action.params}"))
                val result = executor.execute(action.op, action.params)
                Log.i(TAG, "↑ action.result ${action.op} ok=${result.ok} atEnd=${result.atEnd}")
                repo.appendTrace(TraceEvent(System.currentTimeMillis(), TraceDirection.UP, "action.result", "${action.op} ok=${result.ok} atEnd=${result.atEnd}"))
                wsClient.sendActionResult(action.actionId, result.ok, result.atEnd)
                repo.appendActionLog(ActionLog(System.currentTimeMillis(), action.op, result.ok))
                if (action.op == "read_screen") reportScreen()
            },
            onTaskEnd = { reason ->
                taskActive = false
                Log.i(TAG, "↓ task.end reason=$reason → taskActive=false")
                repo.appendTrace(TraceEvent(System.currentTimeMillis(), TraceDirection.DOWN, "task.end", reason))
                repo.updateTask(TaskState.Idle)
            },
            onTaskConfirm = { confirm ->
                Log.i(TAG, "↓ task.confirm target=${confirm.target} msg=${confirm.message} timeoutMs=${confirm.timeoutMs}")
                repo.appendTrace(
                    TraceEvent(
                        System.currentTimeMillis(),
                        TraceDirection.DOWN,
                        "task.confirm",
                        "target=${confirm.target} msg=${confirm.message}",
                    )
                )
                pendingConfirm = confirm
                // 弹 Toast 提示用户:5 秒后自动发送
                val preview = if (confirm.message.isNotBlank()) {
                    "「${confirm.target}」发「${confirm.message}」"
                } else {
                    "「${confirm.target}」发消息"
                }
                val toastText = "${preview}\n切走屏幕取消,5 秒后自动发送"
                Toast.makeText(applicationContext, toastText, Toast.LENGTH_LONG).show()
                // 启动超时定时器
                handler.removeCallbacks(confirmTimeoutRunnable)
                handler.postDelayed(confirmTimeoutRunnable, confirm.timeoutMs.toLong())
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
        val activity = root.packageName?.toString() ?: ""
        val perception = UplinkPerception(
            nodeTree = nodes,
            pkg = root.packageName?.toString() ?: "",
            activity = activity,
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
        handler.removeCallbacks(confirmTimeoutRunnable)
        repo.updateAccessibility(false)
        wsClient.close()
        super.onDestroy()
    }
}
