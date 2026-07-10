# 通用 Agent：目标由 app 端指定 + app 内实时日志 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把项目从"云端硬编码 goal + 连接即自动开跑"改造成"云端场景无关、goal 由 app 端按钮通过 `task.request` 上行指定、连接后待命、点按钮才开跑、待命期端侧完全不上传 perception"，并在 app 内 DebugPanel 提供实时可读的收发日志流。

**Architecture:** 云端 `gateway.py` 去掉自动 `TaskStart`，新增上行 `task.request` 类型（`protocol.py`），收到后用其 goal 覆盖 session.goal 再下发 `task.start`；`_DEFAULT_GOAL` 改为通用中性词。端侧新增 `UplinkTaskRequest` 协议与 `WsClient.sendTaskRequest`，`MainViewModel` 注入同一 `@Singleton` WsClient 暴露 `onRunTestTask()`，`PhoneAgentService` 用 `taskActive` 门控待命期不 `reportScreen`。日志侧新增 `TraceEvent` 模型 + `AgentStateRepository.appendTrace` + DebugPanel「实时事件流」区块。

**Tech Stack:** 云端 Python 3.14 / FastAPI WebSocket / pydantic / pytest；端侧 Kotlin / AccessibilityService / Jetpack Compose / Hilt / StateFlow / kotlinx.serialization / JUnit4。

---

## File Structure

**云端（server）**
- Modify `server/app/protocol.py` — 新增上行 `TaskRequest` 类型 + 注册进 `_UPLINK_MAP`。
- Modify `server/app/gateway.py` — `_DEFAULT_GOAL` 通用化；删除接后自动 `TaskStart`；WS 循环新增 `task.request` 分支（覆盖 goal + 下发 `task.start`）。
- Modify `server/tests/test_gateway_integration.py` — 补：`_DEFAULT_GOAL` 无场景词；收 `task.request` 后覆盖 goal 并下发 `task.start`；连接后不自动下发 `task.start`。

**端侧（android）**
- Modify `.../protocol/Messages.kt` — 新增 `UplinkTaskRequest`。
- Modify `.../protocol/MessagesTest.kt`（test）— 补 `UplinkTaskRequest` 序列化测试。
- Modify `.../net/WsClient.kt` — 新增 `sendTaskRequest(goal)`。
- Modify `.../domain/AgentModels.kt` — 新增 `TraceEvent` + `TraceDirection`，`DebugInfo` 加 `traceEvents`。
- Modify `.../data/AgentStateRepository.kt` — 新增 `appendTrace()`。
- Modify `.../data/AgentStateRepositoryTest.kt`（test，新建）— `appendTrace` 追加与 `takeLast` 截断。
- Modify `.../accessibility/PhoneAgentService.kt` — `taskActive` 门控 + 埋点 `appendTrace`。
- Modify `.../ui/MainViewModel.kt` — 注入 WsClient，暴露 `onRunTestTask()`，`TEST_GOAL` 常量。
- Modify `.../ui/AgentScreen.kt` — 新增「运行测试任务」按钮。
- Modify `.../ui/DebugPanel.kt` — 新增「实时事件流」区块 + 当前状态摘要。

---

## Task 1: 云端新增上行 `task.request` 协议类型

**Files:**
- Modify: `server/app/protocol.py`
- Test: `server/tests/test_protocol.py`（若不存在则新建）

- [ ] **Step 1: 写失败测试 —— parse_uplink 能解析 task.request**

在 `server/tests/test_protocol.py` 追加（无该文件则新建，顶部 `from app.protocol import parse_uplink, TaskRequest`）：

```python
def test_parse_uplink_task_request():
    raw = '{"type":"task.request","goal":"打开设置"}'
    msg = parse_uplink(raw)
    assert isinstance(msg, TaskRequest)
    assert msg.type == "task.request"
    assert msg.goal == "打开设置"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd server && .venv/bin/python -m pytest tests/test_protocol.py::test_parse_uplink_task_request -v`
