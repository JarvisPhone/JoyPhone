# 端侧节点合并 + 纯文本通信协议 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 端侧合并语义等价的碎片节点消除点错歧义，上下行改纯文本 SoM/指令协议并支持多指令批处理，同时落盘通信原文便于排障。

**Architecture:** 端云分工。端侧 `NodeFlattener` 负责「Filter/Merge/Pass-through 三条规则合并碎片节点」并新增 `viewIdResourceName` 采集与 `viewIdToLabel` 兜底摘 label；云侧 `decision.py` 负责「SoM 文本编码 + `n→node` 映射 + `parse_actions` 文本指令解析」，`gateway.py` 负责「多指令批处理逐条下发」。WS 信封仍是 JSON（`perception.screen` 字段改纯文本块，下行仍是 `DownAction` op+params），彻底删除 `match_text` 子串匹配分支，`tap n` 经映射还原为精确坐标。

**Tech Stack:** Kotlin (Android AccessibilityService, kotlinx.serialization, JUnit4)；Python 3.12 (FastAPI, pydantic, pytest)。

**关键前置约定（贯穿所有任务）：**
- 端侧单测运行：`cd android && JAVA_HOME=/opt/homebrew/opt/openjdk@17 ./gradlew :app:testDebugUnitTest --tests "com.example.phoneagent.accessibility.NodeFlattenerTest"`
- 云侧单测运行：`cd server && uv run pytest tests/test_decision.py -v`（或指定 `::test_name`）
- 改了 `decision.py`/`gateway.py`（云侧）必须重启 uvicorn；改了 `NodeFlattener.kt`/`Messages.kt`（端侧）必须重装 apk。
- **真机验证通过前不 commit 到主线**（第 8 组任务前的 commit 都在功能分支）。

---

## File Structure

**端侧（Android）：**
- Modify `android/app/src/main/java/com/example/phoneagent/accessibility/NodeFlattener.kt` — 新增 `viewIdToLabel` 纯函数、`pickLabel` 纯函数；改写 `walk` 为 Filter/Merge/Pass-through。
- Modify `android/app/src/test/java/com/example/phoneagent/accessibility/NodeFlattenerTest.kt` — 为新纯函数补单测。
- Modify `android/app/src/main/java/com/example/phoneagent/protocol/Messages.kt` — `NodeDto` 加 `viewIdResourceName`。

**云侧（Python）：**
- Modify `server/app/protocol.py` — `Node` 加 `viewIdResourceName`。
- Modify `server/app/decision.py` — SoM 编码沿用 `_encode_nodes`（编号语义定稿为 capped 下标）；新增 `parse_actions`；删除 `_resolve_tap_node` 的 match_text 分支；`decide` 拆出可批处理的 action 列表；改写 `_SYSTEM_PROMPT`；移除 `frame_dump.json`/`encode_nodes_debug`/`[LLM-RAW-*]` 插桩。
- Modify `server/app/gateway.py` — 批处理逐条下发；接入 comm/llm 日志。
- Modify `server/app/llm.py` — `RealLLM.complete` 停止 JSON 抽取（改 `_clean_text` 只剥 `<think>`）；接入 llm.log；无 key FakeLLM 默认响应改文本指令。
- Create `server/app/comm_log.py` — comm.log / llm.log 两个独立 RotatingFileHandler logger。
- Modify `server/tests/test_decision.py` — 更新受影响用例 + 新增 `parse_actions`/编码/映射/批处理用例。
- Modify `server/tests/test_protocol.py` — `viewIdResourceName` 反序列化兼容用例。
- Modify `server/tests/test_gateway_loop.py` — FakeLLM 改文本指令 + 批处理停止规则集成用例。
- Create `server/tests/test_comm_log.py` — 日志写入单测。
- Create `server/tests/test_llm.py` — `_clean_text` 剥 `<think>` 单测。

**责任边界：** 端侧只管「减少/合并节点 + 采集 viewId」；云侧只管「编码格式 + 文本指令解析 + 批处理下发 + 日志」。协议 `NodeDto`/`Node` 仅加一个可选字段，向后兼容。

---

### Task 1: 协议加 `viewIdResourceName` 字段（端 + 云）

端侧摘 label 的兜底源需要上报 `viewIdResourceName`；云侧也要能反序列化它（即使暂不用，也要向后兼容不报错）。

**Files:**
- Modify: `android/app/src/main/java/com/example/phoneagent/protocol/Messages.kt:7-14`（`NodeDto`）
- Modify: `server/app/protocol.py:7-13`（`Node`）
- Test: `server/tests/test_protocol.py`

- [ ] **Step 1: 云侧写失败测试**（先云侧因为可纯 JVM/pytest 快速验证反序列化兼容）

在 `server/tests/test_protocol.py` 末尾追加：

```python
def test_node_accepts_view_id_resource_name():
    raw = ('{"type":"perception","nodeTree":[{"id":"n1","clickable":true,'
           '"viewIdResourceName":"com.ss.android.lark:id/search_button"}],'
           '"pkg":"com.ss.android.lark","activity":"Main","ts":1}')
    msg = parse_uplink(raw)
    assert msg.nodeTree[0].viewIdResourceName == "com.ss.android.lark:id/search_button"


def test_node_view_id_resource_name_defaults_none():
    node_json = '{"type":"perception","nodeTree":[{"id":"n1"}]}'
    msg = parse_uplink(node_json)
    assert msg.nodeTree[0].viewIdResourceName is None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd server && uv run pytest tests/test_protocol.py::test_node_accepts_view_id_resource_name -v`
