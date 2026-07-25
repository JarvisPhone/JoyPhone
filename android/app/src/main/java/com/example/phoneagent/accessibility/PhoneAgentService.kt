package com.example.phoneagent.accessibility

import android.accessibilityservice.AccessibilityService
import android.content.Intent
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import android.widget.Toast
import com.example.phoneagent.BuildConfig
import com.example.phoneagent.data.AgentStateRepository
import com.example.phoneagent.domain.ActionLog
import com.example.phoneagent.domain.TaskState
import com.example.phoneagent.domain.TraceDirection
import com.example.phoneagent.domain.TraceEvent
import com.example.phoneagent.net.WsClient
import com.example.phoneagent.protocol.UplinkPerception
import com.example.phoneagent.protocol.UplinkSampleCapture
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import javax.inject.Inject

@AndroidEntryPoint
class PhoneAgentService : AccessibilityService() {

    companion object {
        // WebSocket URL 由 BuildConfig.WS_URL 提供(见 app/build.gradle.kts)
        private const val DEBOUNCE_MS = 400L
        private const val TAG = "PhoneAgent"
    }

    @Inject lateinit var wsClient: WsClient
    @Inject lateinit var repo: AgentStateRepository

    private lateinit var executor: Executor
    private val handler = Handler(Looper.getMainLooper())
    private var pendingReport: Runnable? = null
    @Volatile private var taskActive: Boolean = false
    // 消息序号计数器:perception 与 action.result 共用,用于消息乱序检测
    @Volatile private var msgSeq: Int = 0
    // wsClient.start() 仅调用一次
    @Volatile private var wsStarted = false
    // 下一次 reportScreen() 时携带截图(LLM 上一次发 request_screenshot 时置位)
    @Volatile private var pendingScreenshot: Boolean = false

    /** 最近一次窗口状态变更事件带来的 Activity 类名(带包名前缀补全)。用于采样元数据,与 taskActive 无关。 */
    @Volatile private var lastActivity: String = ""