Expected: FAIL（`ImportError: cannot import name 'TaskRequest'` 或 `unknown uplink type`）

- [ ] **Step 3: 实现 TaskRequest 并注册**

在 `server/app/protocol.py` 的 `Heartbeat` 类之后、`Uplink = Union[...]` 之前新增：

```python
class TaskRequest(BaseModel):
    type: Literal["task.request"] = "task.request"
    goal: str
```

把 `Uplink` 联合类型与映射表改为：

```python
Uplink = Union[Perception, ActionResult, NewMessage, Heartbeat, TaskRequest]

_UPLINK_MAP = {
    "perception": Perception,
    "action.result": ActionResult,
    "event.newMessage": NewMessage,
    "heartbeat": Heartbeat,
    "task.request": TaskRequest,
}
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd server && .venv/bin/python -m pytest tests/test_protocol.py::test_parse_uplink_task_request -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add server/app/protocol.py server/tests/test_protocol.py
git commit -m "feat(server): add task.request uplink protocol type"
```

---

## Task 2: 云端 gateway 去自动开跑 + task.request 触发 + goal 通用化

**Files:**
- Modify: `server/app/gateway.py:37`（`_DEFAULT_GOAL`）、`:73-75`（自动 TaskStart）、`:96` 后（新增分支）
- Test: `server/tests/test_gateway_integration.py`

- [ ] **Step 1: 写失败测试 —— goal 通用化 + 待命 + task.request 触发**

先看现有集成测试如何建立 WS（`from fastapi.testclient import TestClient`、`create_app()`、`client.websocket_connect(f"/ws/{device}")`）。在 `server/tests/test_gateway_integration.py` 追加三条：

```python
def test_default_goal_has_no_scenario_words():
    import app.gateway as gw
    for word in ("飞书", "Android", "环球资讯", "lark"):
        assert word not in gw._DEFAULT_GOAL


def test_no_task_start_before_request(monkeypatch):
    monkeypatch.setenv("PHONEAGENT_FAKE_LLM", '[{"op":"read_screen","params":{}}]')
    from app.gateway import create_app
    from fastapi.testclient import TestClient
    client = TestClient(create_app())
    with client.websocket_connect("/ws/dev1") as ws:
        ws.send_text('{"type":"heartbeat","deviceId":"dev1","ts":1}')
        first = ws.receive_text()
        # 待命期不应先收到 task.start；心跳只回 read_screen action
        assert '"type":"task.start"' not in first


def test_task_request_overrides_goal_and_starts(monkeypatch):
    monkeypatch.setenv("PHONEAGENT_FAKE_LLM", '[{"op":"read_screen","params":{}}]')
    from app.gateway import create_app
    from fastapi.testclient import TestClient
    import json as _json
    client = TestClient(create_app())
    with client.websocket_connect("/ws/dev1") as ws:
        ws.send_text('{"type":"task.request","goal":"打开设置页"}')
        msg = _json.loads(ws.receive_text())
        assert msg["type"] == "task.start"
        assert msg["goal"] == "打开设置页"
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd server && .venv/bin/python -m pytest tests/test_gateway_integration.py -v -k "default_goal or task_start or task_request"`
Expected: FAIL（`_DEFAULT_GOAL` 含"飞书"；连接即收到 task.start；无 task.request 分支）

- [ ] **Step 3: 改 _DEFAULT_GOAL 为通用中性词**

`server/app/gateway.py:37` 改为：

```python
_DEFAULT_GOAL = "等待用户下发任务目标"
```

- [ ] **Step 4: 删除连接后自动下发 TaskStart**

删除 `server/app/gateway.py` 中这段（位于 while 循环前）：

```python
        await websocket.send_text(
            TaskStart(taskId=session.task_id, goal=session.goal, target=device_id).to_json()
        )
```

- [ ] **Step 5: 在 while 循环内新增 task.request 分支**