Expected: FAIL —— pydantic 忽略未知字段，`viewIdResourceName` 属性不存在触发 `AttributeError`。

- [ ] **Step 3: 云侧加字段**

在 `server/app/protocol.py` 的 `Node` 类里，`editable: bool = False` 下一行加：

```python
class Node(BaseModel):
    id: str
    text: Optional[str] = None
    desc: Optional[str] = None
    className: Optional[str] = None
    bounds: Optional[tuple[int, int, int, int]] = None  # [left, top, right, bottom]
    clickable: bool = False
    editable: bool = False
    viewIdResourceName: Optional[str] = None
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd server && uv run pytest tests/test_protocol.py -v`
Expected: PASS（含新增 2 条 + 全部旧用例）。

- [ ] **Step 5: 端侧加字段**

在 `android/app/src/main/java/com/example/phoneagent/protocol/Messages.kt` 的 `NodeDto` 里，`val editable: Boolean = false,` 下一行加：

```kotlin
@Serializable
data class NodeDto(
    val id: String,
    val text: String? = null,
    val desc: String? = null,
    val className: String? = null,
    val bounds: List<Int>? = null,
    val clickable: Boolean = false,
    val editable: Boolean = false,
    val viewIdResourceName: String? = null,
)
```

- [ ] **Step 6: 端侧编译验证**

Run: `cd android && JAVA_HOME=/opt/homebrew/opt/openjdk@17 ./gradlew :app:compileDebugKotlin`
Expected: BUILD SUCCESSFUL。

- [ ] **Step 7: 提交**

```bash
git add android/app/src/main/java/com/example/phoneagent/protocol/Messages.kt server/app/protocol.py server/tests/test_protocol.py
git commit -m "feat(protocol): add viewIdResourceName to NodeDto/Node"
```

---

### Task 2: 端侧 `viewIdToLabel` + `pickLabel` 纯函数（label 兜底）

spec §1 Filter 规则要求 label 优先级：`text → desc → 子孙 text/desc → viewIdToLabel`。当前 [`walk()`](android/app/src/main/java/com/example/phoneagent/accessibility/NodeFlattener.kt:52) 内联了前三级，缺 `viewIdResourceName` 兜底。抽出两个纯函数便于单测，再让 walk 调用。

**Files:**
- Modify: `android/app/src/main/java/com/example/phoneagent/accessibility/NodeFlattener.kt`
- Test: `android/app/src/test/java/com/example/phoneagent/accessibility/NodeFlattenerTest.kt`

- [ ] **Step 1: 写失败测试**

在 `NodeFlattenerTest.kt` 末尾 `}` 前追加：

```kotlin
    @Test
    fun view_id_to_label_takes_last_segment_after_slash() {
        assertEquals("search button", NodeFlattener.viewIdToLabel("com.ss.android.lark:id/search_button"))
    }

    @Test
    fun view_id_to_label_handles_no_slash() {
        assertEquals("submit", NodeFlattener.viewIdToLabel("submit"))
    }

    @Test
    fun view_id_to_label_null_or_blank_returns_null() {
        assertEquals(null, NodeFlattener.viewIdToLabel(null))
        assertEquals(null, NodeFlattener.viewIdToLabel(""))
    }

    @Test
    fun pick_label_prefers_text_over_desc() {
        assertEquals("文本", NodeFlattener.pickLabel(text = "文本", desc = "描述", descendant = "子孙", viewId = "a:id/x"))
    }

    @Test
    fun pick_label_falls_back_to_desc_then_descendant_then_view_id() {
        assertEquals("描述", NodeFlattener.pickLabel(text = null, desc = "描述", descendant = "子孙", viewId = "a:id/x"))
        assertEquals("子孙", NodeFlattener.pickLabel(text = null, desc = null, descendant = "子孙", viewId = "a:id/x"))
        assertEquals("save file", NodeFlattener.pickLabel(text = null, desc = null, descendant = null, viewId = "a:id/save_file"))
    }

    @Test
    fun pick_label_all_null_returns_null() {
        assertEquals(null, NodeFlattener.pickLabel(text = null, desc = null, descendant = null, viewId = null))
    }
```

- [ ] **Step 2: 运行确认失败**

Run: `cd android && JAVA_HOME=/opt/homebrew/opt/openjdk@17 ./gradlew :app:testDebugUnitTest --tests "*.NodeFlattenerTest"`
Expected: FAIL —— `viewIdToLabel`/`pickLabel` 未定义，编译不过。

- [ ] **Step 3: 实现两个纯函数**

在 `NodeFlattener.kt` 的 [`shouldKeep()`](android/app/src/main/java/com/example/phoneagent/accessibility/NodeFlattener.kt:24) 之后、`flatten()` 之前插入：

```kotlin
    /**
     * viewIdResourceName 兜底转 label：取最后一段（"/" 后），下划线转空格。
     * 例 "com.ss.android.lark:id/search_button" -> "search button"。null/空返回 null。纯逻辑。
     */
    fun viewIdToLabel(viewId: String?): String? {
        if (viewId.isNullOrBlank()) return null
        val seg = viewId.substringAfterLast('/')
        return seg.replace('_', ' ').trim().ifBlank { null }
    }

    /** label 优先级：text → desc → 子孙 text/desc → viewIdToLabel。全空返回 null。纯逻辑。 */
    fun pickLabel(text: String?, desc: String?, descendant: String?, viewId: String?): String? = when {
        !text.isNullOrBlank() -> text
        !desc.isNullOrBlank() -> desc
        !descendant.isNullOrBlank() -> descendant
        else -> viewIdToLabel(viewId)
    }
```

- [ ] **Step 4: 运行确认通过**

