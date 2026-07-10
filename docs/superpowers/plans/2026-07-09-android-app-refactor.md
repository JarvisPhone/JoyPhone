# JoyPhone Android App 重构实现计划

日期：2026-07-09
关联设计：`docs/superpowers/specs/2026-07-09-android-app-refactor-design.md`（已获用户认可）

## Goal

用现代 Android 架构（Jetpack Compose + Hilt + Coroutines/Flow）正式重写端侧 App，实现**事件驱动的 WebSocket 连接管理**（服务绑定=连接、解绑=断开、onFailure=有限重试）与**分层状态面板**（用户视图 + 后门调试视图）。核心验证目标：真机全链路 WS 自动连接 + UI 实时反映权限/连接/任务状态。

## Architecture

Clean Architecture 单向数据流：

```
PhoneAgentService（生命周期事件：onServiceConnected/onUnbind）
  └─> ConnectionManager / WsClient（onOpen/onFailure/onClosing 事件 + 有限重试）
        └─> AgentStateRepository（@Singleton，MutableStateFlow 唯一状态源）
              └─> MainViewModel（组合 StateFlow<AgentUiState>）
                    └─> Compose UI（collectAsStateWithLifecycle 实时刷新）
```

包结构（`com.example.phoneagent` 下）：
- `domain/`：纯 Kotlin 状态模型（ConnectionState / TaskState / AgentStatus / DebugInfo / ActionLog / WsEventLog）
- `data/`：AgentStateRepository（实现），WsClient（移入并注入 Repository）
- `di/`：Hilt 模块（AppModule）
- `accessibility/`：PhoneAgentService（@AndroidEntryPoint）
- `ui/`：MainActivity（Compose）+ MainViewModel + theme/ + 各 Composable

## Tech Stack

AGP 9.2.1 / Kotlin 2.4.0 / KSP 2.3.10 / Hilt 2.60.1 / Compose BOM 2024.09.03 / Coroutines 1.9.0 / Lifecycle 2.8.7 / Gradle 9.5.1。JDK17（构建须 `export JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home`）。

## For Agentic Workers（执行须知）

- 每个 Task 都是 bite-sized（2-5 分钟）：读现有代码 → 最小实现 → 编译验证 → commit。
- 本项目**不写重复性单元测试**（用户明确），验证以**编译成功 + 真机联调**为准；Compose 用 `@Preview` 做视觉验证。
- 构建命令统一：`cd android && export JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home && ./gradlew :app:compileDebugKotlin`（快速编译校验）或 `:app:assembleDebug`（出 APK）。
- 完整代码，禁止占位符/TODO/"类似上一步"。
- 每完成一个 Task 立即 `git add -A && git commit`（不 push，最后统一 push；或按用户习惯每步 push）。
- 忽略 `artifactory.jd.com` 内部仓库报错。

## File Structure（本创建/修改）

**新建**：
| 文件 | 职责 |
|------|------|
| `domain/AgentModels.kt` | ConnectionState/TaskState/AgentStatus/DebugInfo/ActionLog/WsEventLog 定义 |
| `data/AgentStateRepository.kt` | @Singleton 唯一状态源，MutableStateFlow + 更新方法 |
| `di/AppModule.kt` | Hilt 提供 AgentStateRepository / WsClient / Json |
| `AgentApplication.kt` | @HiltAndroidApp |
| `ui/MainViewModel.kt` | @HiltViewModel，暴露 uiState + 交互事件 |
| `ui/theme/Theme.kt` | Material3 主题（Color/Typography/Theme） |
| `ui/AgentScreen.kt` | 用户视图 Composable（3 张状态卡片 + 后门解锁标题） |
| `ui/DebugPanel.kt` | 后门调试视图 Composable |

**修改**：
| 文件 | 变更 |
|------|------|
| `net/WsClient.kt` | 注入 Repository，事件写状态流，onFailure 有限重试，删 Log |
| `accessibility/PhoneAgentService.kt` | @AndroidEntryPoint，注入 WsClient/Repository，生命周期驱动连接 |
| `MainActivity.kt` | @AndroidEntryPoint，setContent { AgentScreen() } |
| `AndroidManifest.xml` | application android:name=".AgentApplication" |
| `app/build.gradle.kts` | 确认 hilt/compose 依赖齐全（已在工具链阶段完成，仅校验） |

---

## Tasks

