# 桌面找图标守卫（home_locate_guard）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在桌面场景用纯云端确定性逻辑找目标 app 图标（找到 tap / 没找到自动翻页 / 翻到底 abort），根治 LLM 桌面乱点导致的 pkg_guard_stuck 卡死。

**Architecture:** 新增纯逻辑模块 `home_locate.py`（可单测），在 `engine.decide` 的 `pkg_guard_action` 之后、`_llm_decide` 之前插入守卫。端侧、协议零改动，复用现有 `swipe(direction)`、`tap(match_text)`、`detect_scene`、`AppProfile.aliases`。

**Tech Stack:** Python 3 / pydantic / pytest；uv 管理依赖（`cd server && uv run pytest`）。

设计文档：`docs/superpowers/specs/2026-07-27-home-locate-guard-design.md`

---

## File Structure

- **Create** `server/app/decision/home_locate.py` — 桌面找图标守卫的全部纯逻辑：`_screen_icon_fingerprint`、`find_icon`、`home_locate_action`。单一职责，可独立单测。
- **Modify** `server/app/decision/engine.py` — `decide()` 内接线（约 line 419 之后）。
- **Create** `server/tests/test_home_locate.py` — 纯函数与状态机单测。
- **Modify** `server/tests/test_engine.py` — 接线单测（1 条：pkg_guard 放行后进 home_locate）。

关键既有 API（已核对）：
- `Perception(pkg=str, nodeTree=list[Node])`；`Node(id, text, desc, viewIdResourceName, bounds)`。
- `Action(actionId=str, op=str, params=dict)`；abort 用 `op="abort", params={"reason": ...}`。
- `detect_scene(perception) -> Scene`；`Scene.HOME` / `Scene.MINUS_ONE`（`app.decision.pkg_guard`）。
- `_ui_profile_for_pkg(pkg) -> AppProfile | None`（`engine.py:34`），`AppProfile.aliases: list[str]`。

---

## Task 1: 图标文案指纹 `_screen_icon_fingerprint`

**Files:**
- Create: `server/app/decision/home_locate.py`
- Test: `server/tests/test_home_locate.py`

- [ ] **Step 1: 写失败测试**

```python
# server/tests/test_home_locate.py
from __future__ import annotations

from app.decision.home_locate import _screen_icon_fingerprint, find_icon, home_locate_action
from app.protocol import Node, Perception


def _home(nodes: list[Node]) -> Perception:
    # launcher workspace 全屏 bounds=[0,0,...] → detect_scene 判 HOME
    ws = Node(id="ws", viewIdResourceName="com.coloros.launcher:id/workspace", bounds=(0, 0, 1080, 2400))
    return Perception(pkg="com.coloros.launcher", nodeTree=[ws, *nodes])


def test_fingerprint_ignores_order_and_dedup():
    a = [Node(id="1", text="飞书"), Node(id="2", text="微信")]
    b = [Node(id="3", text="微信"), Node(id="4", text="飞书"), Node(id="5", text="")]
    assert _screen_icon_fingerprint(a) == _screen_icon_fingerprint(b)


def test_fingerprint_differs_when_icon_added():
    a = [Node(id="1", text="飞书")]
    b = [Node(id="1", text="飞书"), Node(id="2", text="微信")]
    assert _screen_icon_fingerprint(a) != _screen_icon_fingerprint(b)
```

- [ ] **Step 2: 运行验证失败**

Run: `cd server && uv run pytest tests/test_home_locate.py -v`
Expected: FAIL（`ModuleNotFoundError: app.decision.home_locate` 或 import error）

- [ ] **Step 3: 写最小实现**

