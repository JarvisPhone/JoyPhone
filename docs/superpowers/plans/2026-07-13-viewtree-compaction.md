# View Tree 感知裁剪与紧凑编码 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把端侧 view tree 感知从「无差别收集所有可见文本」改为「只收可操作结构元素」，并把云侧传给 LLM 的表示从全字段 JSON 改为紧凑编号文本行，彻底消除巨型页面（微博 2973 节点）导致的 context window 溢出崩溃。

**Architecture:** 端云分工正交。端侧 `NodeFlattener` 负责「减少节点数量」（强过滤 + 子树向上合并 + text 截断）；云侧 `decision.py` 负责「紧凑编码格式」（去 bounds/className、编号文本行、上限兜底）。协议 `NodeDto`/`Node` 结构不变（向后兼容），端侧 tap/input 定位机制不变（仍靠 text/desc 重定位）。

**Tech Stack:** Python 3（pytest、pydantic、FakeLLM）；Kotlin（JUnit4，纯 JVM 单——不依赖 `android.graphics.Rect`/`AccessibilityNodeInfo`）。

**分支：** feat/app-driven-goal
**参考 spec：** `docs/superpowers/specs/2026-07-13-viewtree-compaction-design.md`

---

## File Structure

- `server/app/decision.py`（Modify）：新增 `MAX_LLM_NODES`量、`_encode_nodes()` 编码函数、`decide()` 里 payload 改 `screen` 字段、更新 `_SYSTEM_PROMPT`。
- `server/tests/test_decision.py`（Modify）：清理重复/损坏测试，改写为 `screen` 字段 + 编文本格式 + 上限兜底 + 可交互优先测试。
- `android/app/src/main/java/com/example/phoneagent/accessibility/NodeFlattener.kt`（Modify）：抽出纯逻辑辅助函数（`truncate`、`shouldKeep`、`firstNonBlank`），改写 `walk` 为强过滤 + 子树向上合并。
- `android/app/src/test/java/com/example/phoneagent/accessibility/NodeFlattenerTest.kt`（Modify）：为新纯逻辑辅助函数补单测。

**约束（来自现有测试模式）：** Kotlin JVM 单测不能触碰 `AccessibilityNodeInfo`/`Rect`（not-mocked 会抛异常）。因此端侧所有可单测逻辑必须抽成不依赖 framework 类型的纯函数；`walk` 的 framework 遍历部分属集成层，靠真机联调验证。

---

## Phase 1：云侧紧凑编码（decision.py）

### Task 1: 清理 test_decision.py 中重复/损坏的测试

**Files:**
- Modify: `server/tests/test_decision.py`

**背景：** 当前文件里 `test_large_node_tree_is_capped_before_llm` 和 `test_capping_prefers_clickable_nodes` 各定义了两次，且第一份的 `test_capping_prefers_clickable_nodes` 结尾有 `assert action.params == {}`（`action` 未赋值，NameError）。先删掉所有这 4 个旧的上限测试，Phase 1 后续任务会用新格式重写。

- [ ] **Step 1: 删除全部 4 个旧的上限相关测试**

删除文件中所有名为 `test_large_node_tree_is_capped_before_llm` 和 `test_capping_prefers_clickable_nodes` 的函数（共 4 段，包括损坏那段）。保留 `test_skill_hit_without_llm`、`test_fallback_to_llm_when_skill_miss`、`test_cache_hit_returns_step_without_llm`、`test_cache_miss_when_node_not_matchable_falls_through`、`test_llm_non_json_falls_back_to_read_screen`、`test_llm_empty_string_falls_back_to_read_screen`。

- [ ] **Step 2: 运行剩余测试确认无 NameError / 无收集错误**

Run: `cd server && .venv/bin/pytest tests/test_decision.py -q`
Expected: 收集不报错；`test_fallback_to_llm_when_skill_miss` 仍 PASS（此时 payload 还是旧的 `nodes` 键，Task 3 才改）。

- [ ] **Step 3: Commit**

