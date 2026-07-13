# 真人式打开应用（移除 open_app 命令直启）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 移除 open_app 命令直启（作弊/撞 Package Visibility），改为云端 LLM 用 home 回桌面归位第一屏 → 读 view tree 找图标 tap → 翻屏 → 翻到底 abort 的真人式流程。

**Architecture:** 端侧只做纯算子（swipe 到底检测 + 桌面遍历归位/线性扫描），业务判断全交给云端 LLM。翻页前后各拍帧 view tree，取每节点 text/desc/bounds 拼指纹字符串对比，两次一致 = 到底（atEnd=true）。atEnd 通过 action.result 上报，端云协议对称扩展。

**Tech Stack:** Kotlin（Android 无障碍 AccessibilityService、JUnit 单测）、Python（FastAPI WS gateway、pydantic protocol、pytest）。

---

## 背景与关键约束

- 分支 `feat/app-driven-goal`，**每 Task 独立 commit，不 push**。
- JDK17：`cd android && JAVA_HOME=/opt/homebrew/opt/openjdk@17 ./gradlew :app:testDebugUnitTest`
- Python 测试：`cd server && .venv/bin/pytest -q`
- **严禁 uiautomator dump**；观测只用 view tree/screencap。
- 端侧核心代码不含业务场景词（飞书等）；飞书 goal 仅存 MainViewModel。
- swipe 方向语义：`swipe right` = 手指往右滑 = 看**左边**屏（往回）；`swipe left` = 手指往左滑 = 看**右边**屏（往前）。
- framework 集成部分（真实手势派发/拍帧）只在真机联调验证，单测覆盖纯逻辑（指纹生成/相等判定/参数解析）。

## File Structure

**端侧（Kotlin）**
- `android/app/src/main/java/com/example/phoneagent/accessibility/ScreenFingerprint.kt`（**Create**）：纯函数，List<NodeDto> → 指纹字符串。可单测。
- `android/app/src/main/java/com/example/phoneagent/accessibility/Executor.kt`（**Modify**）：删 open_app/openApp/resolvePackageByLabel；execute 返回 `ExecResult`；加 home_first_page/next_page + 拍帧对比。
- `android/app/src/main/java/com/example/phoneagent/protocol/Messages.kt`（**Modify**）：UplinkActionResult 加 `atEnd`。
- `android/app/src/main/java/com/example/phoneagent/net/WsClient.kt`（**Modify**）：sendActionResult 加 `atEnd` 参数。
- `android/app/src/main/java/com/example/phoneagent/accessibility/PhoneAgentService.kt`（**Modify**）：onAction 取 ExecResult.ok/atEnd 上报 + 日志。
- `android/app/src/main/AndroidManifest.xml`（**Modify**）：回退 QUERY_ALL_PACKAGES + tools ns。
- `android/app/src/main/java/com/example/phoneagent/accessibility/AppTarget.kt`（**Delete**）。
- `android/app/src/test/.../AppTargetTest.kt`（**Delete**）。
- `android/app/src/test/.../ScreenFingerprintTest.kt`（**Create**）。
- `android/app/src/test/.../MessagesTest.kt`（**Modify**，若存在）：补 atEnd 序列化断言。

**云端（Python）**
- `server/app/protocol.py`（**Modify**）：ActionResult 加 `atEnd`；Action.op Literal 删 open_app 加 home_first_page/next_page。
- `server/app/gateway.py`（**Modify**）：history 记 atEnd。
- `server/app/decision.py`（**Modify**）：_SYSTEM_PROMPT 删 open_app + 写新策略。
- `server/tests/`（**Modify/Create**）：ActionResult 解析 atEnd、Action.op 不含 open_app、gateway history 写 atEnd。

---

## Task 1: 移除 open_app 全套（端侧 + 云端 + Manifest）

**Files:**
- Delete: `android/app/src/main/java/com/example/phoneagent/accessibility/AppTarget.kt`
- Delete: `android/app/src/test/java/com/example/phoneagent/accessibility/AppTargetTest.kt`
- Modify: `android/app/src/main/java/com/example/phoneagent/accessibility/Executor.kt`
- Modify: `android/app/src/main/AndroidManifest.xml`
- Modify: `server/app/protocol.py:97-108`
- Modify: `server/app/decision.py:16-31`