在 `if uplink.type == "action.result":` 分支**之前**插入：

```python
            if uplink.type == "task.request":
                session.goal = uplink.goal
                logger.info("task.request goal=%s", uplink.goal)
                await websocket.send_text(
                    TaskStart(
                        taskId=session.task_id, goal=session.goal, target=device_id
                    ).to_json()
                )
                continue
```

- [ ] **Step 6: 跑目标测试确认通过 + 全量回归**

Run: `cd server && .venv/bin/python -m pytest tests/ -q`
Expected: PASS（全绿；若旧集成测试断言"连接即收到 task.start"，改为先 `ws.send_text` task.request 再收）

- [ ] **Step 7: 提交**

```bash
git add server/app/gateway.py server/tests/test_gateway_integration.py
git commit -m "feat(server): drive goal via task.request, no auto-start, neutralize default goal"
```

---

## Task 3: 端侧新增 `UplinkTaskRequest` 协议

**Files:**
- Modify: `android/app/src/main/java/com/example/phoneagent/protocol/Messages.kt`
- Test: `android/app/src/test/java/com/example/phoneagent/protocol/MessagesTest.kt`

- [ ] **Step 1: 写失败测试 —— UplinkTaskRequest 序列化**

在 `MessagesTest.kt` 的 `MessagesTest` 类内追加：

```kotlin
@Test
fun task_request_serializes() {
    val m = UplinkTaskRequest(goal = "打开设置")
    val out = json.encodeToString(m)
    assertTrue(out.contains("\"type\":\"task.request\""))
    assertTrue(out.contains("\"goal\":\"打开设置\""))
}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd android && ./gradlew :app:testDebugUnitTest --tests "com.example.phoneagent.protocol.MessagesTest.task_request_serializes"`
Expected: FAIL（`Unresolved reference: UplinkTaskRequest`）

- [ ] **Step 3: 实现 UplinkTaskRequest**

在 `Messages.kt` 的 `UplinkHeartbeat` 之后新增：

```kotlin
@Serializable
data class UplinkTaskRequest(
    val type: String = "task.request",
    val goal: String,
)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd android && ./gradlew :app:testDebugUnitTest --tests "com.example.phoneagent.protocol.MessagesTest.task_request_serializes"`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add android/app/src/main/java/com/example/phoneagent/protocol/Messages.kt android/app/src/test/java/com/example/phoneagent/protocol/MessagesTest.kt
git commit -m "feat(android): add UplinkTaskRequest protocol"
```

---

## Task 4: WsClient 新增 `sendTaskRequest`

**Files:**
- Modify: `android/app/src/main/java/com/example/phoneagent/net/WsClient.kt`

> 说明：`WsClient` 依赖 OkHttp 真实连接，无纯单测；本任务靠编译 + 后续真机联调验证。埋点在 Task 8 统一加。

- [ ] **Step 1: 新增 import 与方法**

在 `WsClient.kt` 顶部 import 区补 `import com.example.phoneagent.protocol.UplinkTaskRequest`。
在 `sendPerception` 方法之后新增：

```kotlin
fun sendTaskRequest(goal: String) {
    ws?.send(json.encodeToString(UplinkTaskRequest(goal = goal)))
}
```

- [ ] **Step 2: 编译确认通过**

Run: `cd android && ./gradlew :app:compileDebugKotlin`
Expected: BUILD SUCCESSFUL

- [ ] **Step 3: 提交**

```bash
git add android/app/src/main/java/com/example/phoneagent/net/WsClient.kt
git commit -m "feat(android): WsClient.sendTaskRequest"
```

---

## Task 5: TraceEvent 日志模型 + Repository.appendTrace

**Files:**
- Modify: `android/app/src/main/java/com/example/phoneagent/domain/AgentModels.kt`
- Modify: `android/app/src/main/java/com/example/phoneagent/data/AgentStateRepository.kt`
- Test: `android/app/src/test/java/com/example/phoneagent/data/AgentStateRepositoryTest.kt`（新建）

- [ ] **Step 1: 写失败测试 —— appendTrace 追加与截断**

新建 `AgentStateRepositoryTest.kt`：

```kotlin
package com.example.phoneagent.data