Run: `cd android && JAVA_HOME=/opt/homebrew/opt/openjdk@17 ./gradlew :app:testDebugUnitTest --tests "*.NodeFlattenerTest"`
Expected: PASS。

- [ ] **Step 5: 改写 walk 调用 pickLabel + 采集 viewIdResourceName**

将 [`walk()`](android/app/src/main/java/com/example/phoneagent/accessibility/NodeFlattener.kt:52) 中 `if (keep) { ... }` 块替换为：

```kotlin
        if (keep) {
            val descendant = if (interactive && text.isNullOrBlank() && desc.isNullOrBlank())
                firstDescendantLabel(node) else null
            val viewId = node.viewIdResourceName
            val label = pickLabel(text = text, desc = desc, descendant = descendant, viewId = viewId)
            out.add(
                NodeDto(
                    id = makeId(path),
                    text = truncate(label),
                    desc = truncate(desc),
                    className = node.className?.toString(),
                    bounds = rectToBounds(rect),
                    clickable = node.isClickable,
                    editable = node.isEditable,
                    viewIdResourceName = viewId,
                )
            )
        }
```

- [ ] **Step 6: 编译验证**

Run: `cd android && JAVA_HOME=/opt/homebrew/opt/openjdk@17 ./gradlew :app:compileDebugKotlin`
Expected: BUILD SUCCESSFUL。

- [ ] **Step 7: 提交**

```bash
git add android/app/src/main/java/com/example/phoneagent/accessibility/NodeFlattener.kt android/app/src/test/java/com/example/phoneagent/accessibility/NodeFlattenerTest.kt
git commit -m "feat(flatten): viewIdToLabel/pickLabel fallback + collect viewIdResourceName"
```

---

### Task 3: 云侧 SoM 编码收敛 + 删 match_text 引用键

spec §2/§4：上行 `screen` 已是 `[n] type "label"` 文本块（[`_encode_nodes()`](server/app/decision.py:57) 已实现，无需改）。核心变更是 **`[n]` 唯一引用键 = capped nodes 下标**，删除 [`_resolve_tap_node()`](server/app/decision.py:73) 的 `match_text` 子串匹配分支。这样 LLM 只能靠行号定位，消除同名子串误命中。

> ⚠️ 兼容性：`skills.py`/`skill_cache.py` 仍用 `match_text` 做技能重定位（[`_cache_step()`](server/app/decision.py:128)）。**本任务只删 LLM tap 路径的 match_text，不动技能缓存路径**，二者互不影响。

**Files:**
- Modify: `server/app/decision.py`（`_resolve_tap_node`）
- Test: `server/tests/test_decision.py`

- [ ] **Step 1: 改测试为「删 match_text」**

在 `server/tests/test_decision.py` 中：

1. 删除这两个基于 match_text 的用例（match_text 不再是 LLM tap 引用键）：
   - `test_tap_by_match_text_resolves_to_bounds_center`
   - `test_tap_match_text_matches_desc`
   - `test_tap_keeps_match_text_as_fallback`
   - `test_tap_node_without_bounds_keeps_original_params`（其用 match_text，改造见下）

2. 追加新用例（只认 id 下标）：

```python
def test_tap_only_resolves_by_id_not_match_text():
    # 删 match_text 后：即使 label 完全匹配，无 id 也解析不到坐标
    llm = FakeLLM(['{"op":"tap","params":{"match_text":"飞书"}}'])
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    nodes = [Node(id="a", text="飞书", clickable=True, bounds=(200, 300, 400, 500))]
    action = engine.decide(goal="打开飞书", perception=_perc(nodes), skill_name=None, cursor=0, history=[])
    assert "x" not in action.params  # match_text 不再被解析


def test_tap_by_id_out_of_range_keeps_original():
    llm = FakeLLM(['{"op":"tap","params":{"id":"99"}}'])
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    nodes = [Node(id="a", text="飞书", clickable=True, bounds=(0, 0, 10, 10))]
    action = engine.decide(goal="打开飞书", perception=_perc(nodes), skill_name=None, cursor=0, history=[])
    assert "x" not in action.params


def test_tap_by_id_node_without_bounds_keeps_original():
    llm = FakeLLM(['{"op":"tap","params":{"id":"0"}}'])
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    nodes = [Node(id="a", text="飞书", clickable=True, bounds=None)]
    action = engine.decide(goal="打开飞书", perception=_perc(nodes), skill_name=None, cursor=0, history=[])
    assert "x" not in action.params
```

- [ ] **Step 2: 运行确认失败**

Run: `cd server && uv run pytest tests/test_decision.py::test_tap_only_resolves_by_id_not_match_text -v`
Expected: FAIL —— 当前 `_resolve_tap_node` 仍走 match_text 分支解析出坐标，`"x" in params`。

- [ ] **Step 3: 删 `_resolve_tap_node` 的 match_text 分支**

把 [`_resolve_tap_node()`](server/app/decision.py:73) 整体替换为：

```python
def _resolve_tap_node(params: dict, nodes: list[Node]) -> Node | None:
    """把 LLM 的 tap 参数还原为被选中的 Node。

    引用键唯一：id = _encode_nodes 的列表下标(对 capped nodes 而言)。
    不再支持 match_text 子串匹配(易误命中同名文字)。越界/缺失返回 None。
    """
    raw_id = params.get("id")
    if raw_id is None or str(raw_id).strip() == "":
        return None
    try:
        idx = int(str(raw_id).strip())
    except (ValueError, TypeError):
        return None
    if 0 <= idx < len(nodes):
        return nodes[idx]
    return None
```

- [ ] **Step 4: 运行确认通过**

