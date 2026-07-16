# 屏幕场景状态机重构（阶段二） 实现计划

> **For agentic workers**: 执行本 plan 前先激活 `test-driven-development` skill（RED→GREEN→REFACTOR 铁律）。每个 Task 是一次 2–5 分钟的原子动作，禁止跳步、禁止占位符（no placeholder / no TODO）。每个 Task 末尾给出的验证命令必须真跑并看到预期结果才算完成，然后才 commit。

- 关联 spec：`docs/superpowers/specs/2026-07-16-scene-state-machine-refactor-design.md`
- 关联问题：PKG_GUARD 死循环（`server/app/decision.py:200-208` 无脑 `home_first_page`）
- 前置状态：`scene.py`（`detect_scene` + `next_action` 转移表，20 测试全绿）与 8 份 fixtures 已落地。`test_decision.py` 有 **2 个 pkg guard RED 测试**（`test_pkg_guard_minus_one_swipes_right_not_home` / `test_pkg_guard_recent_apps_presses_home`）待转绿；另 `test_skill_hit_without_llm` 为**与本次无关的既有失败**，本 plan 不处理。

## Goal

把「归位」从端侧黑盒复合动作重构为**云端逐帧驱动的显式状态机**：端侧退化为哑执行器（只做原子 op），云端持 scene 状态机 + 转移表逐帧收敛，配收敛守卫（停滞/振荡）+ 三级脱困阶梯（转移表 → LLM 脱困 → 机械降级/abort）。

## Architecture

```
LLM(语义层)   → pkg guard 场景输出 target_scene: HOME；正常任务仍输出具体 op
云端(导航层)  → detect_scene(perception) 得 current → next_action(current, HOME) → 下发单个原子动作
端侧(执行层)  → 哑执行器：tap/input/swipe/back/home/read_screen/wait
云端(收敛层)  → 逐帧重判 scene；收敛守卫防兜圈；卡死走三级脱困
```

per-task guard 状态 `{scene_history, stall_count, last_op, escalation_level}` 存 `Session`，`decide()` 原地读写；task.end 随 Session 销毁，不落盘。

## Tech Stack

- 云端：Python 3.12 / pydantic / pytest（`server/.venv/bin/python -m pytest`）
- 端侧：Kotlin / JUnit（`android/gradlew testDebugUnitTest`）

## File Structure

| 文件 | 动作 | 职责 |
|------|------|------|
| `server/app/scene.py` | modify | 顶部加 5 个守卫常量；新增 `_FALLBACK` 备选动作表 + `fallback_action()` |
| `server/app/decision.py` | modify | pkg guard 段接入 `detect_scene`/`next_action` + 收敛守卫 + 三级脱困；`_NOARG_OPS` 删 `home_first`/`next_page`；`decide()` 加 `guard` 参数；`_SYSTEM_PROMPT` 移除 `home_first`/`next_page` 指令 |
| `server/app/session.py` | modify | `Session` 加 `guard` 字段（初始化空守卫状态） |
| `server/app/gateway.py` | modify | `engine.decide(...)` 传入 `session.guard` |
| `server/app/protocol.py` | modify | `Action.op` Literal 删 `home_first_page`/`next_page` |
| `server/tests/test_decision.py` | modify | 2 个 RED 转绿保持；新增停滞/振荡/脱困/降级/abort 测试 |
| `server/tests/test_scene.py` | modify | 新增 `_FALLBACK`/`fallback_action` 测试 |
| `android/.../accessibility/Executor.kt` | modify | 删 `homeFirstPage()`/`nextPage()`/`swipeHorizontal()`/`snapshotNodes()`/`snapshotFingerprint()`；when 删 2 case |
| `android/.../accessibility/HomeDetector.kt` | delete | 判定权移云端 |
| `android/.../accessibility/ScreenFingerprint.kt` | delete | 指纹判定移云端 scene 序列 |
| `android/.../test/.../HomeDetectorTest.kt` | delete | 随 HomeDetector 删 |
| `android/.../test/.../ScreenFingerprintTest.kt` | delete | 随 ScreenFingerprint 删 |
| `android/.../protocol/Messages.kt` | modify | 注释更新（op 集合收窄，无结构改动） |