- [ ] **Step 1: 删除 AppTarget.kt 与 AppTargetTest.kt**

```bash
git rm android/app/src/main/java/com/example/phoneagent/accessibility/AppTarget.kt
git rm android/app/src/test/java/com/example/phoneagent/accessibility/AppTargetTest.kt
```

- [ ] **Step 2: Executor 删除 open_app 分支与 openApp/resolvePackageByLabel**

在 [`Executor.execute`](android/app/src/main/java/com/example/phoneagent/accessibility/Executor.kt:19) 的 when 中删除这一行：

```kotlin
            "open_app" -> openApp(AppTarget.fromParams(params))
```

删除整个 `openApp` 方法（`private fun openApp(target: AppTarget)...`）和整个 `resolvePackageByLabel` 方法。删除文件顶部因此不再使用的 import（`android.util.Log` 若他处仍用则保留；`android.content.Intent`/`PackageManager` 相关按需清理）。

- [ ] **Step 3: 回退 AndroidManifest 的 QUERY_ALL_PACKAGES + tools ns**

在 `android/app/src/main/AndroidManifest.xml` 中删除 `<uses-permission android:name="android.permission.QUERY_ALL_PACKAGES" .../>` 那一行，以及为它添加的 `xmlns:tools="..."` 命名空间声明（若无其他 tools 用途）。

- [ ] **Step 4: 云端 protocol.py 的 Action.op 删 open_app**

将 [`Action.op`](server/app/protocol.py:97) 的 Literal 列表中的 `"open_app",` 删除（本 Task 只删，home_first_page/next_page 在 Task 4 加）。

- [ ] **Step 5: decision.py 删 open_app 定义与飞书示例**

在 [`_SYSTEM_PROMPT`](server/app/decision.py:10) 中删除这两行：

```
- open_app: 打开应用。params: {"package": "应用包名"} 或 {"app": "应用名"}
```
```
输入目标"在飞书里给张三发消息"，当前在桌面看到"飞书"图标 -> {"op": "open_app", "params": {"app": "飞书"}}
```
（完整新策略在 Task 4 重写，本 Task 仅先移除 open_app 相关文本，保证不残留死命令。）

- [ ] **Step 6: 编译验证端侧**

Run: `cd android && JAVA_HOME=/opt/homebrew/opt/openjdk@17 ./gradlew :app:compileDebugKotlin`
Expected: BUILD SUCCESSFUL（无 AppTarget/openApp 未解析引用报错）

- [ ] **Step 7: 云端测试验证无 open_app 残留**

Run: `cd server && .venv/bin/pytest -q`
Expected: PASS（若有原本断言 open_app 的测试，改为不含 open_app，或删除对应旧断言）

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor: 移除 open_app 全套（端侧算子/AppTarget/Manifest/云端 op+prompt）"
```

---

## Task 2: atEnd 协议字段（端云对称 + 序列化测试）

**Files:**
- Modify: `android/app/src/main/java/com/example/phoneagent/protocol/Messages.kt:27-34`
- Modify: `server/app/protocol.py:27-32`
- Test: `android/app/src/test/java/com/example/phoneagent/protocol/MessagesTest.kt`
- Test: `server/tests/test_protocol.py`

- [ ] **Step 1: 端侧写失败测试（UplinkActionResult 序列化含 atEnd）**

在 `MessagesTest.kt`（若不存在则 Create，package `com.example.phoneagent.protocol`）加：

```kotlin
@Test
fun uplinkActionResult_serializes_atEnd() {
    val json = Json { encodeDefaults = true }
    val msg = UplinkActionResult(actionId = "a1", ok = true, atEnd = true)
    val text = json.encodeToString(UplinkActionResult.serializer(), msg)
    assertTrue(text.contains("\"atEnd\":true"))
}
```

- [ ] **Step 2: 运行确认失败**

Run: `cd android && JAVA_HOME=/opt/homebrew/opt/openjdk@17 ./gradlew :app:testDebugUnitTest --tests "*MessagesTest.uplinkActionResult_serializes_atEnd"`
Expected: FAIL（`atEnd` unresolved reference）

- [ ] **Step 3: Messages.kt 给 UplinkActionResult 加 atEnd**

修改 [`UplinkActionResult`](android/app/src/main/java/com/example/phoneagent/protocol/Messages.kt:27)：

```kotlin
@Serializable
data class UplinkActionResult(
    val type: String = "action.result",
    val actionId: String,
    val ok: Boolean,
    val atEnd: Boolean = false,
    val error: String? = null,
    val ts: Long = 0,
)
```

- [ ] **Step 4: 运行确认端侧通过**

Run: `cd android && JAVA_HOME=/opt/homebrew/opt/openjdk@17 ./gradlew :app:testDebugUnitTest --tests "*MessagesTest.uplinkActionResult_serializes_atEnd"`
Expected: PASS

- [ ] **Step 5: 云端写失败测试（ActionResult 解析 atEnd）**

在 `server/tests/test_protocol.py`（若无则 Create）加：

```python
from app.protocol import parse_uplink