import com.example.phoneagent.domain.TraceDirection
import com.example.phoneagent.domain.TraceEvent
import org.junit.Assert.assertEquals
import org.junit.Test

class AgentStateRepositoryTest {

    @Test
    fun appendTrace_keeps_last_50() {
        val repo = AgentStateRepository()
        repeat(60) { i ->
            repo.appendTrace(TraceEvent(i.toLong(), TraceDirection.UP, "perception", "n=$i"))
        }
        val events = repo.debug.value.traceEvents
        assertEquals(50, events.size)
        assertEquals("n=59", events.last().summary)
    }

    @Test
    fun appendTrace_appends_in_order() {
        val repo = AgentStateRepository()
        repo.appendTrace(TraceEvent(1L, TraceDirection.UP, "task.request", "goal=x"))
        repo.appendTrace(TraceEvent(2L, TraceDirection.DOWN, "task.start", "goal=x"))
        val events = repo.debug.value.traceEvents
        assertEquals(2, events.size)
        assertEquals("task.request", events.first().kind)
        assertEquals("task.start", events.last().kind)
    }
}
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd android && ./gradlew :app:testDebugUnitTest --tests "com.example.phoneagent.data.AgentStateRepositoryTest"`
Expected: FAIL（`Unresolved reference: TraceEvent` / `appendTrace`）

- [ ] **Step 3: 新增 TraceEvent 模型**

在 `AgentModels.kt` 的 `WsEventLog` 之后新增：

```kotlin
/** 事件方向：上行 / 下行 / 本地信息。 */
enum class TraceDirection { UP, DOWN, INFO }

/** 统一收发事件流（app 内实时可读日志）。 */
data class TraceEvent(
    val ts: Long,
    val direction: TraceDirection,
    val kind: String,
    val summary: String = "",
)
```

在 `DebugInfo` 的字段列表末尾（`reconnectAttempts` 之后）新增：

```kotlin
    val traceEvents: List<TraceEvent> = emptyList(),
```

- [ ] **Step 4: Repository 新增 appendTrace**

在 `AgentStateRepository.kt` 顶部 import 区补 `import com.example.phoneagent.domain.TraceEvent`。
在 `appendWsEvent` 方法之后新增：

```kotlin
fun appendTrace(event: TraceEvent) {
    _debug.update { it.copy(traceEvents = (it.traceEvents + event).takeLast(MAX_LOG)) }
}
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd android && ./gradlew :app:testDebugUnitTest --tests "com.example.phoneagent.data.AgentStateRepositoryTest"`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add android/app/src/main/java/com/example/phoneagent/domain/AgentModels.kt android/app/src/main/java/com/example/phoneagent/data/AgentStateRepository.kt android/app/src/test/java/com/example/phoneagent/data/AgentStateRepositoryTest.kt
git commit -m "feat(android): TraceEvent model + appendTrace"
```

---

## Task 6: PhoneAgentService 加 taskActive 门控 + 收发埋点

**Files:**
- Modify: `android/app/src/main/java/com/example/phoneagent/accessibility/PhoneAgentService.kt`

> 说明：AccessibilityService 需真机运行，无纯单测；靠编译 + 真机联调验证。

- [ ] **Step 1: 补 import 与 taskActive 字段**

顶部 import 区补：

```kotlin
import com.example.phoneagent.domain.TraceDirection
import com.example.phoneagent.domain.TraceEvent
```

在 `private var pendingReport: Runnable? = null` 之后新增：

```kotlin
    @Volatile private var taskActive = false
```

- [ ] **Step 2: onTaskStart/onAction/onTaskEnd 加门控与埋点**