---

## 提交点 2：端侧删除土法逻辑

### Task 2.1 — 删除 HomeDetector / ScreenFingerprint 及其测试

删除 4 个文件：
- `android/app/src/main/java/com/example/phoneagent/accessibility/HomeDetector.kt`
- `android/app/src/main/java/com/example/phoneagent/accessibility/ScreenFingerprint.kt`
- `android/app/src/test/java/com/example/phoneagent/accessibility/HomeDetectorTest.kt`
- `android/app/src/test/java/com/example/phoneagent/accessibility/ScreenFingerprintTest.kt`

（用文件删除操作，不是清空内容。）

### Task 2.2 — 收窄 Executor.kt

改 `android/app/src/main/java/com/example/phoneagent/accessibility/Executor.kt`：

1. `execute()` when 分派删两行：
```kotlin
            "home_first_page" -> homeFirstPage()
            "next_page" -> nextPage()
```
2. 删除私有方法 `homeFirstPage()`、`nextPage()`、`swipeHorizontal()`、`snapshotNodes()`、`snapshotFingerprint()`（它们只服务已删的复合动作）。
3. `ExecResult` 的 `atEnd` 字段保留（协议暂留，YAGNI）；`companion object` 里 `SETTLE_MS`/`MAX_PAGES` 若无其他引用一并删除。
4. 类顶注释里关于「桌面翻屏算子/负一屏 hack」的段落删除，改一句「端侧为哑执行器，只做原子动作，归位判定在云端」。
5. `import android.util.Log` 若不再使用则删除。

### Task 2.3 — 编译校验 + commit（提交点 2）

验证：
```
cd android && ./gradlew :app:compileDebugKotlin testDebugUnitTest
```
预期：编译通过、无 HomeDetector/ScreenFingerprint 残余引用、剩余端侧单测全绿。

commit：`refactor(android): 删除端侧土法归位逻辑，退化为哑执行器`

---

## 提交点 3：云端接入 scene 状态机 + 收敛守卫 + 三级脱困

### Task 3.1 — scene.py 顶部加守卫常量

在 `server/app/scene.py` 的 import 之后、`Scene` 枚举之前插入：
```python
# ==== 收敛守卫常量（可调）====
STALL_THRESHOLD = 3       # 连续同 scene 同 op 判停滞
CYCLE_THRESHOLD = 2       # 非目标 scene 在窗口内重复次数判振荡
WINDOW = 6                # scene_history 窗口长度
LLM_ESCALATION_TRIES = 1  # 给 LLM 几次脱困机会
FALLBACK_TRIES = 2        # 机械降级动作尝试次数
```

验证：`cd server && .venv/bin/python -c "import app.scene as s; print(s.STALL_THRESHOLD, s.WINDOW)"` → `3 6`

### Task 3.2 — scene.py 加 `_FALLBACK` 表 + `fallback_action()`（RED→GREEN）

先在 `test_scene.py` 末尾加测试：
```python
def test_fallback_action_minus_one_tries_home():
    from app.scene import fallback_action
    act = fallback_action(Scene.MINUS_ONE, Scene.HOME)
    assert act is not None and act.op == "home"  # 主动作 swipe right 失效后的备选


def test_fallback_action_unknown_scene_returns_home():
    from app.scene import fallback_action
    act = fallback_action(Scene.UNKNOWN, Scene.HOME)
    assert act is not None and act.op == "home"


def test_fallback_action_already_at_target_none():
    from app.scene import fallback_action
    assert fallback_action(Scene.HOME, Scene.HOME) is None
```
跑 → RED（`ImportError`）。

