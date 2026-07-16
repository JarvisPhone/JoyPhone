# 探针采样（阶段一）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 给 App 加一个「场景采样」入口：用户输标签、点按钮、10 秒延时后自动抓当前屏 nodeTree 并上报云端，云端落盘为 JSON 样本，供后续人工分析场景特征。

**Architecture:** 采样链路与现有决策链路完全解耦。UI（MainViewModel）通过共享单例 `AgentStateRepository` 发出「采样请求」信号（label + 延时秒数）；无障碍服务 `PhoneAgentService` 观察该信号，延时结束后复用现有抓帧逻辑（`rootInActiveWindow` → `NodeFlattener.flatten`）抓帧，组 `sample.capture` 上行消息经 `WsClient` 发出；云端 `gateway.py` 收到后落盘到 `server/data/samples/<label>-<ts>.json`。**全程不碰 decision.py / PKG_GUARD / session.py。**

**Tech Stack:** Kotlin + Jetpack Compose + Hilt + kotlinx.serialization + OkHttp WebSocket（Android）；Python + FastAPI + pydantic + pytest（云端）。

---

## 文件结构

**云端（先做，可自动化测试）：**
- Modify `server/app/protocol.py` — 新增 `SampleCapture` 上行类型，注册进 `Uplink` 联合类型与 `_UPLINK_MAP`。
- Modify `server/app/gateway.py` — 处理 `sample.capture`：落盘到 `server/data/samples/<label>-<ts>.json`；抽出可测的落盘纯函数 `_persist_sample`。
- Create `server/data/samples/.gitkeep` — 占位保证目录存在（样本文件本身不入库）。
- Modify `server/tests/test_protocol.py` — `SampleCapture` 解析测试。
- Modify `server/tests/test_gateway_integration.py` — 落盘测试。

**Android（后做，手动实机验证）：**
- Modify `.../protocol/Messages.kt` — 新增 `UplinkSampleCapture` 数据类。
- Modify `.../net/WsClient.kt` — 新增 `sendSampleCapture(...)`。
- Create `.../domain/SampleRequest.kt` — 采样请求信号数据类。
- Modify `.../data/AgentStateRepository.kt` — 新增 `sampleRequests` SharedFlow 与 `requestSample(label)`。
- Modify `.../accessibility/PhoneAgentService.kt` — 观察采样请求，延时抓帧上报；抽出 `captureNodeTreeForSample`。
- Modify `.../ui/MainViewModel.kt` — 新增 `onCaptureSample(label)` 与倒计时 UI 状态。
- Modify `.../ui/AgentScreen.kt` — 主界面常驻「场景采样」卡片。
- Modify `.../MainActivity.kt` — 传入 `onCaptureSample` 回调。

---

## 阶段 A：云端

### Task 1: protocol.py 新增 SampleCapture 上行类型

**Files:**
- Modify: `server/app/protocol.py`
- Test: `server/tests/test_protocol.py`

- [ ] **Step 1: 写失败测试**

在 `server/tests/test_protocol.py` 末尾追加：

```python
def test_parse_sample_capture_uplink():
    from app.protocol import SampleCapture
    raw = (
        '{"type":"sample.capture","label":"minus_one",'
        '"nodeTree":[{"id":"n1","text":"小布建议"}],'
        '"pkg":"com.android.launcher","activity":"Launcher","ts":123,"device":"OPPO"}'
    )
    msg = parse_uplink(raw)
    assert isinstance(msg, SampleCapture)
    assert msg.label == "minus_one"
    assert msg.pkg == "com.android.launcher"
    assert msg.nodeTree[0].text == "小布建议"
    assert msg.device == "OPPO"


def test_sample_capture_rejects_missing_label():
    with pytest.raises(ValidationError):
        parse_uplink('{"type":"sample.capture","pkg":"p","activity":"a","ts":0}')


def test_sample_capture_device_defaults_empty():
    raw = '{"type":"sample.capture","label":"home_first","nodeTree":[],"pkg":"p","activity":"a","ts":0}'
    msg = parse_uplink(raw)
    assert msg.device == ""
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `cd server && uv run pytest tests/test_protocol.py::test_parse_sample_capture_uplink -v`
Expected: FAIL —— `ImportError: cannot import name 'SampleCapture'`

- [ ] **Step 3: 实现 SampleCapture 并注册**

在 `server/app/protocol.py` 的`ConfirmResponse` 类定义之后、`Uplink = Union[...]` 之前，插入：

```python
class SampleCapture(BaseModel):
    """上行:探针采样帧。App 延时抓帧后上报,云端落盘供人工分析场景特征。"""
    type: Literal["sample.capture"] = "sample.capture"
    label: str
    nodeTree: list[Node] = Field(default_factory=list)
    pkg: str = ""
    activity: str = ""
    ts: int = 0
    device: str = ""