def test_action_result_parses_at_end():
    raw = '{"type":"action.result","actionId":"a1","ok":true,"atEnd":true}'
    msg = parse_uplink(raw)
    assert msg.atEnd is True

def test_action_result_at_end_defaults_false():
    raw = '{"type":"action.result","actionId":"a1","ok":true}'
    msg = parse_uplink(raw)
    assert msg.atEnd is False
```

- [ ] **Step 6: 运行确认失败**

Run: `cd server && .venv/bin/pytest tests/test_protocol.py -q`
Expected: FAIL（ActionResult 无 atEnd 属性）

- [ ] **Step 7: protocol.py 给 ActionResult 加 atEnd**

修改 [`ActionResult`](server/app/protocol.py:27)：

```python
class ActionResult(BaseModel):
    type: Literal["action.result"] = "action.result"
    actionId: str
    ok: bool
    atEnd: bool = False
    error: Optional[str] = None
    ts: int = 0
```

- [ ] **Step 8: 运行确认云端通过**

Run: `cd server && .venv/bin/pytest tests/test_protocol.py -q`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "feat: action.result 新增 atEnd 字段（端云对称，默认 false 向后兼容）"
```

---

## Task 3: ScreenFingerprint 指纹（纯函数 + 单测）

**Files:**
- Create: `android/app/src/main/java/com/example/phoneagent/accessibility/ScreenFingerprint.kt`
- Test: `android/app/src/test/java/com/example/phoneagent/accessibility/ScreenFingerprintTest.kt`

- [ ] **Step 1: 写失败测试**

Create `ScreenFingerprintTest.kt`（package `com.example.phoneagent.accessibility`，import `com.example.phoneagent.protocol.NodeDto`）：

```kotlin
class ScreenFingerprintTest {
    private fun node(id: String, text: String?, desc: String?, b: List<Int>?) =
        NodeDto(id = id, text = text, desc = desc, bounds = b)

    @Test
    fun same_nodes_produce_equal_fingerprint() {
        val a = listOf(node("0", "微信", null, listOf(0, 0, 10, 10)))
        val b = listOf(node("0", "微信", null, listOf(0, 0, 10, 10)))
        assertEquals(ScreenFingerprint.of(a), ScreenFingerprint.of(b))
    }

    @Test
    fun different_text_produces_different_fingerprint() {
        val a = listOf(node("0", "微信", null, listOf(0, 0, 10, 10)))
        val b = listOf(node("0", "支付宝", null, listOf(0, 0, 10, 10)))
        assertNotEquals(ScreenFingerprint.of(a), ScreenFingerprint.of(b))
    }

    @Test
    fun different_bounds_produces_different_fingerprint() {
        val a = listOf(node("0", "微信", null, listOf(0, 0, 10, 10)))
        val b = listOf(node("0", "微信", null, listOf(0, 0, 20, 20)))
        assertNotEquals(ScreenFingerprint.of(a), ScreenFingerprint.of(b))
    }

    @Test
    fun empty_list_is_stable() {
        assertEquals(ScreenFingerprint.of(emptyList()), ScreenFingerprint.of(emptyList()))
    }
}
```

- [ ] **Step 2: 运行确认失败**

Run: `cd android && JAVA_HOME=/opt/homebrew/opt/openjdk@17 ./gradlew :app:testDebugUnitTest --tests "*ScreenFingerprintTest"`
Expected: FAIL（ScreenFingerprint unresolved）