Run: `cd server && uv run pytest tests/test_decision.py -v`
Expected: PASS（新增 3 条 + `test_tap_by_id_resolves_to_bounds_center` 等 id 用例仍绿；已删的 match_text 用例不再存在）。

- [ ] **Step 5: 提交**

```bash
git add server/app/decision.py server/tests/test_decision.py
git commit -m "refactor(decision): tap resolves by node index only, drop match_text"
```

---

### Task 4: 云侧 `parse_actions` 文本指令解析纯函数

spec §3：下行改文本指令语法，LLM 每行输出一条指令。新增纯函数 `parse_actions(text) -> list[dict]`，把多行文本解析为 `[{"op":..,"params":{..}}]`。**本任务只做解析纯函数**（可 pytest 快速验证），批处理调度在 Task 5 接入 `decide`。

指令语法（首个空格切动词，文本参数取行尾）：
- `tap n` → `{"op":"tap","params":{"id":"n"}}`
- `input n 文本内容` → `{"op":"input","params":{"id":"n","text":"文本内容"}}`
- `swipe up|down|left|right` → `{"op":"swipe","params":{"direction":".."}}`
- `back` / `home` / `home_first` / `next_page` / `read` / `done` → 无参 op（`home_first`→`home_first_page`，`read`→`read_screen`）
- `wait ms` → `{"op":"wait","params":{"ms":".."}}`
- `abort 原因` → `{"op":"abort","params":{"reason":"原因"}}`
- 空行/无法识别的行 → 跳过

**Files:**
- Modify: `server/app/decision.py`（新增 `parse_actions`）
- Test: `server/tests/test_decision.py`

- [ ] **Step 1: 写失败测试**

在 `server/tests/test_decision.py` 顶部 import 区补 `from app.decision import parse_actions`，末尾追加：

```python
def test_parse_actions_single_tap():
    assert parse_actions("tap 3") == [{"op": "tap", "params": {"id": "3"}}]


def test_parse_actions_input_takes_rest_of_line_as_text():
    assert parse_actions("input 2 你好 世界") == [
        {"op": "input", "params": {"id": "2", "text": "你好 世界"}}
    ]


def test_parse_actions_swipe_direction():
    assert parse_actions("swipe up") == [{"op": "swipe", "params": {"direction": "up"}}]


def test_parse_actions_no_arg_ops():
    assert parse_actions("back") == [{"op": "back", "params": {}}]
    assert parse_actions("home") == [{"op": "home", "params": {}}]
    assert parse_actions("done") == [{"op": "done", "params": {}}]


def test_parse_actions_aliases():
    assert parse_actions("home_first") == [{"op": "home_first_page", "params": {}}]
    assert parse_actions("read") == [{"op": "read_screen", "params": {}}]
    assert parse_actions("next_page") == [{"op": "next_page", "params": {}}]


def test_parse_actions_wait_and_abort():
    assert parse_actions("wait 500") == [{"op": "wait", "params": {"ms": "500"}}]
    assert parse_actions("abort 找不到应用") == [
        {"op": "abort", "params": {"reason": "找不到应用"}}
    ]


def test_parse_actions_multiline_batch():
    text = "home_first\nnext_page\ntap 5"
    assert parse_actions(text) == [
        {"op": "home_first_page", "params": {}},
        {"op": "next_page", "params": {}},
        {"op": "tap", "params": {"id": "5"}},
    ]


def test_parse_actions_skips_blank_and_unknown_lines():
    text = "\n  \nfoobar\ntap 1\n"
    assert parse_actions(text) == [{"op": "tap", "params": {"id": "1"}}]
```

- [ ] **Step 2: 运行确认失败**

Run: `cd server && uv run pytest tests/test_decision.py::test_parse_actions_single_tap -v`
Expected: FAIL —— `ImportError: cannot import name 'parse_actions'`。

- [ ] **Step 3: 实现 `parse_actions`**

在 `server/app/decision.py` 的 [`_bounds_center()`](server/app/decision.py:96) 之后插入：

```python
# 无参指令别名 -> 规范 op
_NOARG_OPS = {
    "back": "back",
    "home": "home",
    "home_first": "home_first_page",
    "next_page": "next_page",
    "read": "read_screen",
    "done": "done",
}


def parse_actions(text: str) -> list[dict]:
    """把 LLM 文本指令块解析为动作列表(spec §3)。首空格切动词，文本参数取行尾。

    支持: tap n / input n 文本 / swipe dir / wait ms / abort 原因 / 无参别名。
    空行与无法识别的行跳过。
    """
    actions: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        verb, _, rest = line.partition(" ")
        rest = rest.strip()
        if verb in _NOARG_OPS:
            actions.append({"op": _NOARG_OPS[verb], "params": {}})
        elif verb == "tap" and rest:
            actions.append({"op": "tap", "params": {"id": rest.split()[0]}})
        elif verb == "input" and rest:
            idx, _, txt = rest.partition(" ")
            actions.append({"op": "input", "params": {"id": idx, "text": txt.strip()}})
        elif verb == "swipe" and rest:
            actions.append({"op": "swipe", "params": {"direction": rest.split()[0]}})
        elif verb == "wait" and rest:
            actions.append({"op": "wait", "params": {"ms": rest.split()[0]}})
        elif verb == "abort":
            actions.append({"op": "abort", "params": {"reason": rest}})
        # 其余无法识别 -> 跳过
    return actions
```

- [ ] **Step 4: 运行确认通过**

Run: `cd server && uv run pytest tests/test_decision.py -k parse_actions -v`
Expected: PASS（8 条全绿）。

- [ ] **Step 5: 提交**