```python
# server/app/decision/home_locate.py
"""桌面找图标守卫（纯云端确定性）。

设计: docs/superpowers/specs/2026-07-27-home-locate-guard-design.md
HOME 场景且未进目标 app 时接管:找图标 tap / 归位 / 逐屏扫描 / 到底 abort。
LLM 桌面阶段不参与。端侧、协议零改动。
"""
from __future__ import annotations

import uuid

from app.decision.pkg_guard import Scene, detect_scene
from app.protocol import Action, Node, Perception


def _screen_icon_fingerprint(nodes: list[Node]) -> frozenset[str]:
    """取所有节点非空 text/desc(strip)组成的集合指纹,判翻页到底。"""
    out: set[str] = set()
    for n in nodes:
        for raw in (n.text, n.desc):
            if raw and raw.strip():
                out.add(raw.strip())
    return frozenset(out)
```

- [ ] **Step 4: 运行验证通过**

Run: `cd server && uv run pytest tests/test_home_locate.py -v`
Expected: PASS（2 条指纹测试通过；find_icon/home_locate_action 相关 import 已在，函数下一 Task 补）

注：Step 1 的 import 引用了尚未实现的 `find_icon`/`home_locate_action`。为让本 Task 可独立跑通，import 保留但对应测试在 Task 2/3 添加；本步骤只运行指纹两条：
Run: `cd server && uv run pytest tests/test_home_locate.py -k fingerprint -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/app/decision/home_locate.py server/tests/test_home_locate.py
git commit -m "feat(server): home_locate 图标文案指纹(纯函数)"
```

---

## Task 2: 图标匹配 `find_icon`

**Files:**
- Modify: `server/app/decision/home_locate.py`
- Test: `server/tests/test_home_locate.py`

- [ ] **Step 1: 写失败测试**（追加到 test_home_locate.py 末尾）

```python
def test_find_icon_hit_exact():
    nodes = [Node(id="1", text="微信"), Node(id="2", text="飞书")]
    hit = find_icon(nodes, ["飞书", "feishu", "lark"])
    assert hit is not None and hit.text == "飞书"


def test_find_icon_hit_by_desc_case_insensitive():
    nodes = [Node(id="1", desc="Lark")]
    hit = find_icon(nodes, ["飞书", "feishu", "lark"])
    assert hit is not None


def test_find_icon_miss_returns_none():
    nodes = [Node(id="1", text="微信"), Node(id="2", text="王者荣耀")]
    assert find_icon(nodes, ["飞书", "feishu", "lark"]) is None
```

- [ ] **Step 2: 运行验证失败**

Run: `cd server && uv run pytest tests/test_home_locate.py -k find_icon -v`
Expected: FAIL（`find_icon` 未定义 / 返回 None）

- [ ] **Step 3: 写最小实现**（追加到 home_locate.py，`_screen_icon_fingerprint` 之后）

```python
def find_icon(nodes: list[Node], aliases: list[str]) -> Node | None:
    """扫节点 text/desc,命中任一 alias 返回该节点;完全相等优先于包含。"""
    lowered = [a.strip().lower() for a in aliases if a.strip()]
    if not lowered:
        return None
    best_contains: Node | None = None
    for n in nodes:
        for raw in (n.text, n.desc):
            if not raw:
                continue
            label = raw.strip().lower()
            if not label:
                continue
            if label in lowered:
                return n  # 完全相等,立即命中
            if best_contains is None and any(a in label for a in lowered):
                best_contains = n
    return best_contains
```

- [ ] **Step 4: 运行验证通过**

Run: `cd server && uv run pytest tests/test_home_locate.py -k find_icon -v`
Expected: PASS（3 条）

- [ ] **Step 5: Commit**

```bash
git add server/app/decision/home_locate.py server/tests/test_home_locate.py
git commit -m "feat(server): home_locate 图标匹配 find_icon(相等优先/包含兜底)"
```

---

## Task 3: 状态机 `home_locate_action`

**Files:**
- Modify: `server/app/decision/home_locate.py`
- Test: `server/tests/test_home_locate.py`

- [ ] **Step 1: 写失败测试**（追加到 test_home_locate.py 末尾）