把 `wsClient.start(...)` 里的三个回调替换为：

```kotlin
            onTaskStart = { goal, _ ->
                taskActive = true
                repo.updateTask(TaskState.Running(goal))
                repo.appendTrace(TraceEvent(System.currentTimeMillis(), TraceDirection.DOWN, "task.start", "goal=$goal"))
                reportScreen()
            },
            onAction = { action ->
                repo.appendTrace(TraceEvent(System.currentTimeMillis(), TraceDirection.DOWN, "action", "${action.op} ${action.params}"))
                val ok = executor.execute(action.op, action.params)
                wsClient.sendActionResult(action.actionId, ok)
                repo.appendActionLog(ActionLog(System.currentTimeMillis(), action.op, ok))
                repo.appendTrace(TraceEvent(System.currentTimeMillis(), TraceDirection.UP, "action.result", "${action.op} ${if (ok) "ok" else "fail"}"))
                if (action.op == "read_screen") reportScreen()
            },
            onTaskEnd = { reason ->
                taskActive = false
                repo.updateTask(TaskState.Idle)
                repo.appendTrace(TraceEvent(System.currentTimeMillis(), TraceDirection.DOWN, "task.end", reason))
            },
```

- [ ] **Step 3: onAccessibilityEvent 加 taskActive 门控**

把 `onAccessibilityEvent` 方法体首行改为（待命期不采集不上报）：

```kotlin
    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (!taskActive) return
        pendingReport?.let { handler.removeCallbacks(it) }
        val r = Runnable { reportScreen() }
        pendingReport = r
        handler.postDelayed(r, DEBOUNCE_MS)
    }
```

- [ ] **Step 4: reportScreen 加上行埋点**

把 `reportScreen()` 里 `wsClient.sendPerception(perception)` 前一行加埋点：

```kotlin
    private fun reportScreen() {
        val root = rootInActiveWindow ?: return
        val nodes = NodeFlattener.flatten(root)
        val perception = UplinkPerception(
            nodeTree = nodes,
            pkg = root.packageName?.toString() ?: "",
            activity = "",
            ts = System.currentTimeMillis(),
        )
        repo.appendTrace(TraceEvent(System.currentTimeMillis(), TraceDirection.UP, "perception", "pkg=${perception.pkg} nodes=${nodes.size}"))
        wsClient.sendPerception(perception)
    }
```

- [ ] **Step 5: 编译确认通过**

Run: `cd android && ./gradlew :app:compileDebugKotlin`
Expected: BUILD SUCCESSFUL

- [ ] **Step 6: 提交**

```bash
git add android/app/src/main/java/com/example/phoneagent/accessibility/PhoneAgentService.kt
git commit -m "feat(android): taskActive gate + trace instrumentation in service"
```

---

## Task 7: MainViewModel 注入 WsClient + onRunTestTask + TEST_GOAL

**Files:**
- Modify: `android/app/src/main/java/com/example/phoneagent/ui/MainViewModel.kt`

> 说明：`WsClient` 是 `@Singleton`，ViewModel 注入到的是与 Service 相同的实例，故按钮可直接发 task.request。`TEST_GOAL`（飞书场景）作为测试常量只放在此 UI 层，不进核心。

- [ ] **Step 1: 补 import 与构造注入**

顶部 import 区补：

```kotlin
import com.example.phoneagent.net.WsClient
```

把构造函数改为：

```kotlin
@HiltViewModel
class MainViewModel @Inject constructor(
    private val repo: AgentStateRepository,
    private val wsClient: WsClient,
) : ViewModel() {
```

- [ ] **Step 2: 新增 TEST_GOAL 常量与 onRunTestTask 方法**

把 companion object 改为：