在 `scene.py` `next_action` 之后加：
```python
# 机械降级备选表：主转移动作失效时的次选动作（每个非目标 scene 至少一个）。
_FALLBACK: dict[tuple["Scene", "Scene"], tuple[str, dict]] = {
    (Scene.MINUS_ONE, Scene.HOME): ("home", {}),          # swipe right 失效 -> 按 home 键
    (Scene.RECENT_APPS, Scene.HOME): ("back", {}),        # home 键失效 -> back
    (Scene.NOTIFICATION, Scene.HOME): ("home", {}),
    (Scene.CONTROL_CENTER, Scene.HOME): ("home", {}),
    (Scene.IN_APP, Scene.HOME): ("home", {}),
}


def fallback_action(current: "Scene", target: "Scene") -> Optional[Action]:
    """机械降级备选动作；已在 target 返回 None，无备选时默认按 home 键兜底。"""
    if current == target:
        return None
    op, params = _FALLBACK.get((current, target), ("home", {}))
    return Action(actionId=str(uuid.uuid4()), op=op, params=dict(params))
```
跑 → GREEN。

验证：`cd server && .venv/bin/python -m pytest tests/test_scene.py -q`（原 20 + 新 3 全绿）

### Task 3.3 — Session 加 guard 字段

改 `server/app/session.py` 的 `Session.__init__`，末尾加：
```python
        # per-task 收敛守卫状态；task 生命周期内原地更新，随 Session 销毁。
        self.guard: dict = {
            "scene_history": [],   # 最近 WINDOW 帧 scene 值（str）
            "stall_count": 0,
            "last_op": "",
            "escalation_level": 0,  # 0=正常 / 1=已问 LLM 脱困 / 2=已机械降级
        }
```

验证：`cd server && .venv/bin/python -c "from app.session import Session; s=Session('t','g','d'); print(s.guard['escalation_level'])"` → `0`

### Task 3.4 — decision.py 接入 scene 状态机（2 个 RED 转绿）

改 `server/app/decision.py`：

1. 顶部 import：
```python
from app.scene import (
    Scene, detect_scene, next_action, fallback_action,
    STALL_THRESHOLD, CYCLE_THRESHOLD, WINDOW, LLM_ESCALATION_TRIES, FALLBACK_TRIES,
)
```
2. `decide()` 签名加参数（默认 None，保持既有调用兼容）：
```python
        target_pkg: str = "",
        guard: dict | None = None,
```
3. 把原 pkg guard 段（约 200-208 行 `home_first_page` 那段）替换为调用一个新的私有方法 `self._pkg_guard_action(perception, target_pkg, guard)`，返回 `list[Action] | None`（None 表示不触发 guard，继续走 LLM）：
```python
        guarded = self._pkg_guard_action(perception, target_pkg, guard)
        if guarded is not None:
            return guarded
```
4. 新增 `_pkg_guard_action`（先只做「Level 0 正常收敛」，让 2 个 RED 转绿）：
```python
    def _pkg_guard_action(
        self, perception: Perception, target_pkg: str, guard: dict | None
    ) -> list[Action] | None:
        if not (target_pkg and perception.pkg and perception.pkg != target_pkg):
            return None
        current = detect_scene(perception)
        action = next_action(current, Scene.HOME)
        if action is None:  # 已在 HOME，放行给正常任务决策
            return None
        _diag = logging.getLogger("phoneagent.gateway")
        _diag.info(
            "[PKG_GUARD] scene=%s target_pkg=%s -> op=%s",
            current.value, target_pkg, action.op,
        )
        return [action]
```

先跑 → 2 个原 RED（minus_one/recent_apps）转 GREEN；`test_pkg_guard_forces_home_first_when_current_pkg_mismatches`（通知横幅场景）此时 scene=UNKNOWN → `next_action` 兜底仍是 `home_first_page`，保持绿；`test_pkg_guard_in_app_still_home_first_page` 保持绿。

验证：`cd server && .venv/bin/python -m pytest tests/test_decision.py -q -k pkg_guard`（全绿）

### Task 3.5 — 停滞检测（RED→GREEN）