```python
def _minus_one() -> Perception:
    ws = Node(id="ws", viewIdResourceName="com.coloros.launcher:id/workspace", bounds=(40, 60, 1040, 2340))
    return Perception(pkg="com.coloros.launcher", nodeTree=[ws])


def test_fallback_empty_aliases_returns_none():
    frame = _home([Node(id="1", text="微信")])
    assert home_locate_action(frame, "com.ss.android.lark", [], {}) is None


def test_not_home_returns_none():
    frame = Perception(pkg="com.ss.android.lark", nodeTree=[])
    assert home_locate_action(frame, "com.ss.android.lark", ["飞书"], {}) is None


def test_already_in_target_returns_none():
    ws = Node(id="ws", viewIdResourceName="com.coloros.launcher:id/workspace", bounds=(0, 0, 1080, 2400))
    frame = Perception(pkg="com.ss.android.lark", nodeTree=[ws])
    assert home_locate_action(frame, "com.ss.android.lark", ["飞书"], {}) is None


def test_home_hit_icon_returns_tap():
    frame = _home([Node(id="1", text="飞书")])
    acts = home_locate_action(frame, "com.ss.android.lark", ["飞书", "lark"], {})
    assert acts and acts[0].op == "tap" and acts[0].params["match_text"] == "飞书"


def test_home_miss_homing_swipes_right():
    frame = _home([Node(id="1", text="微信")])
    guard: dict = {}
    acts = home_locate_action(frame, "com.ss.android.lark", ["飞书"], guard)
    assert acts and acts[0].op == "swipe" and acts[0].params["direction"] == "right"
    assert guard["home_locate"]["phase"] == "homing"


def test_minus_one_switches_to_scanning_swipe_left():
    guard = {"home_locate": {"phase": "homing", "last_fingerprint": [], "swipe_count": 1}}
    acts = home_locate_action(_minus_one(), "com.ss.android.lark", ["飞书"], guard)
    assert acts and acts[0].op == "swipe" and acts[0].params["direction"] == "left"
    assert guard["home_locate"]["phase"] == "scanning"


def test_scanning_fingerprint_same_aborts():
    # 上一屏指纹与当前屏一致 → 到底 → abort
    fp = sorted(["微信", "王者荣耀"])
    guard = {"home_locate": {"phase": "scanning", "last_fingerprint": fp, "swipe_count": 3}}
    frame = _home([Node(id="1", text="微信"), Node(id="2", text="王者荣耀")])
    acts = home_locate_action(frame, "com.ss.android.lark", ["飞书"], guard)
    assert acts and acts[0].op == "abort"
    assert acts[0].params["reason"].startswith("app_not_found")


def test_scanning_new_screen_swipes_left():
    guard = {"home_locate": {"phase": "scanning", "last_fingerprint": ["微信"], "swipe_count": 2}}
    frame = _home([Node(id="1", text="王者荣耀")])
    acts = home_locate_action(frame, "com.ss.android.lark", ["飞书"], guard)
    assert acts and acts[0].op == "swipe" and acts[0].params["direction"] == "left"


def test_swipe_count_over_limit_aborts():
    guard = {"home_locate": {"phase": "scanning", "last_fingerprint": ["x"], "swipe_count": 99}}
    frame = _home([Node(id="1", text="王者荣耀")])
    acts = home_locate_action(frame, "com.ss.android.lark", ["飞书"], guard)
    assert acts and acts[0].op == "abort"
```

- [ ] **Step 2: 运行验证失败**

Run: `cd server && uv run pytest tests/test_home_locate.py -k "home_locate or fallback or home_hit or home_miss or minus_one or scanning or swipe_count or not_home or already_in" -v`
Expected: FAIL（`home_locate_action` 未定义）

- [ ] **Step 3: 写最小实现**（追加到 home_locate.py 末尾）