### Task 0：前置校验工具链已通过，仅确认基线）

- 确认 `git status` 干净、当前在 master、工具链 commit `f135465` 已在。
- 确认 `app/build.gradle.kts` 已含 hilt.android 插件、hilt-android + ksp(hilt.compiler) 依赖、buildFeatures.compose=true。
- **验证**：`git log --oneline -1` 显示 `f135465`；无需改动即完成。

---

### Task 1：domain 层状态模型

新建 `android/app/src/main/java/com/example/phoneagent/domain/AgentModels.kt`，完整内容：

```kotlin
package com.example.phoneagent.domain

/** WS 连接状态。 */
enum class ConnectionState { DISCONNECTED, CONNECTING, CONNECTED, RECONNECTING }

/** 任务执行状态。 */
sealed interface TaskState {
    data object Idle : TaskState
    data class Running(val description: String) : TaskState
}

/** 面向用户的聚合状态。 */
data class AgentStatus(
    val accessibilityGranted: Boolean = false,
    val connection: ConnectionState = ConnectionState.DISCONNECTED,
    val task: TaskState = TaskState.Idle,
)

/** 单条动作流水（调试用）。 */
data class ActionLog(
    val ts: Long,
    val op: String,
    val ok: Boolean,
    val detail: String = "",
)

/** 单条 WS 底层事件（调试用）。 */
data class WsEventLog(
    val ts: Long,
    val event: String,   // onOpen / onClosing / onFailure / connecting / retry
    val detail: String = "",
)

/** 调试专用信息（后门才展示）。 */
data class DebugInfo(
    val wsUrl: String = "",
    val deviceId: String = "",
    val recentActions: List<ActionLog> = emptyList(),
    val wsEvents: List<WsEventLog> = emptyList(),
    val reconnectAttempts: Int = 0,
)
```

- **验证**：`./gradlew :app:compileDebugKotlin` 编译通过。
- **提交**：`git add -A && git commit -m "feat(android): 新增 domain 层状态模型"`

---

### Task 2：AgentStateRepository（唯一状态源）

新建 `android/app/src/main/java/com/example/phoneagent/data/AgentStateRepository.kt`，完整内容：

```kotlin
package com.example.phoneagent.data

import com.example.phoneagent.domain.ActionLog
import com.example.phoneagent.domain.AgentStatus
import com.example.phoneagent.domain.ConnectionState
import com.example.phoneagent.domain.DebugInfo
import com.example.phoneagent.domain.TaskState
import com.example.phoneagent.domain.WsEventLog
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import javax.inject.Inject
import javax.inject.Singleton

/** Service 与 UI 的唯一状态桥梁。@Singleton 由 Hilt 保证进程内单例。 */
@Singleton
class AgentStateRepository @Inject constructor() {

    private companion object {
        const val MAX_LOG = 50
    }

    private val _status = MutableStateFlow(AgentStatus())
    val status: StateFlow<AgentStatus> = _status.asStateFlow()

    private val _debug = MutableStateFlow(DebugInfo())
    val debug: StateFlow<DebugInfo> = _debug.asStateFlow()

    fun updateAccessibility(granted: Boolean) {
        _status.update { it.copy(accessibilityGranted = granted) }
    }

    fun updateConnection(state: ConnectionState) {
        _status.update { it.copy(connection = state) }
    }

    fun updateTask(state: TaskState) {
        _status.update { it.copy(task = state) }
    }

    fun setDebugMeta(wsUrl: String, deviceId: String) {
        _debug.update { it.copy(wsUrl = wsUrl, deviceId = deviceId) }
    }

    fun setReconnectAttempts(n: Int) {
        _debug.update { it.copy(reconnectAttempts = n) }
    }

    fun appendActionLog(log: ActionLog) {
        _debug.update { it.copy(recentActions = (it.recentActions + log).takeLast(MAX_LOG)) }
    }

    fun appendWsEvent(log: WsEventLog) {
        _debug.update { it.copy(wsEvents = (it.wsEvents + log).takeLast(MAX_LOG)) }
    }
}
```

- **验证**：`./gradlew :app:compileDebugKotlin` 编译通过。
- **提交**：`git commit -m "feat(android): 新增 AgentStateRepository 唯一状态源"`

---

### Task 3：重构 WsClient（注入 Repository + 有限重试）