```bash
git add server/app/decision.py server/tests/test_decision.py
git commit -m "feat(decision): add parse_actions text-instruction parser"
```

---

### Task 5: `decide` 接入文本协议 + 批处理下发 + 系统提示词

把 Task 4 的 `parse_actions` 接进 [`DecisionEngine.decide()`](server/app/decision.py:110)，让它返回 `list[Action]`（批处理）��gateway 逐条下发。同时把 [`_SYSTEM_PROMPT`](server/app/decision.py:12) 从「输出 JSON」改成「每行输出一条文本指令」。

**批处理规则（spec §3）：** LLM 一次可输出多行 → N 条盲操作（back/home/swipe/wait…）+ 最多 1 条 tap/input 收尾。gateway 按顺序下发，遇首个 tap/input 下发后**本批结束**，等端侧重抓帧。tap 仍在云侧把 `id` 还原为 bounds 中心坐标。

**Files:**
- Modify: `server/app/decision.py`（`_SYSTEM_PROMPT`、`decide` 返回 list）
- Modify: `server/app/gateway.py`（批处理逐条下发）
- Test: `server/tests/test_decision.py`、`server/tests/test_gateway_loop.py`

- [ ] **Step 1: 写 decide 批处理失败测试**

在 `test_decision.py` 追加：

```python
def test_decide_returns_action_list():
    llm = FakeLLM(["home_first\nnext_page\ntap 0"])
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    nodes = [Node(id="a", text="飞书", clickable=True, bounds=(200, 300, 400, 500))]
    actions = engine.decide(goal="打开飞书", perception=_perc(nodes), skill_name=None, cursor=0, history=[])
    assert isinstance(actions,list)
    assert [a.op for a in actions] == ["home_first_page", "next_page", "tap"]
    # tap 的 id=0 -> bounds 中心 (300,400)
    assert actions[-1].params["x"] == "300"
    assert actions[-1].params["y"] == "400"


def test_decide_non_instruction_falls_back_to_read_screen():
    llm = FakeLLM(["我需要更多信息，无法决定"])
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    actions = engine.decide(goal="x", perception=_perc([Node(id="a", text="首页")]), skill_name=None, cursor=0, history=[])
    assert [a.op for a in actions] == ["read_screen"]
```

> 注意：Task 3 里以 JSON 断言 `action.op`（返回单 Action）的旧用例（如 `test_tap_by_id_resolves_to_bounds_center`、`test_llm_non_json_falls_back_to_read_screen`、`test_fallback_to_llm_when_skill_miss`、`test_skill_hit_without_llm`、`test_cache_*`、`test_tap_*`）需同步改造：
> - FakeLLM 响应从 JSON 串改成文本指令串（如 `'{"op":"tap","params":{"id":"1"}}'` → `"tap 1"`）。
> - 断言从 `action.op` 改为 `actions[0].op` / `actions[-1]`。
> - skill/cache 分支仍返回单动作，用 `actions == [Action(...)]` 长度 1 断言。
> 逐个改到绿。

- [ ] **Step 2: 运行确认失败**

Run: `cd server && uv run pytest tests/test_decision.py::test_decide_returns_action_list -v`
Expected: FAIL —— 当前 `decide` 返回单 `Action`，无 `isinstance list`。

- [ ] **Step 3: 改 `_SYSTEM_PROMPT` 为文本指令格式**

> ⚠️ **关键：改 `RealLLM.complete` 停止 JSON 抽取。** [`llm.py`](server/app/llm.py:64) 的 `RealLLM.complete` 末尾调用 `_extract_json(_content)`，会把返回只截成首个 `{...}`——这会毁掉文本指令输出。本步同时改：
> - 把 `RealLLM.complete` 的 `return _extract_json(_content)` 改为 `return _clean_text(_content)`。
> - 新增纯函数 `_clean_text(text)`：仅剥离 `<think>...</think>` 段并 strip，不做 JSON 提取。
> - `_extract_json` 若已无引用可删（先 grep 确认 `grep_search "_extract_json"` 无其他调用再删）。
> - `build_llm()` 里无 key 时的 FakeLLM 默认响应 `'{"op":"read_screen","params":{}}'` 改为 `"read"`。
> 加对应单测 `test_llm.py`：`_clean_text("<think>x</think>tap 3")` == `"tap 3"`。

替换 [`_SYSTEM_PROMPT`](server/app/decision.py:12) 为（保留负一屏/打开应用流程等已验证内容）：

```python
_SYSTEM_PROMPT = """你是一个 Android 手机操作代理的决策核心。给定屏幕可交互元素列表(screen)、任务目标和历史操作，决定下一步动作。

screen 每行格式为 `[n] type "label"`，n 是行号，type 为 input/button/text。

你必须只输出「动作指令」，每行一条，不要输出解释、JSON、Markdown。合法指令：
- tap n            点击行号 n 的元素
- input n 文本      在行号 n 的输入框输入「文本」(文本取行尾全部)
- swipe up|down|left|right   滑动
- back / home      返回键 / 回桌面
- home_first       回桌面并归位最左第一屏(打开应用前必先执行)
- next_page        桌面向后翻一屏找应用图标
- wait 毫秒        等待
- read             信息不足时重读屏幕
- done             任务完成
- abort 原因        无法完成放弃

【批处理】可一次输出多行：若干条盲操作(back/home/swipe/wait/home_first/next_page)后，最多跟 1 条 tap 或 input 收尾。系统执行到第一条 tap/input 后会重新抓屏，故 tap/input 之后不要再写指令。

【打开应用】先 home_first 回第一屏 -> read 读屏找图标 -> tap 打开;没找到 -> next_page 翻屏再 read;翻到末页仍无 -> abort 原因「未找到应用X」。

【负一屏】桌面最左「负一屏」(小布建议/推荐磁贴)不是应用桌面，「XX有N条通知」「为你推荐」非应用图标，误点进错 app。识别到「小布建议」等特征必须先 swipe right 退出再找图标，绝不在负一屏 tap 磁贴。

示例:
home_first
read

打开飞书:
tap 5"""
```