在 `test_decision.py` 末尾加停滞测试：
```python
def test_pkg_guard_stall_escalates_to_llm(monkeypatch):
    # 连续 STALL_THRESHOLD 帧同 scene 同 op（UNKNOWN 反复 home_first_page 无效）
    # -> 触发 LLM 脱困，escalation_level 置 1。
    from app.session import Session
    from app.scene import STALL_THRESHOLD
    calls = {"n": 0}

    def _escape(system, user, image_b64=None):
        calls["n"] += 1
        return "target_scene: HOME"

    llm = FakeLLM(["x"])
    monkeypatch.setattr(llm, "complete", _escape)
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    sess = Session("t", "打开飞书给张三发消息", "d")
    p = Perception(nodeTree=[Node(id="n1", text="未知界面")],
                   pkg="com.tencent.mm", activity="X", ts=1)
    for _ in range(STALL_THRESHOLD + 1):
        engine.decide(goal=sess.goal, perception=p, skill_name=None, cursor=0,
                      history=[], target_pkg="com.ss.android.lark", guard=sess.guard)
    assert calls["n"] >= 1
    assert sess.guard["escalation_level"] >= 1
```
跑 → RED。

在 `_pkg_guard_action` 里补收敛守卫（在算出 `current`/`action` 后、return 前）：
```python
        op = action.op
        # 停滞：相邻两帧 (scene, op) 相同则累加
        gd = guard if guard is not None else {}
        key = f"{current.value}|{op}"
        if gd.get("last_op") == key:
            gd["stall_count"] = gd.get("stall_count", 0) + 1
        else:
            gd["stall_count"] = 0
        gd["last_op"] = key
        # scene_history 滑窗
        hist = gd.setdefault("scene_history", [])
        hist.append(current.value)
        if len(hist) > WINDOW:
            del hist[0]
        stalled = gd["stall_count"] >= STALL_THRESHOLD
        oscillating = (
            current != Scene.HOME
            and hist.count(current.value) >= CYCLE_THRESHOLD + 1
        )
        if (stalled or oscillating) and gd.get("escalation_level", 0) == 0:
            gd["escalation_level"] = 1
            return self._llm_escape(perception, current, Scene.HOME, gd)
        return [action]
```
并新增 `_llm_escape`（Task 3.6 完善解析）：
```python
    def _llm_escape(self, perception, current, target, guard) -> list[Action]:
        raw = self._llm.complete(
            system=_ESCAPE_PROMPT,
            user=json.dumps({
                "current_scene": current.value,
                "target_scene": target.value,
                "scene_history": guard.get("scene_history", []),
            }, ensure_ascii=False),
        )
        new_target = _parse_target_scene(raw) or target
        act = next_action(current, new_target) or next_action(current, Scene.HOME)
        return [act] if act else [Action(actionId=str(uuid.uuid4()), op="home", params={})]
```
跑 → GREEN。

验证：`cd server && .venv/bin/python -m pytest tests/test_decision.py::test_pkg_guard_stall_escalates_to_llm -q`

### Task 3.6 — `target_scene` 解析 + 脱困 prompt（RED→GREEN）

在 `test_decision.py` 加：
```python
def test_parse_target_scene():
    from app.decision import _parse_target_scene
    from app.scene import Scene
    assert _parse_target_scene("target_scene: HOME") == Scene.HOME
    assert _parse_target_scene("target_scene:home") == Scene.HOME
    assert _parse_target_scene("blah") is None
    assert _parse_target_scene("target_scene: NOPE") is None
```
跑 → RED。

在 `decision.py` 加纯函数与 prompt 常量：
```python
_ESCAPE_PROMPT = """你正在帮一个手机操作代理脱困。它想收敛到某个屏幕场景（target_scene），\
但在几个场景之间兜圈或原地卡住（见 scene_history）。请只输出一行：\
`target_scene: X`，X 取值 HOME / MINUS_ONE / IN_APP 之一，表示接下来先去哪个场景。\
不要输出任何解释。"""


def _parse_target_scene(text: str) -> "Scene | None":
    for line in (text or "").splitlines():
        line = line.strip()
        if line.lower().startswith("target_scene:"):
            val = line.split(":", 1)[1].strip().upper()
            try:
                return Scene[val]
            except KeyError:
                return None
    return None
```
跑 → GREEN。

