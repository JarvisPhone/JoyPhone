package com.example.phoneagent.accessibility

import android.accessibilityservice.AccessibilityService
import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.accessibility.AccessibilityEvent
import com.example.phoneagent.data.AgentStateRepository
import com.example.phoneagent.domain.ActionLog
import com.example.phoneagent.domain.TaskState
import com.example.phoneagent.net.WsClient
import com.example.phoneagent.protocol.UplinkPerception
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

@AndroidEntryPoint
class PhoneAgentService : AccessibilityService() {

    companion object {
        const val WS_URL = "ws://10.253.61.158:8000"
        private const val DEBOUNCE_MS = 400L
    }

    @Inject lateinit var wsClient: WsClient
    @Inject lateinit var repo: AgentStateRepository

    private lateinit var executor: Executor
    private val handler = Handler(Looper.getMainLooper())
    private var pendingReport: Runnable? = null

    override fun onServiceConnected() {
        super.onServiceConnected()
        executor = Executor(service = this, context = applicationContext)
        repo.updateAccessibility(true)
        val deviceId = Settings.Secure.getString(contentResolver, Settings.Secure.ANDROID_ID) ?: "device"
        wsClient.start(
            baseUrl = WS_URL,
            deviceId = deviceId,
            onTaskStart = { goal, _ ->
                repo.updateTask(TaskState.Running(goal))
                reportScreen()
            },
            onAction = { action ->
                val ok = executor.execute(action.op, action.params)
                wsClient.sendActionResult(action.actionId, ok)
                repo.appendActionLog(ActionLog(System.currentTimeMillis(), action.op, ok))
                if (action.op == "read_screen") reportScreen()
            },
            onTaskEnd = { repo.updateTask(TaskState.Idle) },
        )
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
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