- [ ] **Step 4: 改 `decide` 返回 `list[Action]`**

改造 [`decide()`](server/app/decision.py:110)：
1. 签名返回类型改 `-> list[Action]`。
2. skill/cache 命中分支：`return [Action(...)]`（包成单元素列表）。
3. LLM 分支：`raw` 不再 `json.loads`，改 `specs = parse_actions(raw)`；`if not specs: return [Action(op="read_screen", params={})]`。
4. 遍历 specs，对每个 `spec` 建 `Action`；若 `spec["op"]=="tap"`，用 `_resolve_tap_node(spec["params"], nodes)` 取节点、`_bounds_center` 注入 `x/y`（复用 Task 3 逻辑）。
5. 批处理截断：遍历 specs 累积 actions，遇首个 `tap`/`input` 追加后 `break`（丢弃其后指令）。
6. 删除所有 `[LLM-RAW-*]`/`frame_dump.json`/`encode_nodes_debug` 调用（插桩留到 Task 7 统一清，但本任务因 raw 不再是 JSON，`json.loads(raw)` 那段兜底必须删）。**本步先只删 `json.loads(raw)` 解析段与其 `data`/`op`/`params` 后续，替换为 parse_actions 流程；其余 `_diag.info` 诊断日志暂留，Task 7 清。**

参考实现骨架（替换 `raw = self._llm.complete(...)` 之后到 return 之间的主体）：

```python
        raw = self._llm.complete(
            system=_SYSTEM_PROMPT,
            user=json.dumps(payload, ensure_ascii=False),
        )
        _diag = logging.getLogger("phoneagent.gateway")
        _diag.info("[LLM-SCREEN-SENT]\n%s", payload["screen"])
        _diag.info("[LLM-RAW-RETURN] %r", raw)

        specs = parse_actions(raw)
        if not specs:
            return [Action(actionId=str(uuid.uuid4()), op="read_screen", params={})]

        actions: list[Action] = []
        for spec in specs:
            op = spec["op"]
            params = dict(spec.get("params", {}))
            if op == "tap":
                target = _resolve_tap_node(params, nodes)
                if target is not None:
                    center = _bounds_center(target.bounds)
                    if center is not None:
                        params["x"] = str(center[0])
                        params["y"] = str(center[1])
            actions.append(Action(actionId=str(uuid.uuid4()), op=op, params=params))
            if op in ("tap", "input"):
                break  # 收尾动作后本批结束，等重抓帧
        _diag.info("[ACTION-BATCH] %s", [(a.op, a.params) for a in actions])
        return actions
```

- [ ] **Step 5: 运行 decide 测试��认通过**

Run: `cd server && uv run pytest tests/test_decision.py -v`
Expected: PASS（含所有已改造旧用例 + 新批处理用例）。

- [ ] **Step 6: 改 gateway 逐条下发批处理**

在 [`gateway.py`](server/app/gateway.py:126) 把 `action = engine.decide(...)` 到末尾的下发逻辑改为遍历 `actions = engine.decide(...)`：

```python
            actions = engine.decide(
                goal=session.goal,
                perception=uplink,
                skill_name=None,
                cursor=cursor,
                history=history,
            )
            session.record_step()

            batch_broke = False
            for action in actions:
                logger.info("decided op=%s params=%s", action.op, action.params)
                if action.op == "done":
                    if applied_steps:
                        engine._cache.learn(session.goal, last_pkg, applied_steps)
                    await websocket.send_text(
                        TaskDone(taskId=session.task_id, result="ok", summary="task completed").to_json()
                    )
                    batch_broke = True
                    break
                if action.op == "abort":
                    await websocket.send_text(
                        TaskAbort(taskId=session.task_id, reason="llm_abort").to_json()
                    )
                    batch_broke = True
                    break
                applied_steps.append({"op": action.op, "params": action.params})
                await websocket.send_text(action.to_json())
            if batch_broke:
                break
```

- [ ] **Step 7: 改 gateway 测试的 FakeLLM 为文本指令**

`test_gateway_loop.py` 中 `PHONEAGENT_FAKE_LLM` 的 JSON 串改文本指令：
- `'{"op":"done","params":{}}'` → `"done"`
- `'{"op":"tap","params":{"match_text":"搜索"}}'` → `"tap 0"`（配合 fixture 节点行号）
- `'{"op":"read_screen","params":{}}'` → `"read"`
- `'{"op":"wait","params":{}}'` → `"wait 100"`

- [ ] **Step 8: 运行 gateway 测试确认通过**

Run: `cd server && uv run pytest tests/test_gateway_loop.py -v`
Expected: PASS。

- [ ] **Step 9: 全量回归 + 提交**

Run: `cd server && uv run pytest -v`
Expected: 全绿。

```bash
git add server/app/decision.py server/app/gateway.py server/tests/test_decision.py server/tests/test_gateway_loop.py
git commit -m "feat(decision): text-instruction protocol + batch action dispatch"
```

---

### Task 6: 通信原文双日志 comm.log / llm.log（常驻功能）