```

把 `Uplink` 一行替换为（加上 `SampleCapture`）：

```python
Uplink = Union[Perception, ActionResult, NewMessage, Heartbeat, TaskRequest, ConfirmResponse, SampleCapture]
```

在 `_UPLINK_MAP` 字典内，`"task.confirm_response": ConfirmResponse,` 这一行之后追加：

```python
    "sample.capture": SampleCapture,
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `cd server && uv run pytest tests/test_protocol.py -v`
Expected: PASS（含新增 3 个用例，且原有用例不回归）

- [ ] **Step 5: 提交**

```bash
git add server/app/protocol.py server/tests/test_protocol.py
git commit -m "feat(protocol): 新增 sample.capture 上行采样帧类型"
```

### Task 2: gateway.py 落盘采样帧

**Files:**
- Modify: `server/app/gateway.py`
- Create: `server/data/samples/.gitkeep`
- Test: `server/tests/test_gateway_integration.py`

- [ ] **Step 1: 建目录占位文件**

```bash
mkdir -p server/data/samples && touch server/data/samples/.gitkeep
```

- [ ] **Step 2: 写失败测试**

在 `server/tests/test_gateway_integration.py` 末尾追加：

```python
def test_persist_sample_writes_json_file(tmp_path):
    from app.gateway import _persist_sample
    from app.protocol import SampleCapture

    sample = SampleCapture(
        label="minus_one",
        nodeTree=[],
        pkg="com.android.launcher",
        activity="Launcher",
        ts=1784168979000,
        device="OPPO",
    )
    path = _persist_sample(sample, base_dir=tmp_path)

    assert path.exists()
    assert path.parent == tmp_path
    assert path.name.startswith("minus_one-")
    assert path.suffix == ".json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["label"] == "minus_one"
    assert data["pkg"] == "com.android.launcher"
    assert data["device"] == "OPPO"


def test_gateway_sample_capture_persists_file(tmp_path, monkeypatch):
    import app.gateway as gw
    monkeypatch.setattr(gw, "_SAMPLES_DIR", tmp_path)
    app = create_app()
    client = TestClient(app)
    sample_msg = json.dumps({
        "type": "sample.capture",
        "label": "home_first",
        "nodeTree": [{"id": "n1", "text": "相机"}],
        "pkg": "com.android.launcher",
        "activity": "Launcher",
        "ts": 1720000000,
        "device": "OPPO",
    })
    with client.websocket_connect("/ws/device-1") as ws:
        ws.send_text(sample_msg)
        ws.send_text(json.dumps({"type": "heartbeat","deviceId": "device-1", "ts": 1}))
        ws.receive_json()  # 采样不回消息,后发心跳确认连接仍活着且能拿到回复

    files = list(tmp_path.glob("home_first-*.json"))
    assert len(files) == 1
```

- [ ] **Step 3: 运行测试，确认失败**

Run: `cd server && uv run pytest tests/test_gateway_integration.py::test_persist_sample_writes_json_file -v`
Expected: FAIL —— `ImportError: cannot import name '_persist_sample'`

- [ ] **Step 4: 实现落盘**

在 `server/app/gateway.py` 顶部 import 区（`from app.protocol import (` 块内）把 `SampleCapture` 加入导入列表：

```python
from app.protocol import (
    Action,
    ConfirmResponse,
    SampleCapture,
    TaskAbort,
    TaskConfirm,
    TaskDone,
    TaskStart,
    parse_uplink,
)
```