- [ ] **Step 3: 实现 ScreenFingerprint**

Create `ScreenFingerprint.kt`：

```kotlin
package com.example.phoneagent.accessibility

import com.example.phoneagent.protocol.NodeDto

/**
 * 屏幕指纹：取每个节点的 text/desc/bounds 拼成稳定字符串。
 * 用于翻页前后对比是否到底（两次指纹一致 = 翻不动）。纯函数，可单测。
 */
object ScreenFingerprint {
    fun of(nodes: List<NodeDto>): String =
        nodes.joinToString("|") { n ->
            "${n.text.orEmpty()}~${n.desc.orEmpty()}~${n.bounds?.joinToString(",").orEmpty()}"
        }
}
```

- [ ] **Step 4: 运行确认通过**

Run: `cd android && JAVA_HOME=/opt/homebrew/opt/openjdk@17 ./gradlew :app:testDebugUnitTest --tests "*ScreenFingerprintTest"`
Expected: PASS（4 tests）

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: 新增 ScreenFingerprint 屏幕指纹纯函数 + 单测"
```

---

## Task 4: Executor 到底检测 + 桌面遍历算子 + 上报链路 + 云端 prompt

**Files:**
- Modify: `android/app/src/main/java/com/example/phoneagent/accessibility/Executor.kt`
- Modify: `android/app/src/main/java/com/example/phoneagent/net/WsClient.kt:118-120`
- Modify: `android/app/src/main/java/com/example/phoneagent/accessibility/PhoneAgentService.kt:55-59`
- Modify: `server/app/protocol.py:97`
- Modify: `server/app/gateway.py:96`
- Modify: `server/app/decision.py:10-31`

- [ ] **Step 1: Executor 定义 ExecResult 并把 execute 返回类型改为 ExecResult**

在 `Executor.kt` 类外（文件顶部 import 之后）加：

```kotlin
data class ExecResult(val ok: Boolean, val atEnd: Boolean = false)
```

将 [`execute`](android/app/src/main/java/com/example/phoneagent/accessibility/Executor.kt:19) 改为返回 ExecResult，并新增 home_first_page/next_page：

```kotlin
    fun execute(op: String, params: Map<String, String>): ExecResult {
        return when (op) {
            "tap" -> ExecResult(tap(params["match_text"].orEmpty()))
            "input" -> ExecResult(input(params["text"].orEmpty()))
            "swipe" -> ExecResult(swipe(params))
            "back" -> ExecResult(service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK))
            "home" -> ExecResult(service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_HOME))
            "home_first_page" -> homeFirstPage()
            "next_page" -> nextPage()
            "read_screen", "wait" -> ExecResult(true)
            else -> ExecResult(false)
        }
    }
```

- [ ] **Step 2: Executor 加拍帧 + 单向翻页 + 到底判定辅助方法**

在 Executor 中新增（`swipeDir` 复用 GestureGeometry 生成方向手势；拍帧用 NodeFlattener.flatten(rootInActiveWindow) 取指纹）：

```kotlin
    /** 拍一帧当前屏幕指纹（framework 集成，真机验证）。 */
    private fun snapshotFingerprint(): String =
        ScreenFingerprint.of(NodeFlattener.flatten(service.rootInActiveWindow))

    /** 派发一次方向翻页手势，等待稳定后返回是否派发成功。方向：right=看左屏，left=看右屏。 */
    private fun swipeHorizontal(toRight: Boolean): Boolean {
        val m = context.resources.displayMetrics
        val y = m.heightPixels / 2f
        val fromX = if (toRight) m.widthPixels * 0.2f else m.widthPixels * 0.8f
        val toX = if (toRight) m.widthPixels * 0.8f else m.widthPixels * 0.2f
        val path = Path().apply { moveTo(fromX, y); lineTo(toX, y) }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, 300))
            .build()
        val dispatched = service.dispatchGesture(gesture, null, null)
        Thread.sleep(SETTLE_MS)
        return dispatched
    }

    /** 回桌面后连续向右翻页（看左边直到前后帧一致 = 已在最左第一屏。 */
    private fun homeFirstPage(): ExecResult {
        service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_HOME)
        Thread.sleep(SETTLE_MS)
        var before = snapshotFingerprint()
        repeat(MAX_PAGES) {
            if (!swipeHorizontal(toRight = true)) return ExecResult(ok = false)
            val after = snapshotFingerprint()
            if (after == before) return ExecResult(ok = true)
            before = after
        }
        return ExecResult(ok = true)
    }

    /** 向左翻一屏（看右边）；前后帧一致 = 到底。 */
    private fun nextPage(): ExecResult {
        val before = snapshotFingerprint()
        val dispatched = swipeHorizontal(toRight = false)
        val after = snapshotFingerprint()
        return ExecResult(ok = dispatched, atEnd = after == before)
    }