```bash
git add server/tests/test_decision.py
git commit -m "test: remove duplicated/broken node-capping tests before rewrite"
```

---

### Task 2: 实现 `_encode_nodes` 紧凑编号文本编码

**Files:**
- Modify: `server/app/decision.py`
- Modify: `server/tests/test_decision.py`

编码规则（来自 spec 组件设计 §3）：
- 序号 = 节点在 `nodeTree` 中的下标。
- 类型标签：`editable` → `input`；`clickable` → `button`；其余 → `text`。（图标/tab 无法从 Node 字段可靠区分，统一归 `button`；spec 里 icon/tab 只是示意，实现用 button 足够，LLM 靠文本判断。）
- 每行格式：`[序号] 类型 "文本"`，文本取 `text`，为空取 `desc`，都空则空串。
- 各行以 `\n` 连接；空列表回空串 `""`。

- [ ] **Step 1: Write the failing test**

在 `server/tests/test_decision.py` 末尾追加：

```python
from app.decision import _encode_nodes


def test_encode_nodes_formats_numbered_lines():
    nodes = [
        Node(id="a", text="首页", clickable=True),
        Node(id="b", text="搜索", editable=True),
        Node(id="c", desc="微博", clickable=True),
        Node(id="d", text="正文"),
    ]
    out = _encode_nodes(nodes)
    assert out == '[0] button "首页"\n[1] input "搜索"\n[2] button "微博"\n[3] text "正文"'


def test_encode_nodes_empty_is_empty_string():
    assert _encode_nodes([]) == ""


def test_encode_nodes_blank_text_and_desc_keeps_empty_quotes():
    nodes = [Node(id="x", clickable=True)]
    assert _encode_nodes(nodes) == '[0] button ""'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && .venv/bin/pytest tests/test_decision.py::test_encode_nodes_formats_numbered_lines -v`
Expected: FAIL with `ImportError: cannot import name '_encode_nodes'`

- [ ] **Step 3: Write minimal implementation**

在 `server/app/decision.py` 顶部（`_SYSTEM_PROMPT` 定义之后、`class DecisionEngine` 之前）新增：

```python
from app.protocol import Node


def _node_type(node: Node) -> str:
    if node.editable:
        return "input"
    if node.clickable:
        return "button"
    return "text"


def _encode_nodes(nodes: list[Node]) -> str:
    lines = []
    for i, n in enumerate(nodes):
        label = (n.text or n.desc or "").strip()
        lines.append(f'[{i}] {_node_type(n)} "{label}"')
    return "\n".join(lines)
```

注意：`from app.protocol import Node` 需加到现有 `from app.protocol import Action, Perception` 那行（合为 `from app.protocol import Action, Node, Perception`），不要重复 import。

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && .venv/bin/pytest tests/test_decision.py -k encode_nodes -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add server/app/decision.py server/tests/test_decision.py
git commit -m "feat(decision): add _encode_nodes compact numbered-text encoding"
```

---

### Task 3: `decide()` 改用 `screen` 字段 + 上限兜底 `MAX_LLM_NODES`

**Files:**
- Modify: `server/app/decision.py`
- Modify: `server/tests/test_decision.py`

- [ ] **Step 1: 更新失败测试（改 payload 断言 + 加上限/优先测试）**

把 `server/tests/test_decision.py` 里 `test_fallback_to_llm_when_skill_miss` 结尾对 payload 的断言替换为：

```python
    payload = json.loads(captured["user"])
    assert set(payload.keys()) == {"goal", "screen", "history"}
    assert payload["goal"] == "发消息"
    assert payload["history"] == []
    assert payload["screen"] == '[0] text "首页"'