```python
_MAX_SWIPE = 20  # 归位+扫描总上限,防双判据失效死翻


def _act(op: str, params: dict) -> Action:
    return Action(actionId=str(uuid.uuid4()), op=op, params=params)


def home_locate_action(
    perception: Perception,
    target_pkg: str,
    aliases: list[str],
    guard: dict,
) -> list[Action] | None:
    """桌面找图标守卫;不该介入返回 None(放行给后续 LLM 决策)。"""
    # fallback: 无匹配依据不介入
    if not aliases:
        return None
    # 已进目标 app / 非桌面场景 → 放行
    if perception.pkg == target_pkg:
        return None
    scene = detect_scene(perception)
    if scene not in (Scene.HOME, Scene.MINUS_ONE):
        return None

    st = guard.setdefault("home_locate", {"phase": "homing", "last_fingerprint": [], "swipe_count": 0})

    # 安全上限兜底
    if st["swipe_count"] >= _MAX_SWIPE:
        return [_act("abort", {"reason": f"app_not_found:{aliases[0]}"})]

    # 归位阶段:滑到负一屏说明越过首屏 → 退回首屏,切扫描
    if st["phase"] == "homing":
        if scene == Scene.MINUS_ONE:
            st["phase"] ="scanning"
            st["last_fingerprint"] = []
            st["swipe_count"] += 1
            return [_act("swipe", {"direction": "left"})]
        # 仍在 HOME:先找图标,命中即 tap
        hit = find_icon(perception.nodeTree, aliases)
        if hit is not None:
            guard.pop("home_locate", None)
            return [_act("tap", {"match_text": (hit.text or hit.desc or "").strip()})]
        st["swipe_count"] += 1
        return [_act("swipe", {"direction": "right"})]

    # 扫描阶段:先找图标
    hit = find_icon(perception.nodeTree, aliases)
    if hit is not None:
        guard.pop("home_locate", None)
        return [_act("tap", {"match_text": (hit.text or hit.desc or "").strip()})]
    # 指纹到底判定
    fp = _screen_icon_fingerprint(perception.nodeTree)
    if st["last_fingerprint"] and frozenset(st["last_fingerprint"]) == fp:
        return [_act("abort", {"reason": f"app_not_found:{aliases[0]}"})]
    st["last_fingerprint"] = sorted(fp)
    st["swipe_count"] += 1
    return [_act("swipe", {"direction": "left"})]
```

- [ ] **Step 4: 运行验证通过**

Run: `cd server && uv run pytest tests/test_home_locate.py -v`
Expected: PASS（全部，含 Task 1/2）

- [ ] **Step 5: Commit**

```bash
git add server/app/decision/home_locate.py server/tests/test_home_locate.py
git commit -m "feat(server): home_locate_guard 桌面找图标状态机(归位/扫描/abort)"
```

---

## Task 4: engine.decide 接线

**Files:**
- Modify: `server/app/decision/engine.py:419`
- Test: `server/tests/test_engine.py`

- [ ] **Step 1: 写失败测试**（追加到 test_engine.py 末尾；沿用该文件既有 Engine/DecideInput 构造夹具，若无则参考文件顶部 import）

```python
def test_home_locate_engages_when_home_and_wrong_pkg(engine, make_decide_input):
    # 桌面(launcher workspace 全屏) + 目标 lark 未进 + 无飞书图标 → 应下发 swipe right(归位)
    from app.protocol import Node
    ws = Node(id="ws", viewIdResourceName="com.coloros.launcher:id/workspace", bounds=(0, 0, 1080, 2400))
    frame = Perception(pkg="com.coloros.launcher", nodeTree=[ws, Node(id="1", text="微信")])
    d = make_decide_input(frame=frame, target_pkg="com.ss.android.lark", goal="打开飞书")
    dec = engine.decide(d)
    assert dec.source == "home_locate"
    assert dec.actions[0].op == "swipe"
```