```

在 companion object 加常量：

```kotlin
        const val SETTLE_MS = 500L
        const val MAX_PAGES = 12
```

- [ ] **Step 3: 编译端侧确认 Executor 通过**

Run: `cd android && JAVA_HOME=/opt/homebrew/opt/openjdk@17 ./gradlew :app:compileDebugKotlin`
Expected: BUILD SUCCESSFUL

- [ ] **Step 4: WsClient.sendActionResult 加 atEnd 参数**

修改 [`sendActionResult`](android/app/src/main/java/com/example/phoneagent/net/WsClient.kt:118)：

```kotlin
    fun sendActionResult(actionId: String, ok: Boolean, atEnd: Boolean = false, error: String? = null) {
        ws?.send(json.encodeToString(UplinkActionResult(actionId = actionId, ok = ok, atEnd = atEnd, error = error)))
    }
```

- [ ] **Step 5: PhoneAgentService.onAction 取 ExecResult.ok/atEnd 上报 + 日志**

修改 [`onAction`](android/app/src/main/java/com/example/phoneagent/accessibility/PhoneAgentService.kt:55) 内 5 行：

```kotlin
                val result = executor.execute(action.op, action.params)
                Log.i(TAG, "↑ action.result ${action.op} ok=${result.ok} atEnd=${result.atEnd}")
                repo.appendTrace(TraceEvent(System.currentTimeMillis(), TraceDirection.UP, "action.result", "${action.op} ok=${result.ok} atEnd=${result.atEnd}"))
                wsClient.sendActionResult(action.actionId, result.ok, result.atEnd)
                repo.appendActionLog(ActionLog(System.currentTimeMillis(), action.op, result.ok))
```

- [ ] **Step 6: 编译端侧全量**

Run: `cd android && JAVA_HOME=/opt/homebrew/opt/openjdk@17 ./gradlew :app:compileDebugKotlin :app:testDebugUnitTest`
Expected: BUILD SUCCESSFUL，测试全绿

- [ ] **Step 7: 云端 protocol.py 的 Action.op 加 home_first_page/next_page**

在 [`Action.op`](server/app/protocol.py:97) Literal 中加入（open_app 已在 Task 1 删除）：

```python
        "home_first_page",
        "next_page",
```

- [ ] **Step 8: 云端写失败测试（gateway history 记 atEnd + op 不含 open_app）**

在 `server/tests/test_protocol.py` 加：

```python
from app.protocol import Action

def test_action_op_excludes_open_app():
    import typing
    ops = typing.get_args(Action.model_fields["op"].annotation)
    assert "open_app" not in ops
    assert "home_first_page" in ops
    assert "next_page" in ops
```

- [ ] **Step 9: gateway.py history 记 atEnd**

修改 [`gateway.py`](server/app/gateway.py:96) 的 action.result 分支：

```python
            if uplink.type == "action.result":
                history.append({"actionId": uplink.actionId, "ok": uplink.ok, "atEnd": uplink.atEnd})
                if uplink.ok:
                    cursor += 1
                continue