```

再在文件末尾追加：

```python
def test_large_node_tree_capped_and_encoded(monkeypatch):
    # 巨型页面(3000 节点)必须在发给 LLM 前截断到 MAX_LLM_NODES，且以 screen 编号文本传递。
    captured = {}
    llm = FakeLLM(['{"op":"back","params":{}}'])

    def _capture(system, user, image_b64=None):
        captured["user"] = user
        return '{"op":"back","params":{}}'

    monkeypatch.setattr(llm, "complete", _capture)
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    nodes = [Node(id=f"n{i}", text=f"item{i}") for i in range(3000)]
    engine.decide(goal="发消息", perception=_perc(nodes), skill_name=None, cursor=0, history=[])

    payload = json.loads(captured["user"])
    assert "screen" in payload and "nodes" not in payload
    line_count = len(payload["screen"].splitlines())
    assert line_count <= DecisionEngine.MAX_LLM_NODES


def test_capping_prefers_interactive_nodes(monkeypatch):
    # 裁剪时优先保留可交互节点(clickable/editable)，避免把操作目标挤掉。
    captured = {}
    llm = FakeLLM(['{"op":"back","params":{}}'])

    def _capture(system, user, image_b64=None):
        captured["user"] = user
        return '{"op":"back","params":{}}'

    monkeypatch.setattr(llm, "complete", _capture)
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    nodes = [Node(id=f"t{i}", text=f"text{i}") for i in range(3000)]
    nodes.append(Node(id="target", text="飞书", clickable=True))
    engine.decide(goal="打开飞书", perception=_perc(nodes), skill_name=None, cursor=0, history=[])

    payload = json.loads(captured["user"])
    assert '飞书' in payload["screen"]  # clickable 目标不能被裁掉
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd server && .venv/bin/pytest tests/test_decision.py -k "fallback_to_llm or capped or prefers_interactive" -v`
Expected: FAIL —`test_fallback_to_llm_when_skill_miss` 断言 `screen` 失败（当前是 `nodes`）；`AttributeError: MAX_LLM_NODES`。

- [ ] **Step 3: Write minimal implementation**

在 `server/app/decision.py` 的 `class DecisionEngine` 里加类常量，并改写 `decide()` 中构造 payload 那段：

类顶部（`def __init__` 之前）加：

```python
    MAX_LLM_NODES = 80
```

把 `decide()` 里原来的：

```python
        payload = {
            "goal": goal,
            "nodes": [n.model_dump(exclude_none=True) for n in perception.nodeTree],
            "history": history,
        }
```

替换为：

```python
        nodes = self._cap_nodes(perception.nodeTree)
        payload = {
            "goal": goal,
            "screen": _encode_nodes(nodes),
            "history": history,
        }