注：`engine` / `make_decide_input` 复用 test_engine.py 现有 fixture。若现有 fixture 名不同，按文件内实际夹具改造（构造 `DecideInput(frame=, target_pkg=, guard={}, goal=, ...)`，`target_pkg` 必须是已注册 profile 的 pkg，飞书 `com.ss.android.lark` 已在 profiles）。

- [ ] **Step 2: 运行验证失败**

Run: `cd server && uv run pytest tests/test_engine.py -k home_locate -v`
Expected: FAIL（`dec.source` 为 `"llm"` 而非 `"home_locate"`——旧行为走 LLM）

- [ ] **Step 3a: 放开 DecisionSource Literal**（必做，否则 mypy 报错）

`server/app/decision/types.py:13` 现为：

```python
DecisionSource = Literal["cache", "skill", "pkg_guard", "llm"]
```

改为加入 `"home_locate"`：

```python
DecisionSource = Literal["cache", "skill", "pkg_guard", "home_locate", "llm"]
```

- [ ] **Step 3b: 接线实现**

在 `server/app/decision/engine.py` 顶部 import 区加：

```python
from app.decision.home_locate import home_locate_action
```

在 `decide()` 内 `pkg_guard_action` 分支之后、`return self._llm_decide(d)` 之前（约 line 421 后）插入：

```python
        guarded = pkg_guard_action(d.frame, d.target_pkg, d.guard, self._escape_llm)
        if guarded is not None:
            return Decision(actions=guarded, source="pkg_guard")

        # 桌面找图标守卫:HOME 且未进目标 app 时确定性找图标/翻页/abort(不问 LLM)
        profile = _ui_profile_for_pkg(d.target_pkg)
        aliases = profile.aliases if profile else []
        located = home_locate_action(d.frame, d.target_pkg, aliases, d.guard)
        if located is not None:
            return Decision(actions=located, source="home_locate")

        return self._llm_decide(d)
```

- [ ] **Step 4: 运行验证通过**

Run: `cd server && uv run pytest tests/test_engine.py -k home_locate -v`
Expected: PASS

- [ ] **Step 5: 全量回归**

Run: `cd server && uv run pytest -q`
Expected: 全绿（无回归）。类型检查：`cd server && uv run mypy app/decision/home_locate.py app/decision/engine.py app/decision/types.py`，Expected: 无 error（Step 3a 已放开 Literal）。

- [ ] **Step 6: Commit**

```bash
git add server/app/decision/engine.py server/app/decision/types.py server/tests/test_engine.py
git commit -m "feat(server): engine.decide 接线 home_locate(pkg_guard 后/LLM 前)"
```

---

## Self-Review

- **Spec 覆盖**：fallback(aliases 空放行)=Task3 test_fallback；找图标 tap=Task3 test_home_hit；归位 swipe right=test_home_miss；负一屏切扫描=test_minus_one；指纹到底 abort=test_scanning_fingerprint_same；swipe_count 上限=test_swipe_count_over_limit；接线=Task4。方向×判据(右滑负一屏/左滑指纹)已在状态机分支实现。✅
- **Placeholder 扫描**：无 TBD/TODO；所有 step 含完整代码与命令。✅
- **类型一致**：`home_locate_action(perception, target_pkg, aliases, guard)` 四参贯穿 Task3/4；`_screen_icon_fingerprint`/`find_icon` 签名一致；abort 用 `op="abort"` 与 pkg_guard 现有约定一致。✅

## 风险与联调项

- **`DecisionSource` Literal 已在 Task 4 Step 3a 放开**（加 `"home_locate"`）——非 pydantic 运行时不校验，但 mypy 必查，故列为必做步骤而非可选风险。
- **真机联调**（不写单测）：swipe direction=right/left 是否精确翻一屏、负一屏能否稳定判 MINUS_ONE、swipe 后端侧重抓帧的等待时间是否足够（指纹抖动）。改 engine/decision 后需重启 uvicorn。
- **`_MAX_SWIPE=20`** 为经验值，真机若首屏数多可调大。