**重写** `android/app/src/main/java/com/example/phoneagent/net/WsClient.kt`。要点：改为 Hilt 可注入（构造注入 Repository + Json），保留原 dispatch 回调协作，事件写入 Repository，删除 Log，onFailure 触发固定间隔有限重试。完整内容：

```kotlin
package com.example.phoneagent.net

import com.example.phoneagent.data.AgentStateRepository
import com.example.phoneagent.domain.ConnectionState
import com.example.phoneagent.domain.WsEventLog
import com.example.phoneagent.protocol.DownAction
import com.example.phoneagent.protocol.UplinkActionResult
import com.example.phoneagent.protocol.UplinkPerception
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import javax.inject.Inject
import javax.inject.Singleton

/**
 * WebSocket 客户端：连接状态写入 Repository，onFailure 触发有限重试。
 * 下行消息仍经 WsDispatcher 分发到 Service 注入的回调。
 */
@Singleton
class WsClient @Inject constructor(
    private val repo: AgentStateRepository,
    private val json: Json,
) {
    private companion object {
        const val MAX_RETRY = 5
        const val RETRY_DELAY_MS = 3000L
    }

    private val client = OkHttpClient()
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var ws: WebSocket? = null
    private var dispatcher: WsDispatcher? = null

    private var baseUrl: String = ""
    private var deviceId: String = ""
    private var retryCount = 0
    private var manuallyClosed = false

    /** 由 Service 注入下行回调后调用。 */
    fun start(
        baseUrl: String,
        deviceId: String,
        onTaskStart: (goal: String, taskId: String) -> Unit,
        onAction: (DownAction) -> Unit,
        onTaskEnd: (reason: String) -> Unit,
    ) {
        this.baseUrl = baseUrl
        this.deviceId = deviceId
        this.dispatcher = WsDispatcher(onTaskStart, onAction, onTaskEnd)
        manuallyClosed = false
        retryCount = 0
        repo.setDebugMeta(baseUrl, deviceId)
        connect()
    }

    private fun connect() {
        repo.updateConnection(
            if (retryCount ==0) ConnectionState.CONNECTING else ConnectionState.RECONNECTING
        )
        repo.appendWsEvent(WsEventLog(now(), "connecting", "$baseUrl/ws/$deviceId"))
        val req = Request.Builder().url("$baseUrl/ws/$deviceId").build()
        ws = client.newWebSocket(req, listener)
    }

    private val listener = object : WebSocketListener() {
        override fun onOpen(webSocket: WebSocket, response: Response) {
            retryCount = 0
            repo.setReconnectAttempts(0)
            repo.updateConnection(ConnectionState.CONNECTED)
            repo.appendWsEvent(WsEventLog(now(), "onOpen", "code=${response.code}"))
        }

        override fun onMessage(webSocket: WebSocket, text: String) {
            dispatcher?.dispatch(text)
        }

        override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
            repo.updateConnection(ConnectionState.DISCONNECTED)
         repo.appendWsEvent(WsEventLog(now(), "onClosing", "$code $reason"))
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            repo.appendWsEvent(WsEventLog(now(), "onFailure", t.message ?: "unknown"))
            scheduleRetry()
        }
    }

    private fun scheduleRetry() {
        if (manuallyClosed) return
        if (retryCount >= MAX_RETRY) {
            repo.updateConnection(ConnectionState.DISCONNECTED)
            repo.appendWsEvent(WsEventLog(now(), "retry", "达上限 $MAX_RETRY，停止重连"))
            return
        }
        retryCount++
        repo.setReconnectAttempts(retryCount)
        repo.updateConnection(ConnectionState.RECONNECTING)
        scope.launch {
            delay(RETRY_DELAY_MS)
            if (!manuallyClosed) connect()
        }
    }

    fun sendPerception(p: UplinkPerception) {
        ws?.send(json.encodeToString(p))
    }

    fun sendActionResult(actionId: String, ok: Boolean, error: String? = null) {
        ws?.send(json.encodeToString(UplinkActionResult(actionId = actionId, ok = ok, error = error)))
    }

    fun close() {
        manuallyClosed = true
        ws?.close(1000, "bye")
        ws = null
        repo.updateConnection(ConnectionState.DISCONNECTED)
    }

    private fun now() = System.currentTimeMillis()
}
```

- **验证**：`./gradlew :app:compileDebugKotlin` 编译通过。
- **提交**：`git commit -m "refactor(android): WsClient 注入 Repository + onFailure 有限重试"`