验证：`cd server && .venv/bin/python -m pytest tests/test_decision.py::test_parse_target_scene -q`

### Task 3.7 — 振荡检测测试（GREEN 覆盖）

在 `test_decision.py` 加振荡测试（逻辑已在 3.5 落地，此测试锁行为）：
```python
def test_pkg_guard_oscillation_escalates_to_llm(monkeypatch):
    # HOME↔MINUS_ONE 来回横跳 -> 命中振荡 -> 走 LLM 脱困。
    from app.session import Session
    seen = {"n": 0}
    llm = FakeLLM(["x"])
    monkeypatch.setattr(llm, "complete",
                        lambda *a, **k: (seen.__setitem__("n", seen["n"] + 1), "target_scene: HOME")[1])
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    sess = Session("t", "打开飞书", "d")
    minus = Perception(nodeTree=[Node(id="n1",
             viewIdResourceName="com.android.launcher:id/workspace", bounds=(43, 95, 1037, 2279))],
             pkg="com.android.launcher", activity="L", ts=1)
    for _ in range(4):
        engine.decide(goal=sess.goal, perception=minus, skill_name=None, cursor=0,
                      history=[], target_pkg="com.ss.android.lark", guard=sess.guard)
    assert seen["n"] >= 1
```
跑 → GREEN。若红，回到 3.5 校准振荡判据（`hist.count >= CYCLE_THRESHOLD + 1`，注意 MINUS_ONE 主动作 swipe right 也算同 op 停滞，两条件择一命中即可）。

验证：`cd server && .venv/bin/python -m pytest tests/test_decision.py::test_pkg_guard_oscillation_escalates_to_llm -q`

### Task 3.8 — 机械降级 + abort（RED→GREEN）

在 `test_decision.py` 加：
```python
def test_pkg_guard_level2_mechanical_fallback(monkeypatch):
    # escalation_level 已达 1、LLM 脱困后仍卡 -> Level 2 机械降级用 fallback_action。
    from app.session import Session
    llm = FakeLLM(["target_scene: HOME"])
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    sess = Session("t", "打开飞书", "d")
    sess.guard["escalation_level"] = 1
    sess.guard["stall_count"] = 99  # 已判停滞
    sess.guard["last_op"] = "minus_one|swipe"
    minus = Perception(nodeTree=[Node(id="n1",
             viewIdResourceName="com.android.launcher:id/workspace", bounds=(43, 95, 1037, 2279))],
             pkg="com.android.launcher", activity="L", ts=1)
    actions = engine.decide(goal=sess.goal, perception=minus, skill_name=None, cursor=0,
                            history=[], target_pkg="com.ss.android.lark", guard=sess.guard)
    assert actions[0].op == "home"  # MINUS_ONE 的 _FALLBACK 备选
    assert sess.guard["escalation_level"] == 2
```
跑 → RED。

在 `_pkg_guard_action` 的守卫段扩展 Level 1→2 分支（替换 3.5 里的 escalation 判定块）：
```python
        if stalled or oscillating:
            lvl = gd.get("escalation_level", 0)
            if lvl == 0:
                gd["escalation_level"] = 1
                return self._llm_escape(perception, current, Scene.HOME, gd)
            if lvl == 1:
                gd["escalation_level"] = 2
                fb = fallback_action(current, Scene.HOME)
                if fb is not None:
                    return [fb]
            # lvl >= 2：机械降级仍卡 -> abort
            return [Action(actionId=str(uuid.uuid4()), op="abort",
                           params={"reason": f"pkg_guard_stuck:{current.value}"})]
        return [action]
```
跑 → GREEN。