spec §6：新建 `server/app/comm_log.py`，提供两个 RotatingFileHandler logger（10MB×5）：
- `comm.log`：端↔云原文，格式 `ts|UP/DOWN|type|内容`
- `llm.log`：云↔LLM 原文，格式 `ts|LLM-REQ/RESP|内容`

**Files:**
- Create: `server/app/comm_log.py`
- Create: `server/tests/test_comm_log.py`
- Modify: `server/app/gateway.py`（收发处调 `log_up`/`log_down`）
- Modify: `server/app/llm.py`（`RealLLM.complete` 调 `log_llm_req`/`log_llm_resp`）

- [ ] **Step 1: 写失败测试**

新建 `server/tests/test_comm_log.py`：

```python
from app.comm_log import log_up, log_down, log_llm_req, log_llm_resp, _comm_logger, _llm_logger


def test_log_up_writes_line(tmp_path, monkeypatch):
    logfile = tmp_path / "comm.log"
    monkeypatch.setenv("PHONEAGENT_LOG_DIR", str(tmp_path))
    # 重置 handler 指向 tmp
    from app import comm_log
    comm_log._reset_for_test(tmp_path)
    log_up("perception", '{"a":1}')
    content = (tmp_path / "comm.log").read_text(encoding="utf-8")
    assert "UP" in content and "perception" in content and '{"a":1}' in content


def test_log_down_and_llm(tmp_path):
    from app import comm_log
    comm_log._reset_for_test(tmp_path)
    log_down("action", "tap 3")
    log_llm_req("system+user")
    log_llm_resp("tap 3")
    comm = (tmp_path / "comm.log").read_text(encoding="utf-8")
    llm = (tmp_path / "llm.log").read_text(encoding="utf-8")
    assert "DOWN" in comm and "tap 3" in comm
    assert "LLM-REQ" in llm and "LLM-RESP" in llm
```

- [ ] **Step 2: 运行确认失败**

Run: `cd server && uv run pytest tests/test_comm_log.py -v`
Expected: FAIL —— `ModuleNotFoundError: app.comm_log`。

- [ ] **Step 3: 实现 `comm_log.py`**

新建 `server/app/comm_log.py`：

```python
import logging
import os
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path


def _log_dir() -> Path:
    d = Path(os.getenv("PHONEAGENT_LOG_DIR",
                        Path(__file__).resolve().parents[1] / "logs"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _make_logger(name: str, filename: str) -> logging.Logger:
    lg = logging.getLogger(name)
    lg.setLevel(logging.INFO)
    lg.propagate = False
    if not lg.handlers:
        h = RotatingFileHandler(
            _log_dir() / filename, maxBytes=10 * 1024 * 1024,
            backupCount=5, encoding="utf-8",
        )
        h.setFormatter(logging.Formatter("%(message)s"))
        lg.addHandler(h)
    return lg


_comm_logger = _make_logger("phoneagent.comm", "comm.log")
_llm_logger = _make_logger("phoneagent.llmraw", "llm.log")


def _ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def log_up(msg_type: str, content: str) -> None:
    _comm_logger.info("%s|UP|%s|%s", _ts(), msg_type, content)


def log_down(msg_type: str, content: str) -> None:
    _comm_logger.info("%s|DOWN|%s|%s", _ts(), msg_type, content)


def log_llm_req(content: str) -> None:
    _llm_logger.info("%s|LLM-REQ|%s", _ts(), content)


def log_llm_resp(content: str) -> None:
    _llm_logger.info("%s|LLM-RESP|%s", _ts(), content)


def _reset_for_test(dir_path) -> None:
    """测试用：重建 handler 指向指定目录。"""
    global _comm_logger, _llm_logger
    os.environ["PHONEAGENT_LOG_DIR"] = str(dir_path)
    for name in ("phoneagent.comm", "phoneagent.llmraw"):
        lg = logging.getLogger(name)
        for h in list(lg.handlers):
            lg.removeHandler(h)
            h.close()
    _comm_logger = _make_logger("phoneagent.comm", "comm.log")
    _llm_logger = _make_logger("phoneagent.llmraw", "llm.log")
```

- [ ] **Step 4: 运行确认通过**

Run: `cd server && uv run pytest tests/test_comm_log.py -v`
Expected: PASS。

- [ ] **Step 5: gateway 接入 log_up/log_down**

在 [`gateway.py`](server/app/gateway.py:82) `raw = await websocket.receive_text()` 成功后加 `log_up(uplink.type, raw)`（放在 `parse_uplink` 之后拿到 type）；每个 `await websocket.send_text(x)` 前后配一条 `log_down(<type>, x)`。顶部 `from app.comm_log import log_up, log_down`。

- [ ] **Step 6: llm.py 接入 log_llm_req/resp**

在 [`RealLLM.complete`](server/app/llm.py:64) 请求前 `log_llm_req(system + "\n---\n" + user)`，拿到 `_content` 后 `log_llm_resp(_content)`。顶部 `from app.comm_log import log_llm_req, log_llm_resp`。

- [ ] **Step 7: 回归 + 提交**

Run: `cd server && uv run pytest -v`
Expected: 全绿。

```bash
git add server/app/comm_log.py server/tests/test_comm_log.py server/app/gateway.py server/app/llm.py
git commit -m "feat(log): persistent comm.log/llm.log raw traffic logging"
```

---

### Task 7: 真机端到端验证 + 清理调试插桩

spec §5：功能全部实现后，先真机验证「点击不再错位、批处理连贯、日志落盘」，通过后统一清除调试插桩，再合并主线。

**清理清单（spec §5）：**