---

### Task 4：Hilt Application + AppModule

**4a.** 新建 `android/app/src/main/java/com/example/phoneagent/AgentApplication.kt`：

```kotlin
package com.example.phoneagent

import android.app.Application
import dagger.hilt.android.HiltAndroidApp

@HiltAndroidApp
class AgentApplication : Application()
```

**4b.** 新建 `android/app/src/main/java/com/example/phoneagent/di/AppModule.kt`（仅提供 Json；Repository/WsClient 已用构造注入，无需 provides）：

```kotlin
package com.example.phoneagent.di

import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import kotlinx.serialization.json.Json
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object AppModule {

    @Provides
    @Singleton
    fun provideJson(): Json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }
}
```

**4c.** 修改 `android/app/src/main/AndroidManifest.xml`，给 `<application>` 加 `android:name=".AgentApplication"`：

将 `<application` 起始标签改为：
```xml
    <application
        android:name=".AgentApplication"
        android:allowBackup="true"
        android:label="@string/app_name"
        android:usesCleartextTraffic="true"
        android:theme="@style/Theme.AppCompat.DayNight.NoActionBar">
```
（theme 稍后 Task 8 换成 Compose 主题，此处先保留能编译。）

- **验证**：`./gradlew :app:compileDebugKotlin` 编译通过（Hilt 注解处理无报错）。
- **提交**：`git commit -m "feat(android): 新增 @HiltAndroidApp 与 AppModule"`

---

### Task 5：重构 PhoneAgentService（@AndroidEntryPoint + 生命周期驱动）

**重写** `android/app/src/main/java/com/example/phoneagent/accessibility/PhoneAgentService.kt`。要点：标注 `@AndroidEntryPoint`，注入 `WsClient` 与 `AgentStateRepository`；`onServiceConnected` 置 accessibilityGranted=true 并 start WS；`onUnbind`/`onDestroy` 断开并置 false；动作执行结果写 ActionLog；WS_URL 保留常量。完整内容：

```kotlin
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
```

- **验证**：`./gradlew :app:compileDebugKotlin` 编译通过。
- **提交**：`git commit -m "refactor(android): PhoneAgentService @AndroidEntryPoint 生命周期驱动连接"`

---

### Task 6：MainViewModel（暴露 uiState + 交互事件）

新建 `android/app/src/main/java/com/example/phoneagent/ui/MainViewModel.kt`。要点：组合 status + debug，暴露 `AgentUiState`；`debugUnlocked` 由连点计数触发（阈值 7）。完整内容：

```kotlin
package com.example.phoneagent.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.example.phoneagent.data.AgentStateRepository
import com.example.phoneagent.domain.AgentStatus
import com.example.phoneagent.domain.DebugInfo
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
) : ViewModel() {

    private companion object {
        const val UNLOCK_THRESHOLD = 7
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

    /** 连点标题：达阈值解锁调试视图�� */
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
}
```

- **验证**：`./gradlew :app:compileDebugKotlin` 编译通过。
- **提交**：`git commit -m "feat(android): 新增 MainViewModel 暴露 uiState"`

---

### Task 7：Compose Material3 主题

新建 `android/app/src/main/java/com/example/phoneagent/ui/theme/Theme.kt`，完整内容：

```kotlin
package com.example.phoneagent.ui.theme

import android.app.Activity
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val LightColors = lightColorScheme(
    primary = Color(0xFF2563EB),
    secondary = Color(0xFF0EA5E9),
    background = Color(0xFFF8FAFC),
    surface = Color(0xFFFFFFFF),
)

private val DarkColors = darkColorScheme(
    primary = Color(0xFF60A5FA),
    secondary = Color(0xFF38BDF8),
    background = Color(0xFF0F172A),
    surface = Color(0xFF1E293B),
)

/** 状态色：连接指示灯用。 */
object StatusColors {
    val Connected = Color(0xFF22C55E)   // 绿
    val Pending = Color(0xFFF59E0B)     // 黄（连接中/重连中）
    val Disconnected = Color(0xFFEF4444) // 红
}

@Composable
fun JoyPhoneTheme(
    darkTheme: Boolean = isSystemInDarkTheme(),
    content: @Composable () -> Unit,
) {
    val colors = if (darkTheme) DarkColors else LightColors
    MaterialTheme(
        colorScheme = colors,
        typography = Typography(),
        content = content,
    )
}
```