在 `_DEFAULT_GOAL = "等待用户下发任务目标"` 这一行之后，新增模块级常量与落盘函数：

```python
_SAMPLES_DIR = Path(__file__).resolve().parents[1] / "data" / "samples"


def _persist_sample(sample: "SampleCapture", base_dir: Path | None = None) -> Path:
    """把一帧采样落盘为 <label>-<ts>.json,返回落盘路径。"""
    target_dir = base_dir if base_dir is not None else _SAMPLES_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{sample.label}-{sample.ts}.json"
    path.write_text(sample.model_dump_json(indent=2), encoding="utf-8")
    return path
```

在 `ws_gateway` 的消息分发处理里，`if uplink.type == "heartbeat":` 这个分支**之前**，新增采样分支（采样与决策解耦，落盘后 `continue`，不进决策）：

```python
            if uplink.type == "sample.capture":
                try:
                    saved = _persist_sample(uplink)
                    logger.info("sample.capture label=%s nodes=%d saved=%s",
                                uplink.label, len(uplink.nodeTree), saved.name)
                except OSError as exc:
                    logger.error("sample.capture persist failed label=%s err=%s",
                                 uplink.label, exc)
                continue
```

- [ ] **Step 5: 运行测试，确认通过**

Run: `cd server && uv run pytest tests/test_gateway_integration.py -v`
Expected: PASS（新增 2 个用例通过，原有 2 个用例不回归）

- [ ] **Step 6: 全量回归**

Run: `cd server && uv run pytest -q`
Expected: 全绿（确认 protocol/gateway 改动未破坏决策链路）

- [ ] **Step 7: 提交**

```bash
git add server/app/gateway.py server/data/samples/.gitkeep server/tests/test_gateway_integration.py
git commit -m "feat(gateway): sample.capture 落盘到 data/samples/"
```

---

## 阶段 B：Android

> Android 端无自动化测试，靠编译 + 实机验证。每个 Task 后跑 `cd android && ./gradlew :app:assembleDebug` 确认编译通过再提交。

### Task 3: Messages.kt 新增上行采样类型

**Files:**
- Modify: `android/app/src/main/java/com/example/phoneagent/protocol/Messages.kt`

- [ ] **Step 1: 新增数据类**

在 `Messages.kt` 中 `UplinkTaskRequest` 数据类定义之后追加（字段与云端 `SampleCapture` 严格对齐）：

```kotlin
@Serializable
data class UplinkSampleCapture(
    val type: String = "sample.capture",
    val label: String,
    val nodeTree: List<NodeDto>,
    val pkg: String,
    val activity: String,
    val ts: Long,
    val device: String = "",
)
```

- [ ] **Step 2: 编译确认**

Run: `cd android && ./gradlew :app:assembleDebug`
Expected: BUILD SUCCESSFUL

- [ ] **Step 3: 提交**

```bash
git add android/app/src/main/java/com/example/phoneagent/protocol/Messages.kt
git commit -m "feat(android): 新增 UplinkSampleCapture 协议类"
```

### Task 4: WsClient 新增 sendSampleCapture

**Files:**
- Modify: `android/app/src/main/java/com/example/phoneagent/net/WsClient.kt`

- [ ] **Step 1: 新增发送方法**

在 `WsClient.kt` 顶部 import 区补一行（与其它 Uplink import 并列）：

```kotlin
import com.example.phoneagent.protocol.UplinkSampleCapture
```

在 `sendTaskRequest(goal: String)` 方法之后追加：

```kotlin
    /** 发送探针采样帧。采样与决策解耦,不影响任务链路。 */
    fun sendSampleCapture(msg: UplinkSampleCapture) {
        ws?.send(json.encodeToString(msg))
    }
```

- [ ] **Step 2: 编译确认**

Run: `cd android && ./gradlew :app:assembleDebug`
Expected: BUILD SUCCESSFUL

- [ ] **Step 3: 提交**

```bash
git add android/app/src/main/java/com/example/phoneagent/net/WsClient.kt
git commit -m "feat(android): WsClient 支持发送采样帧"
```

