# JoyPhone Android App 重构设计

日期：2026-07-09
状态：待用户审阅

## 1. 背景与目标

JoyPhone 是"飞书触发 → 云端 LLM 决策 → 端侧无障碍执行"的手机自动化 Agent。

当前端侧 App 存在两类问题：

1. **连接架构缺陷**：WS 连接只在 `onServiceConnected()` 单次触发，`onFailure` 仅打日志、无恢复，首次失败即永久断连。
2. **界面简陋**：原生 View + 一个文案 + 一个按钮，无法反映权限/连接/任务的实时状态。

本次重构目标：用现代 Android 架构（Compose + Hilt + Coroutines/Flow）正式重写 App，实现**事件驱动的连接管理**与**分层的精美状态面板**。

## 2. 核心决策（已与用户对齐）

| 决策点 | 结论 |
|--------|------|
| App 定位 | 先做"台执行器 + 状态面板"（方向 A），架构为未来"操作入口"（方向 B）预留扩展 |
| 云端地址管理 | BuildConfig 编译期写死（`WS_URL`），换网重新构建 |
| 连接生命周期 | 事件驱动：服务绑定=连接时机，服务解绑=断开时机 |
| 断线恢复 | `onFailure` 事件触发的**有限次重试**（非轮询），Service 存活期间尝试恢复 |
| UI 分层 | 用户视图（简洁）+ 隐藏调试视图（后门：连点标题/版本号 N 次触发） |

## 3. 架构：Clean Architecture 分层

```
ui/          Compose UI + ViewModel（展示层）
domain/      状态模型 + Repository 接口（业务层，纯 Kotlin 可测）
data/        Repository 实现 + WsClient（数据层）
accessibility/  PhoneAgentService（无障碍执行，驱动连接生命周期）
di/          Hilt 模块
```

**单向数据流**：
```
PhoneAgentService (生命周期事件)
        │ onServiceConnected / onUnbind
        ▼
WsClient (连接 + onOpen/onFailure/onClosing 事件)
        │ 更新
        ▼
AgentStateRepository (StateFlow 单例，唯一状态源)
        │ 观察
        ▼
MainViewModel (暴露 uiState: StateFlow<AgentUiState>)
        │ collectAsStateWithLifecycle
        ▼
Compose UI (实时刷新)
```

## 4. 关键组件设计

### 4.1 domain 层（纯 Kotlin，可独立理解）

```kotlin
enum class ConnectionState { DISCONNECTED, CONNECTING, CONNECTED, RECONNECTING }

sealed interface TaskState {
    data object Idle : TaskState
    data class Running(val description: String) : TaskState
}

// 面向用户的状态
data class AgentStatus(
    val accessibilityGranted: Boolean,
    val connection: ConnectionState,
    val task: TaskState,
)

// 调试专用信息（后门才展示）
data class DebugInfo(
    val wsUrl: String,
    val deviceId: String,
    val recentActions: List<ActionLog>,   // 最近动作流水
    val wsEvents: List<WsEventLog>,        // WS 底层事件
    val reconnectAttempts: Int,
)
```

### 4.2 AgentStateRepository（唯一状态源）

- 单例（Hilt `@Singleton`），是 Service 与 UI 的唯一桥梁。
- 内部持有 `MutableStateFlow<AgentStatus>` + `MutableStateFlow<DebugInfo>`。
- 提供 `updateConnection()` / `updateTask()` / `appendActionLog()` / `appendWsEvent()` 等方法，供 WsClient / Service 调用。
- 对外暴露只读 `StateFlow`，供 ViewModel 观察。

### 4.3 WsClient（数据层，注入 Repository）

- 通过 Hilt 注入 `AgentStateRepository`。
- `onOpen` → `repo.updateConnection(CONNECTED)`；`onClosing` → `DISCONNECTED`；`onFailure` → 触发**有限重试**逻辑并置 `RECONNECTING`。
- 重试策略：失败后固定间隔（如 3s）重试，最多 N 次（如 5 次），连上即清零；由 `onFailure` 事件驱动，非空转轮询。
- 收到下行指令 → `repo.appendActionLog()`；同时保留原有 dispatch → Service 执行。
- **删除临时 `Log.x` 诊断，用 Repository 状态流替代**（调试信息进 DebugInfo 由后门查看）。

### 4.4 PhoneAgentService（事件驱动连接）

- 标注 `@AndroidEntryPoint`，注入 `WsClient`（或连接管理器）与 `AgentStateRepository`。
- `onServiceConnected()` → 置 `accessibilityGranted = true` → 发起 WS 连接。
- `onUnbind()` / `onDestroy()` → 断开 WS → 置 `accessibilityGranted = false`, `DISCONNECTED`。
- 保留 `onAccessibilityEvent` debounce 上报屏幕的既有逻辑。

### 4.5 UI 层

**AgentApplication**：`@HiltAndroidApp`。

**MainViewModel**（`@HiltViewModel`）：
- 注入 `AgentStateRepository`。
- 组合 `AgentStatus` + 权限实时状态，暴露 `uiState: StateFlow<AgentUiState>`。
- 提供 `onOpenAccessibilitySettings()`、`onDebugUnlock()`（连点计数）等交互事件。

**Compose UI**：
- **用户视图**（默认）：
  - 无障碍权限卡片（已授权/未授权 + 去开启按钮）
  - WS 连接状态卡片（颜色指示器：绿=已连 / 黄=连接中·重连中 / 红=断开）
  - 当前任务卡片（空闲 / 执行中 + 人话描述）
- **调试视图**（后门）：连点标题/版本号 N 次（如 7 次）解锁，展开显示 `DebugInfo`：完整 WS_URL、deviceId、最近动作流水、WS 事件日志、重连次数。可用可展开区域或独立弹窗，实时刷新。
- Material3 主题（配色/字体/深浅色），`@Preview` 覆盖各状态。

## 5. 错误处理

- WS 连接失败：`onFailure` → 有限重试 → 达上限置 `DISCONNECTED`，调试视图记录失败原因与重连次数。
- 无障碍未授权：UI 明确提示 + 去开启入口。
- 明文流量：已由 `usesCleartextTraffic="true"` 放行（保留）。

## 6. 测试策略

按用户要求，本次**不写重复性单元测试**。仅保留必要的纯逻辑校验（如已有的 `AccessibilityStatus.isEnabled`），Compose 用 `@Preview` 覆盖各状态视图做视觉验证。核心验证以**真机联调跑通闭环**为准。

## 7. 不做的事（YAGNI）

- 不做 App 内地址编辑（BuildConfig 写死）。
- 不做 App 内下发任务/历史列表（方向 B 留待后续）。
- 不做持久化存储（DataStore/Room）。
- 不做退避轮询（用户明确否定）。

## 8. 交付顺序

1. Gradle 工具链升级（已完成 libs.versions.toml / build.gradle.kts）
2. domain 层状态模型
3. AgentStateRepository
4. Hilt Application + 模块
5. 重构 WsClient（注入 Repository + 有限重试）
6. 重构 PhoneAgentService（@AndroidEntryPoint + 生命周期驱动）
7. MainViewModel
8. Compose Theme
9. Compose UI（用户视图 + 后门调试视图）
10. 重构 MainActivity（setContent + Hilt）
11. 构建 APK + 真机验证 WS 自动连接 + UI 展示
12. commit + push