- **验证**：`./gradlew :app:compileDebugKotlin` 编译通过。
- **提交**：`git commit -m "feat(android): 新增 Compose Material3 主题"`

---

### Task 8：后门调试面板 Composable

新建 `android/app/src/main/java/com/example/phoneagent/ui/DebugPanel.kt`，完整内容：

```kotlin
package com.example.phoneagent.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import com.example.phoneagent.domain.DebugInfo

@Composable
fun DebugPanel(
    debug: DebugInfo,
    onHide: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Card(modifier = modifier.fillMaxWidth()) {
       Column(
            modifier = Modifier
                .padding(16.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Text("调试信息", style = MaterialTheme.typography.titleMedium)
            Text("WS_URL: ${debug.wsUrl}", style = MaterialTheme.typography.bodySmall, fontFamily = FontFamily.Monospace)
            Text("deviceId: ${debug.deviceId}", style = MaterialTheme.typography.bodySmall, fontFamily = FontFamily.Monospace)
            Text("重连次数: ${debug.reconnectAttempts}", style = MaterialTheme.typography.bodySmall)

            Text("最近动作", style = MaterialTheme.typography.titleSmall)
            if (debug.recentActions.isEmpty()) {
                Text("（暂无）", style = MaterialTheme.typography.bodySmall)
            } else {
                debug.recentActions.takeLast(10).reversed().forEach { a ->
                    Text(
                        "${a.op} ${if (a.ok) "✓" else "✗"} ${a.detail}",
                        style = MaterialTheme.typography.bodySmall,
                        fontFamily = FontFamily.Monospace,
                    )
                }
            }

            Text("WS 事件", style = MaterialTheme.typography.titleSmall)
            if (debug.wsEvents.isEmpty()) {
                Text("（暂无）", style = MaterialTheme.typography.bodySmall)
            } else {
                debug.wsEvents.takeLast(10).reversed().forEach { e ->
                    Text(
                        "${e.event}: ${e.detail}",
                        style = MaterialTheme.typography.bodySmall,
                        fontFamily = FontFamily.Monospace,
                    )
                }
            }

            TextButton(onClick = onHide) { Text("收起调试视图") }
        }
    }
}
```

- **验证**：`./gradlew :app:compileDebugKotlin` 编译通过。
- **提交**：`git commit -m "feat(android): 新增后门调试面板 Composable"`

---

### Task 9：用户视图 AgentScreen（3 张状态卡片 + 后门标题）

新建 `android/app/src/main/java/com/example/phoneagent/ui/AgentScreen.kt`。要点：标题可连点触发 `onTitleTap`；无障碍卡片带"去开启"按钮；连接卡片带颜色指示灯；任务卡片显示人话描述；`debugUnlocked` 时底部展开 `DebugPanel`；`@Preview` 覆盖已连接/断开两态。完整内容：