### Task 5: 采样请求信号中转（Repository）

**Files:**
- Create: `android/app/src/main/java/com/example/phoneagent/domain/SampleRequest.kt`
- Modify: `android/app/src/main/java/com/example/phoneagent/data/AgentStateRepository.kt`

- [ ] **Step 1: 建信号数据类**

新建 `android/app/src/main/java/com/example/phoneagent/domain/SampleRequest.kt`：

```kotlin
package com.example.phoneagent.domain

/** UI 发给无障碍服务的采样请求信号:延时 delaySeconds 秒后抓当前帧,打上 label。 */
data class SampleRequest(
    val label: String,
    val delaySeconds: Int,
)
```

- [ ] **Step 2: Repository 暴露采样请求流**

在 `AgentStateRepository.kt` 顶部 import 区补充：

```kotlin
import com.example.phoneagent.domain.SampleRequest
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.asSharedFlow
```

在类体内（`appendTrace` 方法之后）新增：

```kotlin
    // ---- 采样请求信号:UI -> Service。用 replay=0 的 SharedFlow,只通知在线的 Service。----
    private val _sampleRequests = MutableSharedFlow<SampleRequest>(extraBufferCapacity = 4)
    val sampleRequests: SharedFlow<SampleRequest> = _sampleRequests.asSharedFlow()

    /** UI 侧调用:发出一次采样请求。返回 false 表示当前无订阅者(Service 未连接)。 */
    fun requestSample(label: String, delaySeconds: Int): Boolean =
        _sampleRequests.tryEmit(SampleRequest(label, delaySeconds))
```

- [ ] **Step 3: 编译确认**

Run: `cd android && ./gradlew :app:assembleDebug`
Expected: BUILD SUCCESSFUL

- [ ] **Step 4: 提交**

```bash
git add android/app/src/main/java/com/example/phoneagent/domain/SampleRequest.kt android/app/src/main/java/com/example/phoneagent/data/AgentStateRepository.kt
git commit -m "feat(android): Repository 新增采样请求信号流"
```

### Task 6: Service 观察采样请求，延时抓帧上报

**Files:**
- Modify: `android/app/src/main/java/com/example/phoneagent/accessibility/PhoneAgentService.kt`

- [ ] **Step 1: 补充 import**

在 `PhoneAgentService.kt` 顶部 import 区追加：

```kotlin
import android.os.Build
import com.example.phoneagent.protocol.UplinkSampleCapture
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
```

- [ ] **Step 2: 新增服务级协程作用域字段**

在 `@Volatile private var pendingConfirm: DownTaskConfirm? = null` 这一行之后追加：

```kotlin
    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.Main)
```

- [ ] **Step 3: onServiceConnected 末尾订阅采样请求**

在 `onServiceConnected()` 方法体最后（`wsClient.start(...)` 调用结束的 `)` 之后、方法闭合 `}` 之前）追加：

```kotlin
        serviceScope.launch {
            repo.sampleRequests.collect { req ->
                Log.i(TAG, "sample request label=${req.label} delay=${req.delaySeconds}s")
                delay(req.delaySeconds * 1000L)
                captureSample(req.label)
            }
        }
```

- [ ] **Step 4: 新增采样抓帧方法**

在 `reportScreen()` 方法之后追加（复用现有 `rootInActiveWindow` + `NodeFlattener.flatten` 抓帧逻辑，与 `reportScreen` 一致，但走采样上行、不受 taskActive 门控）：

```kotlin
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
        val sample = UplinkSampleCapture(
            label = label,
            nodeTree = nodes,
            pkg = pkg,
            activity = pkg,
            ts = System.currentTimeMillis(),
            device = "${Build.MANUFACTURER} ${Build.MODEL}",
        )
        wsClient.sendSampleCapture(sample)
        Toast.makeText(applicationContext, "已采样「$label」: ${nodes.size} 个节点", Toast.LENGTH_SHORT).show()
        Log.i(TAG, "↑ sample.capture label=$label pkg=$pkg nodes=${nodes.size}")
        repo.appendTrace(
            TraceEvent(System.currentTimeMillis(), TraceDirection.UP, "sample.capture", "label=$label nodes=${nodes.size}")
        )
    }
```