    /** Toast 确认窗口:状态与超时由 ConfirmManager 管理。Toast 展示留在 Service。 */
    private val confirmManager by lazy {
        ConfirmManager(
            sendResponse = { taskId, confirmId, approved, reason ->
                wsClient.sendConfirmResponse(taskId, confirmId, approved, reason)
            },
            postDelayed = { r, delayMs -> handler.postDelayed(r, delayMs) },
            removeCallbacks = { r -> handler.removeCallbacks(r) },
            onTrace = { detail ->
                repo.appendTrace(
                    TraceEvent(System.currentTimeMillis(), TraceDirection.UP, "task.confirm_response", detail)
                )
            },
        )
    }
    // 使用 Dispatchers.Main.immediate 替代 Dispatchers.Main，避免在主线程上不必要的调度开销
    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    override fun onServiceConnected() {
        super.onServiceConnected()
        executor = Executor(service = this, context = applicationContext)
        repo.updateAccessibility(true)

        // 仅在首次调用时启动 WebSocket
        if (wsStarted) return
        wsStarted = true

        val deviceId = Settings.Secure.getString(contentResolver, Settings.Secure.ANDROID_ID) ?: "device"
        wsClient.start(
            baseUrl = BuildConfig.WS_URL,
            deviceId = deviceId,
            onTaskStart = { goal, _ ->
                taskActive = true
                resetSequenceNumbers()
                Log.i(TAG, "↓ task.start goal=$goal → taskActive=true")
                repo.appendTrace(TraceEvent(System.currentTimeMillis(), TraceDirection.DOWN, "task.start", goal))
                repo.updateTask(TaskState.Running(goal))
                reportScreen()
            },
            onAction = { action ->
                Log.i(TAG, "↓ action ${action.op} ${action.params} (taskActive=$taskActive)")
                repo.appendTrace(TraceEvent(System.currentTimeMillis(), TraceDirection.DOWN, "action", "${action.op} ${action.params}"))
                val result = executor.execute(action.op, action.params)
                val seq = ++msgSeq
                Log.i(TAG, "↑ action.result ${action.op} ok=${result.ok} error=${result.error} seq=$seq")
                repo.appendTrace(TraceEvent(System.currentTimeMillis(), TraceDirection.UP, "action.result", "${action.op} ok=${result.ok} error=${result.error} seq=$seq"))
                wsClient.sendActionResult(action.actionId, result.ok, seq, result.error)
                repo.appendActionLog(ActionLog(System.currentTimeMillis(), action.op, result.ok))
                if (action.op == "read_screen") reportScreen()
                // request_screenshot 触发截屏;结果在下一帧 perception.screenshot 上传
                if (action.op == "request_screenshot") {
                    pendingScreenshot = true
                    Log.i(TAG, "request_screenshot → 下一帧带 screenshot")
                    repo.appendTrace(TraceEvent(System.currentTimeMillis(), TraceDirection.INFO, "screenshot.request", "pending"))
                }
            },
            onTaskEnd = { done, detail ->
                taskActive = false
                confirmManager.onTaskEnd()
                val summary = if (done) detail else "失败: $detail"
                Log.i(TAG, "↓ task.end done=$done detail=$detail → taskActive=false")
                repo.appendTrace(TraceEvent(System.currentTimeMillis(), TraceDirection.DOWN, "task.end", summary))
                repo.updateTask(
                    if (done) TaskState.Done(detail)
                    else TaskState.Failed(detail),
                )
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
                confirmManager.onConfirm(confirm)
                // 弹 Toast 提示用户:5 秒后自动发送
                val preview = if (confirm.message.isNotBlank()) {
                    "「${confirm.target}」发「${confirm.message}」"
                } else {
                    "「${confirm.target}」发消息"
                }
                val toastText = "${preview}\n切走屏幕取消,5 秒后自动发送"
                Toast.makeText(applicationContext, toastText, Toast.LENGTH_LONG).show()
            },
        )

        serviceScope.launch {
            repo.sampleRequests.collect { req ->
                Log.i(TAG, "sample request label=${req.label} delay=${req.delaySeconds}s")
                delay(req.delaySeconds * 1000L)
                captureSample(req.label)
            }
        }
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event?.eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) {
            val cls = event.className?.toString()
            val pkg = event.packageName?.toString()
            if (!cls.isNullOrEmpty()) {
                lastActivity = if (pkg != null && cls.startsWith(".")) "$pkg$cls" else cls
            }
        }
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
        val seq = ++msgSeq
        // 若上一次动作是 request_screenshot,本次 perception 携带 base64 截图
        val screenshotB64 = if (pendingScreenshot) {
            pendingScreenshot = false
            captureScreenshot()?.also { Log.i(TAG, "screenshot attached, size=${it.length}") }
        } else null
        val perception = UplinkPerception(
            nodeTree = nodes,
            screenshot = screenshotB64,
            pkg = root.packageName?.toString() ?: "",
            activity = activity,
            ts = System.currentTimeMillis(),
            seq = seq,
        )
        wsClient.sendPerception(perception)
        Log.i(TAG, "↑ perception pkg=${perception.pkg} nodes=${nodes.size} seq=$seq (taskActive=$taskActive)")
        repo.appendTrace(TraceEvent(System.currentTimeMillis(), TraceDirection.UP, "perception", "pkg=${perception.pkg} nodes=${nodes.size} seq=$seq"))
    }

    /** 截屏:返回 PNG base64。无 root 权限时退化为 null(LLM 收到反馈可再发一次)。
     *
     * 注意:AccessibilityService 没有 MediaProjection/system_app 权限,不能真正截屏。
     * 此处返回 null + 在端侧 log 一行警告——实际联调需要给端侧开「无障碍截屏」白名单
     * 或用 ADB shell screencap 通过主端协助传递图片。基线接通链路,等真机权限到位。
     */
    private fun captureScreenshot(): String? {
        Log.w(TAG, "screenshot not yet implemented on AccessibilityService (need MediaProjection or system_app)")
        return null
    }

    /** 采样专用抓帧:抓当前屏 nodeTree,组 sample.capture 上报。与决策链路解耦。 */
    private fun captureSample(label: String) {
        val root = rootInActiveWindow
        if (root == null) {
            Toast.makeText(applicationContext, "抓帧失败:请确认无障碍已开启", Toast.LENGTH_SHORT).show()
            Log.w(TAG, "captureSample: rootInActiveWindow == null")
            return
        }
        val nodes = NodeFlattener.flatten(root)
        val pkg = root.packageName?.toString() ?: ""
        val activity = lastActivity.ifEmpty { pkg }
        val sample = UplinkSampleCapture(
            label = label,
            nodeTree = nodes,
            pkg = pkg,
            activity = activity,
            ts = System.currentTimeMillis(),
            device = "${Build.MANUFACTURER} ${Build.MODEL}",
        )
        wsClient.sendSampleCapture(sample)
        Toast.makeText(applicationContext, "已采样「$label」: ${nodes.size} 个节点", Toast.LENGTH_SHORT).show()
        Log.i(TAG, "↑ sample.capture label=$label pkg=$pkg activity=$activity nodes=${nodes.size}")
        repo.appendTrace(
            TraceEvent(System.currentTimeMillis(), TraceDirection.UP, "sample.capture", "label=$label nodes=${nodes.size}")
        )
    }

    override fun onInterrupt() {
        wsClient.close()
    }

    override fun onUnbind(intent: Intent?): Boolean {
        repo.updateAccessibility(false)
        wsClient.close()
        return super.onUnbind(intent)
    }

    private fun resetSequenceNumbers() {
        // 任务重置时重置消息序号
        msgSeq = 0
    }

    override fun onDestroy() {
        pendingReport?.let { handler.removeCallbacks(it) }
        confirmManager.onDestroy()
        repo.updateAccessibility(false)
        wsClient.destroy()
        serviceScope.coroutineContext[kotlinx.coroutines.Job]?.cancel()
        super.onDestroy()
    }
}