```kotlin
package com.example.phoneagent.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import com.example.phoneagent.domain.AgentStatus
import com.example.phoneagent.domain.ConnectionState
import com.example.phoneagent.domain.DebugInfo
import com.example.phoneagent.domain.TaskState
import com.example.phoneagent.ui.theme.JoyPhoneTheme
import com.example.phoneagent.ui.theme.StatusColors

@Composable
fun AgentScreen(
    uiState: AgentUiState,
    onTitleTap: () -> Unit,
    onOpenAccessibility: () -> Unit,
    onHideDebug: () -> Unit,
) {
    Scaffold { inner ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(inner)
                .padding(20.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            Text(
                text = "JoyPhone Agent",
                style = MaterialTheme.typography.headlineMedium,
                modifier = Modifier.clickable { onTitleTap() },
            )

            AccessibilityCard(uiState.status.accessibilityGranted, onOpenAccessibility)
            ConnectionCard(uiState.status.connection)
            TaskCard(uiState.status.task)

            if (uiState.debugUnlocked) {
                DebugPanel(debug = uiState.debug, onHide = onHideDebug)
            }
        }
    }
}

@Composable
private fun AccessibilityCard(granted: Boolean, onOpen: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("无障碍服务", style = MaterialTheme.typography.titleMedium)
            Text(
                if (granted) "已授权，可开始联调" else "未授权，请先开启无障碍服务",
                style = MaterialTheme.typography.bodyMedium,
            )
            if (!granted) {
                Button(onClick = onOpen) { Text("去开启") }
            }
        }
    }
}

@Composable
private fun ConnectionCard(state: ConnectionState) {
    val (color, label) = when (state) {
        ConnectionState.CONNECTED -> StatusColors.Connected to "已连接"
        ConnectionState.CONNECTING -> StatusColors.Pending to "连接中…"
        ConnectionState.RECONNECTING -> StatusColors.Pending to "重连中…"
        ConnectionState.DISCONNECTED -> StatusColors.Disconnected to "已断开"
    }
    Card(modifier = Modifier.fillMaxWidth()) {
        Row(
            Modifier.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Box(Modifier.size(14.dp).background(color, CircleShape))
            Column {
                Text("云端连接", style = MaterialTheme.typography.titleMedium)
                Text(label, style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
}

@Composable
private fun TaskCard(task: TaskState) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("当前任务", style = MaterialTheme.typography.titleMedium)
            when (task) {
                is TaskState.Idle -> Text("空闲中", style = MaterialTheme.typography.bodyMedium)
                is TaskState.Running -> Text("执行中：${task.description}", style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
}

@Preview(showBackground = true)
@Composable
private fun PreviewConnected() {
    JoyPhoneTheme {
        AgentScreen(
            uiState = AgentUiState(
                status = AgentStatus(
                    accessibilityGranted = true,
                    connection = ConnectionState.CONNECTED,
                    task = TaskState.Running("打开飞书并回复消息"),
                ),
       ),
            onTitleTap = {}, onOpenAccessibility = {}, onHideDebug = {},
        )
    }
}

@Preview(showBackground = true)
@Composable
private fun PreviewDisconnected() {
    JoyPhoneTheme {
        AgentScreen(
            uiState = AgentUiState(
                status = AgentStatus(
                    accessibilityGranted = false,
                    connection = ConnectionState.DISCONNECTED,
                    task = TaskState.Idle,
                ),
                debug = DebugInfo(wsUrl = "ws://10.253.61.158:8000", deviceId = "abc123", reconnectAttempts = 2),
                debugUnlocked = true,
            ),
            onTitleTap = {}, onOpenAccessibility = {}, onHideDebug = {},
        )
    }
}
```

- **验证**：`./gradlew :app:compileDebugKotlin` 编译通过。
- **提交**：`git commit -m "feat(android): 新增用户视图 AgentScreen + Preview"`

---

### Task 10：重构 MainActivity（Compose + Hilt）

**重写** `android/app/src/main/java/com/example/phoneagent/MainActivity.kt`。要点：`@AndroidEntryPoint`，`ComponentActivity`，`setContent`，onResume 时刷新无障碍权限写入 Repository（通过 ViewModel 或直接判定）；打开无障碍设置。完整内容：

```kotlin
package com.example.phoneagent

import android.content.ComponentName
import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.example.phoneagent.accessibility.PhoneAgentService
import com.example.phoneagent.ui.AgentScreen
import com.example.phoneagent.ui.MainViewModel
import com.example.phoneagent.ui.theme.JoyPhoneTheme
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    private val viewModel: MainViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            JoyPhoneTheme {
                val uiState by viewModel.uiState.collectAsStateWithLifecycle()
                AgentScreen(
                    uiState = uiState,
                    onTitleTap = viewModel::onTitleTap,
                    onOpenAccessibility = { openAccessibilitySettings() },
                    onHideDebug = viewModel::onHideDebug,
                )
            }
        }
    }

    private fun openAccessibilitySettings() {
        startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
    }
}
```

> 说明：无障碍授权状态由 `PhoneAgentService.onServiceConnected/onUnbind` 权威写入 Repository，`AccessibilityStatus.isEnabled` 保留供后续需要时使用。MainActivity 不再自行判定，避免双源。

同时清理 `AndroidManifest.xml` 中 activity 主题继承：由于全 Compose，`<application>` 的 `android:theme` 可保留 AppCompat 或改为无 ActionBar 的 Material 主题以避免崩溃——保留现有 `Theme.AppCompat.DayNight.NoActionBar` 即可（ComponentActivity 不强制 AppCompat 主题）。

- **验证**：`./gradlew :app:compileDebugKotlin` 编译通过。
- **提交**：`git commit -m "refactor(android): MainActivity 迁移到 Compose + Hilt"`

---

### Task 11：构建 APK + 真机联调验证