- [ ] **Step 5: onDestroy 取消作用域**

在 `onDestroy()` 方法体内、`super.onDestroy()` 之前追加：

```kotlin
        serviceScope.coroutineContext[kotlinx.coroutines.Job]?.cancel()
```

- [ ] **Step 6: 编译确认**

Run: `cd android && ./gradlew :app:assembleDebug`
Expected: BUILD SUCCESSFUL

- [ ] **Step 7: 提交**

```bash
git add android/app/src/main/java/com/example/phoneagent/accessibility/PhoneAgentService.kt
git commit -m "feat(android): 无障碍服务延时抓帧并上报采样帧"
```

### Task 7: MainViewModel 采样入口 + 倒计时状态

**Files:**
- Modify: `android/app/src/main/java/com/example/phoneagent/ui/MainViewModel.kt`

- [ ] **Step 1: 新增采样状态字段与常量**

在 `MainViewModel` 的 `private companion object` 内追加常量：

```kotlin
        const val SAMPLE_DELAY_SECONDS = 10
```

在 `AgentUiState` 数据类新增字段（默认值保证不破坏现有构造）：

```kotlin
    val sampleCountdown: Int = 0,
    val sampleHint: String = "",
```

- [ ] **Step 2: 新增倒计时 StateFlow 并合并进 uiState**

在 `private val _debugUnlocked = MutableStateFlow(false)` 之后追加：

```kotlin
    private val _sampleCountdown = MutableStateFlow(0)
    private val _sampleHint = MutableStateFlow("")
```

把 `uiState` 的 `combine(...)` 改为合并这两个新流。将原：

```kotlin
        combine(repo.status, repo.debug, _debugUnlocked) { status, debug, unlocked ->
            AgentUiState(status = status, debug = debug, debugUnlocked = unlocked)
        }.stateIn(
```

替换为：

```kotlin
        combine(
            repo.status, repo.debug, _debugUnlocked, _sampleCountdown, _sampleHint,
        ) { status, debug, unlocked, countdown, hint ->
            AgentUiState(
                status = status, debug = debug, debugUnlocked = unlocked,
                sampleCountdown = countdown, sampleHint = hint,
            )
        }.stateIn(
```

- [ ] **Step 3: 新增 onCaptureSample**

在 `onRunTestTask()` 方法之后追加（发采样请求信号 + 本地倒计时显示，倒计时仅 UI 提示，真正抓帧在 Service）：

```kotlin
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
```

在 import 区补：

```kotlin
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
```

- [ ] **Step 4: 编译确认**

Run: `cd android && ./gradlew :app:assembleDebug`
Expected: BUILD SUCCESSFUL

- [ ] **Step 5: 提交**

```bash
git add android/app/src/main/java/com/example/phoneagent/ui/MainViewModel.kt
git commit -m "feat(android): MainViewModel 采样入口与倒计时状态"
```

### Task 8: AgentScreen 采样卡片 + MainActivity 接线

**Files:**
- Modify: `android/app/src/main/java/com/example/phoneagent/ui/AgentScreen.kt`
- Modify: `android/app/src/main/java/com/example/phoneagent/MainActivity.kt`

- [ ] **Step 1: AgentScreen 加回调参数**

给 `AgentScreen` 函数签名新增参数（放在 `onRunTestTask` 之后）：

```kotlin
    onCaptureSample: (String) -> Unit,
```

- [ ] **Step 2: 主界面常驻插入采样卡**

在 `AgentScreen` 的 `Column` 内、`TestTaskCard(...)` 之后、`TaskCard(...)` 之前插入：

```kotlin
            SampleCard(
                enabled = uiState.status.connection == ConnectionState.CONNECTED,
                countdown = uiState.sampleCountdown,
                hint = uiState.sampleHint,
                onCapture = onCaptureSample,
            )
```

- [ ] **Step 3: 新增 SampleCard Composable**

在 `TestTaskCard` Composable 之后追加：