再加 abort 测试：
```python
def test_pkg_guard_level2_exhausted_aborts(monkeypatch):
    from app.session import Session
    llm = FakeLLM(["target_scene: HOME"])
    engine = DecisionEngine(llm=llm, skills=SkillLibrary())
    sess = Session("t", "打开飞书", "d")
    sess.guard["escalation_level"] = 2
    sess.guard["stall_count"] = 99
    sess.guard["last_op"] = "unknown|home_first_page"
    p = Perception(nodeTree=[Node(id="n1", text="未知")], pkg="com.tencent.mm", activity="X", ts=1)
    actions = engine.decide(goal=sess.goal, perception=p, skill_name=None, cursor=0,
                            history=[], target_pkg="com.ss.android.lark", guard=sess.guard)
    assert actions[0].op == "abort"
    assert "pkg_guard_stuck" in actions[0].params["reason"]
```
跑 → GREEN。

验证：`cd server && .venv/bin/python -m pytest tests/test_decision.py -q -k "level2"`

### Task 3.9 — gateway 传入 guard + commit（提交点 3）

改 `server/app/gateway.py:334` 的 `engine.decide(...)` 调用，加一行 `guard=session.guard,`。

验证（全量云端回归）：
```
cd server && .venv/bin/python -m pytest tests/test_decision.py tests/test_scene.py -q
```
预期：全绿（`test_skill_hit_without_llm` 那个既有无关失败若仍红，单独记录、不在本提交点范围）。

commit：`feat(server): pkg guard 接入 scene 状态机 + 收敛守卫 + 三级脱困`

---

## 提交点 4：LLM 提示词改造 + 协议 op 收窄

### Task 4.1 — `_NOARG_OPS` 移除 home_first / next_page（RED→GREEN）

在 `test_decision.py` 改/加：
```python
def test_parse_actions_home_first_and_next_page_no_longer_mapped():
    # 复合 op 已废弃：home_first / next_page 不再解析为动作（跳过）。
    assert parse_actions("home_first") == []
    assert parse_actions("next_page") == []
```
注意：原 `test_parse_actions_alias_mapping` 断言 `home_first -> home_first_page`、`test_decide_returns_action_list`/`test_decide_stops_batch_at_first_tap` 用到 `home_first`/`next_page` —— **这些用例需同步改写**为不含废弃 op 的等价流程（如用 `swipe`/`read` 替代）。逐个改断言。

跑 → RED。

改 `decision.py` 的 `_NOARG_OPS`，删两项：
```python
_NOARG_OPS = {
    "back": "back",
    "home": "home",
    "read": "read_screen",
    "done": "done",
}
```
跑 → GREEN（含被改写的原用例）。

验证：`cd server && .venv/bin/python -m pytest tests/test_decision.py -q -k "parse_actions or decide_"`

### Task 4.2 — `_SYSTEM_PROMPT` 移除废弃 op 指令

改 `decision.py` 的 `_SYSTEM_PROMPT`：
- 删掉 `home_first` / `next_page` 两条指令行；
- 删「打开应用的流程」里 `home_first`/`next_page`/`atEnd` 相关步骤，改为「回桌面用 `home`，找不到图标用 `swipe left` 翻屏」；
- 「跑错应用」示例把 `home_first` 改为 `home`。

保留既有断言用例（`test_fallback_to_llm_when_skill_miss` 要求 system 含 tap/input/swipe/done/abort/read）——确认这些词仍在。

验证：`cd server && .venv/bin/python -m pytest tests/test_decision.py -q`（全绿，除既有无关失败）

### Task 4.3 — protocol.py 收窄 Action.op Literal（RED→GREEN）

在 `server/tests/` 找 protocol 测试（若无则在 `test_decision.py` 加）：
```python
def test_action_op_rejects_deprecated_ops():
    import pytest
    from app.protocol import Action
    for dead in ("home_first_page", "next_page"):
        with pytest.raises(Exception):
            Action(actionId="x", op=dead)
```
跑 → RED。

改 `server/app/protocol.py` 的 `Action.op` Literal，删 `"home_first_page"` 与 `"next_page"` 两个取值。