```

- [ ] **Step 10: decision.py 重写 _SYSTEM_PROMPT 策略段**

在 [`_SYSTEM_PROMPT`](server/app/decision.py:10) 的合法 op 列表中，把原 open_app 行替换为：

```
- home_first_page: 回到桌面并归位到最左第一屏（端侧会自动翻到头）。params: {}
- next_page: 桌面向后翻一屏找应用图标。若返回的 atEnd 为 true 表示已到最后一屏。params: {}
```

并在 prompt 追加策略说明：

```
打开应用的正确流程（禁止假设包名、禁止命令直启，只点屏幕上真实可见的图标）：
1. 先 home_first_page 归位到桌面第一屏；
2. read_screen 观察当前屏节点，若看到目标应用图标文本 -> tap 该图标；
3. 若当前屏没有目标图标 -> next_page 翻到下一屏继续找；
4. 若某次 next_page 的历史 atEnd 为 true 且仍未找到目标图标 -> abort，reason 写“未找到应用<名>”。
history 中每条含 atEnd 字段，true 表示端侧翻不动了（到底）。
```

- [ ] **Step 11: 运行云端测试**

Run: `cd server && .venv/bin/pytest -q`
Expected: PASS（含新增 op 断言；若旧集成测试引用 open_app 需同步改）

- [ ] **Step 12: Commit**

```bash
git add -A
git commit -m "feat: swipe 到底检测(ExecResult+指纹) + home_first_page/next_page 算子 + atEnd 上报链路 + 云端翻屏找图标 prompt"
```

---

## Task 5: 真机联调校准（联调后再做）

**Files:**
- Modify: `android/app/src/main/java/com/example/phoneagent/accessibility/Executor.kt`（SETTLE_MS/MAX_PAGES/滑动起止比例，按真机表现微调）

- [ ] **Step 1: 安装并连真机**

Run: `cd android && JAVA_HOME=/opt/homebrew/opt/openjdk@17 ./gradlew :app:installDebug`
Expected: BUILD SUCCESSFUL，安装到 3B15AG00WCY00000。重装后到 app 前台确认无障碍/WS 已连。

- [ ] **Step 2: 后台流式抓日志（规避终端 clear 污染）**

Run: `adb logcat -s "PhoneAgent:*" > /tmp/pa.log &`
用 read_file 读 `/tmp/pa.log` 观测 `↑ action.result <op> ok=.. atEnd=..`。

- [ ] **Step 3: 触发 home_first_page 联调**

从 app 按钮下发 TEST_GOAL（飞群任务），观察日志：home_first_page 是否稳定归位第一屏（前后帧一致才停），next_page 到最后一屏是否 atEnd=true，未找到是否走 abort → TaskAbort → UI 提示。

- [ ] **Step 4: 按表现微调常量并 commit**

若翻页太快导致误判 atEnd，调大 SETTLE_MS；若归位次数不够调大 MAX_PAGES；若滑动幅度不够调整起止比例。改后：

```bash
git add android/app/src/main/java/com/example/phoneagent/accessibility/Executor.kt
git commit -m "fix: 真机联调校准翻页等待/幅度/最大屏数"
```

---

## Self-Review

**Spec coverage：**
- ① Executor swipe 到底检测（ExecResult + 指纹）→ Task 3（指纹纯函数+单测）+ Task 4 Step 1-3（ExecResult/拍帧/nextPage）✓
- ② 桌面遍历算子 home_first_page/next_page（B2）→ Task 4 Step 2 ✓
- ③ atEnd 协议对称（端 Uplink + 云 ActionResult 默认 false）→ Task 2 ✓
- ④ 上报消费链路（WsClient + PhoneAgentService + gateway history）→ Task 4 Step 4/5/9 ✓
- ⑤ 云端决策（Action.op 删 open_app 加两算子 + prompt 改造）→ Task 1 Step 4/5 + Task 4 Step 7/10 ✓
- 死代码清理（Executor open_app 分支/openApp/resolvePackageByLabel、AppTarget(+Test)、Manifest 回退）→ Task 1 ✓
- 测试（fingerprint 单测、MessagesTest atEnd、云端 ActionResult 解析 atEnd + op 不含 open_app + gateway history）→ Task 2/3/4 ✓

**Placeholder scan：** 无 TBD/TODO；所有代码步骤含完整代码块；Task 5 明确标注“联调后再做”，其常量微调依赖真机是设计明示的非目标校准，非占位。

**Type consistency：** `ExecResult(ok, atEnd=false)` 在 Task 4 定义并全程一致使用；`ScreenFingerprint.of(nodes)` Task 3 定义、Task 4 引用一致；`sendActionResult(actionId, ok, atEnd, error)` 参数顺序一致；`atEnd` 字段名端（Kotlin）云（Python）一致。