- 构建：`cd android && export JAVA_HOME=/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home && ./gradlew :app:assembleDebug` → 期望 `BUILD SUCCESSFUL`，产出 `app/build/outputs/apk/debug/app-debug.apk`。
- 安装到真机（用户执行）：`adb install -r app/build/outputs/apk/debug/app-debug.apk`。
- 真机验证清单：
  1. 打开 App，用户视图显示三张卡片，无障碍未授权时显示"去开启"。
  2. 开启无障碍服务 → 卡片变"已授权"，连接卡片指示灯由红→黄（连接中）→绿（已连接）。
  3. 云端确保运行、Mac IP = 10.253.61.158；断开云端 → 指示灯转黄（重连中）并累加重连次数，达 5 次上限后转红。
  4. 连点标题 7 次 → 底部展开调试面板，显示 WS_URL/deviceId/重连次数/动作流水/WS 事件。
  5. 飞书触发一次任务 → 任务卡片显示"执行中：<goal>"，动作流水累加。
- **验证**：`BUILD SUCCESSFUL` + 真机闭环通过。
- **提交**：`git commit -m "build(android): Compose+Hilt 重构完成，真机联调通过"` 并 `git push`。

---

## Self-Review

**spec 覆盖检查**（对照 design 第 8 节交付顺序）：
- [x] domain 层状态模型 → Task 1（ConnectionState/TaskState/AgentStatus/DebugInfo/ActionLog/WsEventLog 全覆盖）
- [x] AgentStateRepository → Task 2（@Singleton + status/debug 两 StateFlow + 全部更新方法）
- [x] Hilt Application + 模块 → Task 4
- [x] 重构 WsClient（注入 Repository + 有限重试）→ Task 3（MAX_RETRY=5、RETRY_DELAY=3s、onFailure 驱动、非轮询）
- [x] 重构 PhoneAgentService（@AndroidEntryPoint + 生命周期驱动）→ Task 5（onServiceConnected 连、onUnbind/onDestroy 断）
- [x] MainViewModel → Task 6（combine 三流 + 连点解锁）
- [x] Compose Theme → Task 7（Material3 + StatusColors 三色）
- [x] Compose UI（用户视图 + 后门调试视图）→ Task 9 + Task 8（连点 7 次解锁）
- [x] 重构 MainActivity → Task 10
- [x] 构建 APK + 真机验证 → Task 11

**占位符扫描**：全部 Task 均为完整可编译代码，无 TODO/TBD/"类似上一步"。

**类型/签名一致性核对**：
- `WsClient.start(baseUrl, deviceId, onTaskStart, onAction, onTaskEnd)` — Task 3 定义，Task 5 调用签名一致。
- `AgentStateRepository` 方法名（updateAccessibility/updateConnection/updateTask/setDebugMeta/setReconnectAttempts/appendActionLog/appendWsEvent）— Task 2 定义，Task 3/5 调用一致。
- `AgentUiState(status, debug, debugUnlocked)` — Task 6 定义，Task 9 Preview 与 Task 10 collect 一致。
- `ActionLog(ts, op, ok, detail)` / `WsEventLog(ts, event, detail)` — Task 1 定义，Task 3/5/8 使用字段一致。
- `TaskState.Running(description)` — Task 1 定义，Task 5/9 使用一致。
- `Executor(service, context)` 与 `executor.execute(op, params)` — 沿用现有 `accessibility/Executor.kt`，签名不变。

**已知约束/风险**：
- WS_URL 硬编码 Mac IP，换网需改常量重构建（用户已接受）。
- Hilt 首次编译触发 KSP 注解处理，耗时略长属正常。
- Compose 依赖已在工具链阶段**全部就位并核实**：`app/build.gradle.kts` 已含 compose-bom、activity-compose、compose-ui/graphics/tooling(-preview)、material3、material-icons-extended，以及 `lifecycle-runtime-compose`（提供 `collectAsStateWithLifecycle`）、`lifecycle-viewmodel-compose`、hilt-android + ksp(hilt-compiler)、hilt-navigation-compose。**无需 Task 前补依赖。**

## 执行方式（计划完成后请选择）

1. **Subagent-Driven（推荐）**：每个 Task 派发独立 fresh subagent 执行 + 两阶段审查，隔离上下文、质量更稳。
2. **Inline Execution**：本会话按 Task 顺序批量执行，每 2-3 个 Task 一个检查点。