```

并在 `class DecisionEngine` 内新增裁剪方法（可交互优先）：

```python
    def _cap_nodes(self, nodes: list[Node]) -> list[Node]:
        if len(nodes) <= self.MAX_LLM_NODES:
            return nodes
        interactive = [n for n in nodes if n.clickable or n.editable]
        others = [n for n in nodes if not (n.clickable or n.editable)]
        capped = (interactive + others)[: self.MAX_LLM_NODES]
        # 保持原始下标顺序，使序号对齐屏幕直觉
        keep = set(id(n) for n in capped)
        return [n for n in nodes if id(n) in keep]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && .venv/bin/pytest tests/test_decision.py -q`
Expected: all passed

- [ ] **Step 5: 更新 `_SYSTEM_PROMPT` 描述 screen 格式**

把 `_SYSTEM_PROMPT` 中这两处更新：

将开头 `给定当前屏幕的可交互节点、任务目标和历史操作` 改为 `给定当前屏幕的可交互元素列表(screen)、任务目标和历史操作`。

在 `- abort: ...` 那行之后、`打开应用的流程：` 之前插入一段：

```
输入里的 screen 是当前屏可交互元素列表，每行格式为 `[序号] 类型 "文本"`，
类型为 input(输入框)/button(可点击)/text(纯文本)。tap/input 的 match_text 填元素文本，
也可用 {"id": "序号"} 指定行号。
```

- [ ] **Step 6: Run full decision suite + whole server suite**

Run: `cd server && .venv/bin/pytest tests/test_decision.py -q && .venv/bin/pytest -q`
Expected: all passed（若其他测试引用旧 `nodes` payload，需一并修，但预期仅 test_decision.py 涉及）。

- [ ] **Step 7: Commit**

```bash
git add server/app/decision.py server/tests/test_decision.py
git commit -m "feat(decision): send compact screen text to LLM with MAX_LLM_NODES cap"
```

---

## Phase 2：端侧强过滤 + 子树向上合并 + text 截断（NodeFlattener.kt）

### Task 4: 抽出并测试纯逻辑辅助函数

**Files:**
- Modify: `android/app/src/main/java/com/example/phoneagent/accessibility/NodeFlattener.kt`
- Modify: `android/app/src/test/java/com/example/phoneagent/accessibility/NodeFlattenerTest.kt`

只加不依赖 framework 类型的纯函数，先单测锁定行为。

- [ ] **Step 1: Write the failing tests**

在 `NodeFlattenerTest.kt` 的 `class NodeFlattenerTest {` 内追加：

```kotlin
    @Test
    fun truncate_keeps_short_text_unchanged() {
        assertEquals("你好", NodeFlattener.truncate("你好"))
    }

    @Test
    fun truncate_cuts_long_text_with_ellipsis() {
        val long = "一".repeat(30)
        val out = NodeFlattener.truncate(long)
        assertEquals(NodeFlattener.MAX_TEXT_LEN + 1, out.length) // 20 字 + 省略号
        assertEquals("…", out.substring(out.length - 1))
    }

    @Test
    fun truncate_null_returns_null() {
        assertEquals(null, NodeFlattener.truncate(null))
    }

    @Test
    fun should_keep_true_for_interactive_flags() {
        assertEquals(true, NodeFlattener.shouldKeep(clickable = true, editable = false, scrollable = false, checkable = false, hasDesc = false))
        assertEquals(true, NodeFlattener.shouldKeep(clickable = false, editable = true, scrollable = false, checkable = false, hasDesc = false))
        assertEquals(true, NodeFlattener.shouldKeep(clickable = false, editable = false, scrollable = true, checkable = false, hasDesc = false))
        assertEquals(true, NodeFlattener.shouldKeep(clickable = false, editable = false, scrollable = false, checkable = true, hasDesc = false))
    }

    @Test
    fun should_keep_true_when_has_content_description() {
        assertEquals(true, NodeFlattener.shouldKeep(clickable = false, editable = false, scrollable = false, checkable = false, hasDesc = true))
    }

    @Test
    fun should_keep_false_for_plain_text_leaf() {
        // 纯文本叶子（不可交互、无 desc）被丢弃
        assertEquals(false, NodeFlattener.shouldKeep(clickable = false, editable = false, scrollable = false, checkable = false, hasDesc = false))
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd android && JAVA_HOME=/opt/homebrew/opt/openjdk@17 ./gradlew :app:testDebugUnitTest --tests "com.example.phoneagent.accessibility.NodeFlattenerTest"`
Expected: FAIL —编译错误 `unresolved reference: truncate / shouldKeep / MAX_TEXT_LEN`

- [ ] **Step 3: Write minimal implementation**

在 `NodeFlattener.kt` 的 `object NodeFlattener {` 内（`flatten` 之前）加：

```kotlin
    const val MAX_TEXT_LEN = 20

    /** text 截断：超过 MAX_TEXT_LEN 加省略号。null 原样返回。纯逻辑，可单测。 */
    fun truncate(s: String?): String? {
        if (s == null) return null
        return if (s.length > MAX_TEXT_LEN) s.substring(0, MAX_TEXT_LEN) + "…" else s
    }

    /** 是否保留该节点：可交互或携带可定位语义(desc)。纯逻辑，可单测。 */
    fun shouldKeep(
        clickable: Boolean,
        editable: Boolean,
        scrollable: Boolean,
        checkable: Boolean,
        hasDesc: Boolean,
    ): Boolean = clickable || editable || scrollable || checkable || hasDesc
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd android && JAVA_HOME=/opt/homebrew/opt/openjdk@17 ./gradlew :app:testDebugUnitTest --tests "com.example.phoneagent.accessibility.NodeFlattenerTest"`
Expected: PASS（原有 3 个 + 新增 6 个）

- [ ] **Step 5: Commit**

```bash
git add android/app/src/main/java/com/example/phoneagent/accessibility/NodeFlattener.kt android/app/src/test/java/com/example/phoneagent/accessibility/NodeFlattenerTest.kt
git commit -m "feat(flatten): add pure truncate/shouldKeep helpers with unit tests"
```

---

### Task 5: 改写 `walk` 为强过滤 + 子树向上合并

**Files:**
- Modify: `android/app/src/main/java/com/example/phoneagent/accessibility/NodeFlattener.kt`

这是 framework 集成层（依赖 `AccessibilityNodeInfo`），靠 Task 4 的纯逻辑单测 + Phase 3 真机联调验证，本任务不写 JVM 单测（会 not-mocked 崩）。

- [ ] **Step 1: 改写 `walk`**

把现有 `walk` 整体替换为：

```kotlin
    /**
     * 递归收集节点：
     * - 可交互(clickable/editable/scrollable/checkable)或有 contentDescription 才收录。
     * - 子树向上合并：可交互节点自身 text 为空时，取子树中最近的非空 text/desc 补上。
     * - 合并后不再单独收录被吸收的纯文本叶子。
     * framework 集成，真机验证。
     */
    private fun walk(node: AccessibilityNodeInfo, path: List<Int>, out: MutableList<NodeDto>) {
        val rect = Rect().also { node.getBoundsInScreen(it) }
        val visible = rect.width() > 0 && rect.height() > 0
        val text = node.text?.toString()
        val desc = node.contentDescription?.toString()
        val interactive = node.isClickable || node.isEditable || node.isScrollable || node.isCheckable
        val keep = visible && shouldKeep(
            clickable = node.isClickable,
            editable = node.isEditable,
            scrollable = node.isScrollable,
            checkable = node.isCheckable,
            hasDesc = !desc.isNullOrBlank(),
        )

        if (keep) {
            // 可交互但自身无文本 -> 向下摘一个最近的非空 text/desc 补上
            val label = when {
                !text.isNullOrBlank() -> text
                !desc.isNullOrBlank() -> desc
                interactive -> firstDescendantLabel(node)
                else -> null
            }
            out.add(
                NodeDto(
                    id = makeId(path),
                    text = truncate(label),
                    desc = truncate(desc),
                    className = node.className?.toString(),
                    bounds = rectToBounds(rect),
                    clickable = node.isClickable,
                    editable = node.isEditable,
                )
            )
        }

        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            walk(child, path + i, out)
        }
    }

    /** 深度优先取子树中第一个非空 text/desc（供可交互父容器合并用）。 */
    private fun firstDescendantLabel(node: AccessibilityNodeInfo): String? {
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val t = child.text?.toString()
            if (!t.isNullOrBlank()) return t
            val d = child.contentDescription?.toString()
            if (!d.isNullOrBlank()) return d
            val deeper = firstDescendantLabel(child)
            if (deeper != null) return deeper
        }
        return null
    }
```

说明：本次实现保留了「递归所有子节点」而非严格剪枝——纯文本叶子因 `shouldKeep=false` 自然不被收录，等价于「不再单独收录纯文本叶」；可交互父容器会通过 `firstDescendantLabel` 拿到标签。这样最小改动即满足 spec 的「合并 + 丢纯文本叶」目标，避免复杂剪枝带来的误删风险。

- [ ] **Step 2: 编译验证（无单测，仅确保编译通过）**

Run: `cd android && JAVA_HOME=/opt/homebrew/opt/openjdk@17 ./gradlew :app:compileDebugKotlin`
Expected: BUILD SUCCESSFUL

- [ ] **Step 3: 跑全部单测确保纯逻辑测试仍绿**

Run: `cd android && JAVA_HOME=/opt/homebrew/opt/openjdk@17 ./gradlew :app:testDebugUnitTest`
Expected: BUILD SUCCESSFUL

- [ ] **Step 4: Commit**

```bash
git add android/app/src/main/java/com/example/phoneagent/accessibility/NodeFlattener.kt
git commit -m "feat(flatten): strong filter + subtree label merge + text truncation"
```

---

## Phase 3：真机联调复测

### Task 6: 重装 apk + 重启 uvicorn，复现微博/飞书验证不溢出

**Files:** 无（联调验证）

**前置：** 改了 `decision.py`（云侧）必须重启 uvicorn；改了 `NodeFlattener.kt`（端侧）必须重装 apk。

- [ ] **Step 1: 重装 apk**

Run: `cd android && JAVA_HOME=/opt/homebrew/opt/openjdk@17 ./gradlew :app:installDebug`
Expected: BUILD SUCCESSFUL

- [ ] **Step 2: 重启 uvicorn（先停旧进程再起）**

停掉当前 uvicorn 进程（查 pid：`ps aux | grep uvicorn | grep -v grep`），然后重启（沿用项目既有启动命令，后台运行并把日志写到 `/tmp/uvicorn.log`）。

- [ ] **Step 3: 触发 TEST_GOAL 并观察日志**

在真机点「运行测试任务」，后台 `tail -f /tmp/uvicorn.log`。
Expected:
- gateway 日志 `perception pkg=... nodes=N`，微博页面 N 从 2973 降到几十个（≤ MAX_LLM_NODES=80）。
- 不再现 `openai.BadRequestError: 400 ... context window exceeds limit`。
- WS 循环不断连，决策链能继续走 tap/next_page 等算子。

- [ ] **Step 4: 若节点数仍偏高或误裁目标**

若微博页 N 仍 >80 或找不到飞书图标：读 `/tmp/uvicorn.log` 里编码后的 `screen` 内容，检查是哪些节点漏过滤（回到 Task 5 调 `shouldKeep`/合并逻辑），或 `MAX_LLM_NODES` 需微调。属调优迭代，不改架构。

- [ ] **Step 5: 复测通过后 commit（若 Step 4 有代码改动）**

```bash
git add -A
git commit -m "test: on-device verify viewtree compaction eliminates context overflow"
```

---

## Self-Review

**Spec 覆盖：**
- 端侧强过滤 → Task 4（shouldKeep）+ Task 5（walk）✅
- 子树向上合并 → Task 5（firstDescendantLabel）✅
- text 截断 MAX_TEXT_LEN=20 → Task 4（truncate）✅
- 云侧 `_encode_nodes` 编号文本 → Task 2 ✅
- payload 改 `screen` → Task 3 ✅
- `_SYSTEM_PROMPT` 更新 → Task 3 Step 5 ✅
- `MAX_LLM_NODES=80` 上限兜底 + 可交互优先 → Task 3 ✅
- 端云协议不变（NodeDto/Node 结构保持）→ 全程未改协议 ✅
- 测试策略（端侧纯文本叶丢弃/合并/截断；云侧格式/上限/优先/screen 字段）→ Task 2、3、4 ✅
- 真机复测 → Task 6 ✅

**Placeholder 扫描：** 无 TBD/TODO；每个代码步均含完整代码。Task 5 无单测是刻意决策（framework not-mocked，已在任务内说明）。

**类型/签名一致性：**
- `_encode_nodes(nodes: list[Node]) -> str`（Task 2 定义，Task 3 调用一致）。
- `DecisionEngine.MAX_LLM_NODES` / `_cap_nodes`（Task 3 内定义并使用）。
- `NodeFlattener.truncate` / `shouldKeep` / `MAX_TEXT_LEN`（Task 4 定义，Task 5 调用签名一致：shouldKeep 5 个布尔参数）。
- `firstDescendantLabel`（Task 5 内定义并使用）。

**注意事项：**
- Task 5 里 `desc` 也做了 `truncate`，与 spec「text/desc 都截断」一致。
- `_cap_nodes` `id(n)` 去重保序，仅在 >MAX_LLM_NODES 时触发，正常强过滤后不触发（defense-in-depth）。