```kotlin
@Composable
private fun SampleCard(
    enabled: Boolean,
    countdown: Int,
    hint: String,
    onCapture: (String) -> Unit,
) {
    var label by androidx.compose.runtime.saveable.rememberSaveable { androidx.compose.runtime.mutableStateOf("") }
    val counting = countdown > 0
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("场景采样", style = MaterialTheme.typography.titleMedium)
            androidx.compose.material3.OutlinedTextField(
                value = label,
                onValueChange = { label = it },
                label = { Text("场景标签,如 home_first / minus_one") },
                singleLine = true,
                enabled = enabled && !counting,
                modifier = Modifier.fillMaxWidth(),
            )
            Button(
                onClick = { onCapture(label) },
                enabled = enabled && !counting,
            ) {
                Text(if (counting) "倒计时 $countdown s…" else "开始采样(10s 后抓帧)")
            }
            if (hint.isNotBlank()) {
                Text(hint, style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}
```

- [ ] **Step 4: 更新两个 Preview 调用**

`AgentScreen.kt` 里两处 `@Preview` 内的 `AgentScreen(...)` 调用参数列表末尾（`onHideDebug = {}` 一行）改为：

```kotlin
            onTitleTap = {}, onOpenAccessibility = {}, onRunTestTask = {},
            onCaptureSample = {}, onHideDebug = {},
```

（两个 Preview 函数 `PreviewConnected` 与 `PreviewDisconnected` 都要改。）

- [ ] **Step 5: MainActivity 接线**

在 `MainActivity.kt` 的 `AgentScreen(...)` 调用里，`onRunTestTask = viewModel::onRunTestTask,` 之后追加：

```kotlin
                    onCaptureSample = viewModel::onCaptureSample,
```

- [ ] **Step 6: 编译确认**

Run: `cd android && ./gradlew :app:assembleDebug`
Expected: BUILD SUCCESSFUL

- [ ] **Step 7: 提交**

```bash
git add android/app/src/main/java/com/example/phoneagent/ui/AgentScreen.kt android/app/src/main/java/com/example/phoneagent/MainActivity.kt
git commit -m "feat(android): 主界面常驻场景采样卡片"
```

---

## 实机验证（Task 8 之后手动执行）

1. 启动云端：`cd server && uv run uvicorn app.gateway:create_app --factory --host 0.0.0.0 --port 8000`
2. 装 App 到 OPPO：`cd android && ./gradlew :app:installDebug`，开无障碍服务，确认「云端连接」显示已连接。
3. 逐场景采样：在采样卡输 `home_first`，点「开始采样」，10 秒内滑到桌面第一屏；倒计时结束看到 Toast「已采样」。依次采 `home_other` / `minus_one` / `notification`（下拉通知栏）/ `control_center`（下拉控制中心）/ `in_target_app`（进飞书）。
4. 核对落盘：`ls -la server/data/samples/` 应见到 `home_first-*.json` 等文件；`cat` 抽查确认含 `pkg` / `nodeTree`。
5. **重点观察**：下拉通知栏/控制中心时 `nodeTree` 是否抓到内容、`pkg` 是什么——这是阶段二定特征的关键依据。若抓到空/极少，如实记录（这本身是有价值的结论）。

---

## 自检记录

- **Spec 覆盖**：交互流程(Task 6/7/8)、10 秒延时(SAMPLE_DELAY_SECONDS=10)、sample.capture 协议(Task 1/3)、落盘 `<label>-<ts>.json`(Task 2)、主界面常驻(Task 8)、错误处理(抓帧失败 Toast / WS 未连接禁用按钮 / 落盘 OSError 记日志)、不动 decision.py/PKG_GUARD/session.py(阶段 A 分支独立 continue) —— 均有对应任务。
- **占位符**:无 TBD/TODO,每个代码步骤均给出完整代码。
- **类型一致性**:云端 `SampleCapture` 与端侧 `UplinkSampleCapture` 字段一一对应(label/nodeTree/pkg/activity/ts/device);`requestSample(label, delaySeconds)`、`sendSampleCapture(msg)`、`onCaptureSample(label)`、`captureSample(label)` 命名前后一致。