⚠️ 先全局搜确认云端无其他地方构造这两个 op：
```
cd server && grep -rn "home_first_page\|next_page" app/
```
若 `scene.py._TRANSITIONS` 仍有 `(IN_APP, HOME): ("home_first_page", ...)` —— 需一并改为原子 op（如 `("home", {})`），并同步 `test_scene.py` 对应断言与 `test_decision.py` 里 IN_APP/UNKNOWN 兜底断言（原 `home_first_page` → `home`）。

跑 → GREEN。

验证：`cd server && .venv/bin/python -m pytest tests/ -q`

### Task 4.4 — Messages.kt 注释更新 + commit（提交点 4）

改 `android/.../protocol/Messages.kt`：`DownAction` 无结构改动，只在注释里说明 op 集合已收窄（删 home_first_page/next_page）。若无注释则跳过纯代码改动。

端侧编译校验：`cd android && ./gradlew :app:compileDebugKotlin`

commit：`feat: LLM prompt 与协议 op 集合收窄（移除 home_first_page/next_page）`

---

## 提交点 5：全量回归 + 真机 e2e

### Task 5.1 — 云端全量回归

```
cd server && .venv/bin/python -m pytest -q
```
预期：本次 scope 全绿。`test_skill_hit_without_llm` 若仍红，确认它在重构前就红（`git stash` 前对比），作为**既有 issue** 记录进 commit message，不阻塞。

### Task 5.2 — 端侧全量单测 + 编译

```
cd android && ./gradlew testDebugUnitTest :app:assembleDebug
```
预期：全绿、APK 构建成功、无 HomeDetector/ScreenFingerprint/home_first_page/next_page 残余。

### Task 5.3 — 真机 e2e 验证（激活 device-verification-rules skill）

装 APK，跑「打开飞书给张三发消息」，在跑错 app / 负一屏 / 最近任务场景下验证：
- 云端逐帧下发原子动作（日志 `[PKG_GUARD] scene=... -> op=...`）
- 负一屏 → `swipe right`、最近任务 → `home`，不再死循环
- 卡死场景观察 LLM 脱困日志与最终收敛/abort

⚠️ 真机页面状态验证**必须**遵循 `device-verification-rules` skill（uiautomator dump / 采样确认当前页面）。

### Task 5.4 — commit（提交点 5）

commit：`test: 全量回归 + 真机 e2e 验证 scene 状态机收敛`

---

## Self-Review Checklist（执行完逐项核对）

- [ ] spec §4.1/§4.2/§4.3 停滞/振荡/三级脱困全部落地并有测试覆盖
- [ ] spec §4.4 五个常量在 `scene.py` 顶部、可调
- [ ] spec §5.1 四块土法逻辑（含测试文件）全删，Executor when 收窄
- [ ] spec §5.3 `atEnd` 暂留（YAGNI），DownAction/Perception 结构不变
- [ ] spec §6 三决策点：pkg guard 走 scene / 正常任务留具体 op / 脱困走 `target_scene`
- [ ] spec §6.2 `_NOARG_OPS` 删 home_first/next_page、新增 `_parse_target_scene`
- [ ] spec §10 `_FALLBACK` 表每个非目标 scene 至少一个备选
- [ ] 全局 grep 无 `home_first_page`/`next_page` 残余（云端 + 端侧）
- [ ] 无 placeholder / TODO / 未实现分支
- [ ] 命名/类型一致（guard dict key、Scene 枚举值、Action.op 取值）

---

## 执行方式（二选一，请用户拍板）

- **A. Subagent-Driven（推荐）**：按提交点 2→3→4→5 分派子任务，每个提交点一个子 agent 独立跑 TDD + commit，主 agent 串联审查。隔离性好、上下文干净。
- **B. Inline Execution**：在当前会话逐 Task 执行，实时可见每步红绿。

> ⚠️ 当前直接在 master 工作（feature 已删）。执行前建议先激活 `superpowers:using-git-worktrees` 建隔离 worktree，或至少新建 `feature/scene-state-machine` 分支，避免 master 长期挂 RED。