云侧 `server/app/decision.py`：
- 删 `encode_nodes_debug` 函数（[decision.py:94](server/app/decision.py:94)）
- 删所有 `_diag.info("[LLM-SCREEN-SENT]...`、`[LLM-RAW-RETURN]`、`[FRAME]`、`[NODE]`、`[TAP-RESOLVE]`、`[FRAME-DUMP]` 及 `frame_dump.json` 写盘整段（Task 5 后残留的 `_diag`）
- 保留 `[ACTION-BATCH]` 一条精简日志即可，或改走 comm_log
- 删无用 `import os`、`import time`（若清理后不再引用）

云侧 `server/app/llm.py`：
- 删 `[LLM-RAW-UNCLEANED]` 日志（[llm.py:78](server/app/llm.py:78)），改由 Task 6 的 `log_llm_resp` 承担

端侧 `PhoneAgentService.kt`：
- 删 `DEBUG_ONESHOT_PREFIX`、`DEBUG_CAPTURE_DELAY_MS`、`readOnlyMode` 及其分支（[PhoneAgentService.kt:28-88](android/app/src/main/java/com/example/phoneagent/accessibility/PhoneAgentService.kt:28)）
- 删调试测试按钮（若在 UI 层，grep `DEBUG-ONESHOT` 定位）

**Files:**
- Modify: `server/app/decision.py`、`server/app/llm.py`
- Modify: `android/app/src/main/java/com/example/phoneagent/accessibility/PhoneAgentService.kt`
- 相关调试测试按钮所在 UI 文件

- [ ] **Step 1: 部署待验证版本**

```bash
# 云侧重启
cd server && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 &
# 端侧重装(注意：真机验证前不 commit 主线)
cd android && JAVA_HOME=/opt/homebrew/opt/openjdk@17 ./gradlew :app:installDebug
```

- [ ] **Step 2: 真机验证矩阵（人工，逐项打勾）**

在真机上下发「打开飞书给张三发消息」类任务，观察并确认：
- [ ] 点击命中率：桌面图标 tap 命中正确 App（不再进负一屏磁贴/小红书）
- [ ] 节点合并：`comm.log` 里 UP perception 的 screen 每行都有非空 label，无重复碎片
- [ ] 批处理连贯：`llm.log` 中一次 LLM-RESP 含多行（如 home_first→next_page），端侧顺序执行到 tap 后重抓帧
- [ ] 编号定位：`tap n` 下发的 x/y 与目标 bounds 中心吻合
- [ ] 日志落盘：`server/logs/comm.log`、`llm.log` 均有内容且格式正确
- [ ] viewId 兜底：无 text/desc 的图标节点，label 来自 viewIdResourceName（可在 comm.log 抽查）

> ⚠️ 若任一项失败：进入 `superpowers:systematic-debugging`，先复现→定位→写回归测试→修，不要盲改。修复后回到 Step 1 重验。

- [ ] **Step 3: 验证全绿后清理云侧插桩**

按清理清单删 `decision.py` / `llm.py` 调试段。删后运行：

Run: `cd server && uv run pytest -v`
Expected: 全绿（清理不应影响任何单测；若某测试依赖 `encode_nodes_debug` 需一并删该测试）。

- [ ] **Step 4: 清理端侧插桩**

按清理清单删 `PhoneAgentService.kt` 的 readOnly/oneshot 调试逻辑。删后：

Run: `cd android && JAVA_HOME=/opt/homebrew/opt/openjdk@17 ./gradlew :app:testDebugUnitTest`
Expected: BUILD SUCCESSFUL，测试全绿。

- [ ] **Step 5: 清理后再回归一次真机（冒烟）**

重装 + 重启，再跑一遍 Step 2 的核心 2 项（点击命中、批��理连贯），确认清理没引入回归。

- [ ] **Step 6: 提交清理**

```bash
git add -A
git commit -m "chore: remove debug instrumentation after on-device verification"
```

---

## Self-Review Checklist（agent 执行完全部任务后逐项核对）

- [ ] spec §1 端侧合并：`pickLabel` 覆盖 text→desc→子孙→viewIdToLabel 四级；editable 节点保留（walk 中 `shouldKeep(editable=...)` 未动）
- [ ] spec §2 上行 SoM：screen 为 `[n] type "label"`，`_encode_nodes` 未破坏；`[n]` 是唯一引用键
- [ ] spec §3 下行指令 + 批处理：`parse_actions` 覆盖全部指令；`decide` 遇 tap/input break；gateway 逐条下发
- [ ] spec §4 引用键：`_resolve_tap_node` 只认 id 下标，match_text 分支已删（技能缓存路径的 match_text 保留，不冲突）
- [ ] spec §5 插桩清理：decision.py / llm.py / PhoneAgentService.kt 三处调试标记全清
- [ ] spec §6 双日志：comm.log/llm.log RotatingFileHandler(10MB×5)，UP/DOWN/LLM-REQ/RESP 格式
- [ ] 跨任务命名一致：`viewIdResourceName`(端云同名)、`viewIdToLabel`/`pickLabel`(端)、`parse_actions`/`_resolve_tap_node`(云)
- [ ] 向后兼容：`viewIdResourceName` 为可选字段，旧 payload 不报错
- [ ] 无占位符/TODO 遗留
- [ ] 所有 commit 均在真机验证通过后才合并主线

## 执行方式建议

- **推荐 Subagent-Driven**（`superpowers:subagent-driven-development`）：Task 1–6 每个都是独立可测的 bite-sized 单元，适合分派子 agent 逐个实现-验证-提交；Task 7 因含人工真机验证，须由主 session 亲自执行。
- **或 Inline Execution**（`superpowers:executing-plans`）：单 session 顺序执行，每个 Task 完成后停下让用户 review。
