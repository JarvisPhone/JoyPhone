package com.example.phoneagent.accessibility

import android.accessibilityservice.AccessibilityService
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.accessibility.AccessibilityEvent
import com.example.phoneagent.net.WsClient
import com.example.phoneagent.protocol.UplinkPerception

class PhoneAgentService : AccessibilityService() {

    companion object {
        // 真机联调：填 Mac 局域网 IP，如 "ws://192.168.1.20:8000"
        const val WS_URL = "ws://10.0.2.2:8000"
        private const val DEBOUNCE_MS = 400L
    }

    private lateinit var executor: Executor
    private var wsClient: WsClient? = null
    private val handler = Handler(Looper.getMainLooper())
    private var pendingReport: Runnable? = null

    override fun onServiceConnected() {
        super.onServiceConnected()
        executor = Executor(service = this, context = applicationContext)
        val deviceId = Settings.Secure.getString(contentResolver, Settings.Secure.ANDROID_ID) ?: "device"
        wsClient = WsClient(
            baseUrl = WS_URL,
            onTaskStart = { _, _ -> reportScreen() },
            onAction = { action ->
                val ok = executor.execute(action.op, action.params)
                wsClient?.sendActionResult(action.actionId, ok)
                if (action.op == "read_screen") reportScreen()
            },
            onTaskEnd = { /* done/abort：MVP 仅结束 */ },
        ).also { it.connect(deviceId) }
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
        wsClient?.sendPerception(perception)
    }

    override fun onInterrupt() {
      wsClient?.close()
    }

    override fun onDestroy() {
        pendingReport?.let { handler.removeCallbacks(it) }
        wsClient?.close()
        super.onDestroy()
    }
}