```kotlin
    private companion object {
        const val UNLOCK_THRESHOLD = 7

        // 测试专用 goal（飞书找 Android 群），仅存于 UI 层，绝不进入决策核心。
     const val TEST_GOAL = "在飞书里完成以下任务链，全程不发送任何消息：" +
            "1) 打开飞书后检测当前账号；" +
            "2) 若当前为企业账号\"环球资讯\"，切换到个人账号\"飞书个人用户\"；" +
            "3) 找到群名包含 \"Android\" 的群聊并进入；" +
            "4) 点击输入框使其获得焦点即完成；" +
            "5) 禁止发送任何消息。"
    }
```

在 `onHideDebug()` 方法之后新增：

```kotlin
    /** 测试按钮：向云端发送 task.request(TEST_GOAL) 启动测试链路。 */
    fun onRunTestTask() {
        wsClient.sendTaskRequest(TEST_GOAL)
        repo.appendTrace(
            com.example.phoneagent.domain.TraceEvent(
                System.currentTimeMillis(),
                com.example.phoneagent.domain.TraceDirection.UP,
                "task.request",
                "goal=飞书找Android群(测试)",
            )
        )
    }
```

- [ ] **Step 3: 编译确认通过**

Run: `cd android && ./gradlew :app:compileDebugKotlin`
Expected: BUILD SUCCESSFUL

- [ ] **Step 4: 提交**

```bash
git add android/app/src/main/java/com/example/phoneagent/ui/MainViewModel.kt
git commit -m "feat(android): MainViewModel onRunTestTask + TEST_GOAL (ui-only)"
```

---

## Task 8: AgentScreen 新增「运行测试任务」按钮

**Files:**
- Modify: `android/app/src/main/java/com/example/phoneagent/ui/AgentScreen.kt`
- Modify: `android/app/src/main/java/com/example/phoneagent/MainActivity.kt`（若在此接线 ViewModel 回调）

- [ ] **Step 1: AgentScreen 增加回调参数�按钮**

把 `AgentScreen` 签名加一个回调：

```kotlin
@Composable
fun AgentScreen(
    uiState: AgentUiState,
    onTitleTap: () -> Unit,
    onOpenAccessibility: () -> Unit,
    onHideDebug: () -> Unit,
    onRunTestTask: () -> Unit,
) {
```

在 `TaskCard(uiState.status.task)` 之后、`if (uiState.debugUnlocked)` 之前插入按钮（仅连接后可点）：

```kotlin
            Button(
                onClick = onRunTestTask,
                enabled = uiState.status.connection == ConnectionState.CONNECTED,
                modifier = Modifier.fillMaxWidth(),
            ) { Text("运行测试任务（飞书找 Android 群）") }
```

两个 `@Preview` 的 `AgentScreen(...)` 调用末尾补 `onRunTestTask = {},`。

- [ ] **Step 2: MainActivity 接线**

找到调用 `AgentScreen(` 的地方（`grep_search "AgentScreen(" --glob "*.kt"`），补 `onRunTestTask = viewModel::onRunTestTask,`。

- [ ] **Step 3: 编译确认通过**

Run: `cd android && ./gradlew :app:compileDebugKotlin`
Expected: BUILD SUCCESSFUL

- [ ] **Step 4: 提交**

```bash
git add android/app/src/main/java/com/example/phoneagent/ui/AgentScreen.kt android/app/src/main/java/com/example/phoneagent/MainActivity.kt
git commit -m "feat(android): run-test-task button on AgentScreen"
```

---

## Task 9: DebugPanel 新增「实时事件流」区块 + 当前状态摘要

**Files:**
- Modify: `android/app/src/main/java/com/example/phoneagent/ui/DebugPanel.kt`

- [ ] **Step 1: 补 import**

顶部 import 区补：

```kotlin
import com.example.phoneagent.domain.TraceDirection
import com.example.phoneagent.domain.TraceEvent
import java.text.SimpleDateFormat
import java.util.Locale
```

- [ ] **Step 2: 新增格式化工具函数（文件底部，DebugPanel 外）**

```kotlin
private val traceTimeFmt = SimpleDateFormat("HH:mm:ss", Locale.getDefault())

private fun TraceEvent.formatLine(): String {
    val arrow = when (direction) {
        TraceDirection.UP -> "↑"
        TraceDirection.DOWN -> "↓"
        TraceDirection.INFO -> "·"
    }
    return "${traceTimeFmt.format(ts)} $arrow $kind ${summary}".trimEnd()
}
```

- [ ] **Step 3: 在「WS 事件」区块之后、收起按钮之前插入实时事件流**

```kotlin
            Text("实时事件流", style = MaterialTheme.typography.titleSmall)
            if (debug.traceEvents.isEmpty()) {
                Text("（暂无，点\"运行测试任务\"后开始）", style = MaterialTheme.typography.bodySmall)
            } else {
                debug.traceEvents.takeLast(30).reversed().forEach { ev ->
                    Text(
                        ev.formatLine(),
                        style = MaterialTheme.typography.bodySmall,
                        fontFamily = FontFamily.Monospace,
                    )
                }
            }
```

- [ ] **Step 4: 编译确认通过**

Run: `cd android && ./gradlew :app:compileDebugKotlin`
Expected: BUILD SUCCESSFUL

- [ ] **Step 5: 提交**

```bash
git add android/app/src/main/java/com/example/phoneagent/ui/DebugPanel.kt
git commit -m "feat(android): live trace event stream in DebugPanel"
```

---

## Task 10: 全量回归 + 真机联调验证

- [ ] **Step 1: 云端全量测试**

Run: `cd server && .venv/bin/python -m pytest tests/ -q`
Expected: 全绿

- [ ] **Step 2: 端侧全量单测**

Run: `cd android && ./gradlew :app:testDebugUnitTest`
Expected: BUILD SUCCESSFUL

- [ ] **Step 3: 装 apk 真机验证**

Run: `cd android && ./gradlew :app:installDebug`
手动验证：① 连接后待命，云端 gateway.log 无 perception 日志 ② 连点标题 7 次解锁 DebugPanel ③ 点「运行测试任务」→ 事件流出现 `↑ task.request` → `↓ task.start` → `↑ perception` → `↓ action` … ④ 全程不发送消息。

- [ ] **Step 4: 提交（如有联调微调）**

```bash
git add -A && git commit -m "chore: e2e verification for app-driven goal + live log"
```

---

## Self-Review

**1. Spec 覆盖：**
- goal 通用化 → Task 2 Step 3 ✓
- goal 由 app task.request 指定 → Task 1（协议）+ Task 2（云端分支）+ Task 3/4（端侧协议+发送）+ Task 7/8（按钮）✓
- 连接后不自动开跑 → Task 2 Step 4 ✓
- TEST_GOAL 端侧 UI 常量 → Task 7 Step 2 ✓
- taskActive 门控（待命不上报）→ Task 6 Step 1/3 ✓
- TraceEvent 实时日志 → Task 5（模型/repo）+ Task 6（埋点）+ Task 9（展示）✓
- Debug 后门连点 7 次 → 已存在，无需改动 ✓
- 云端单测 goal 无场景词 / task.request 覆盖 → Task 2 Step 1 ✓
- 端侧 appendTrace/takeLast 测试 → Task 5 Step 1 ✓

**2. Placeholder 扫描：** 无 TBD/TODO；所有 code step 均有完整代码。✓

**3. 类型一致性：** `TraceEvent(ts, direction, kind, summary)`、`TraceDirection{UP,DOWN,INFO}`、`appendTrace`、`UplinkTaskRequest(type,goal)`、`sendTaskRequest(goal)`、`TaskRequest(type,goal)`、`onRunTestTask` 全程命名一致。✓

**安全约束复核：** 云端 `protocol.py`/`gateway.py` 不含任何场景词；飞书内容仅出现在端侧 `MainViewModel.TEST_GOAL` 与联调脚本。✓
