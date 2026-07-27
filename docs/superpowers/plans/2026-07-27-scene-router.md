# SceneRouter 实施计划：决策链场景路由重构

- 日期：2026-07-27
- 状态：待执行
- 关联 spec：docs/superpowers/specs/2026-07-27-scene-router-design.md
- 关联根因：pkg_guard 在 HOME/MINUS_ONE 场景抢先 return，短路 home_locate

## 目标与约束

把 `engine.decide()` 里 `pkg_guard → home_locate` 的扁平短路链，
收敛为「先判一次场景，按场景显式分派」的 `route_by_scene()` 路由。
彻底修复 home_locate 被 pkg_guard 短路的真机 bug。

- 严格 TDD：每个任务先写失败测试，再写实现，最后全绿。
- 复用现有测试模式：engine 层用 `DecideInput`/`FakeLLM`/`DecisionEngine`；
  场景构造复用 test_home_locate 的 `_home`/`_minus_one`。
- 非目标（YAGNI）：不引入守卫协议/applies_to；不合并 pkg_guard+home_locate；不改端侧/协议。

## 职责边界（route_by_scene 的唯一真相）

| 场景 | handler | 返回 |
|---|---|---|
| HOME / MINUS_ONE | home_locate | 命中→(actions,"home_locate")；无aliases/None→None（回落LLM）|
| IN_APP 且 pkg==target | —— | None（回落LLM）|
| IN_APP 非目标 / NOTIFICATION / CONTROL_CENTER / RECENT_APPS / LOCK_SCREEN / UNKNOWN | pkg_guard | 命中→(actions,"pkg_guard")；None→None |

---

## Task 1：新建 scene_router.py（纯函数路由 + RouteContext）

**先写测试** `server/tests/test_scene_router.py`：
- `test_home_scene_routes_to_home_locate`：HOME 场景 + 有 aliases + 无图标 → 返回 `(actions, "home_locate")`，actions[0].op=="swipe"。
- `test_minus_one_routes_to_home_locate`：MINUS_ONE 场景 → 返回 `(_, "home_locate")`。
- `test_home_scene_no_aliases_returns_none`：HOME + aliases=[] → 返回 None（回落 LLM）。
- `test_in_app_target_returns_none`：IN_APP 且 pkg==target → None。
- `test_in_app_non_target_routes_to_pkg_guard`：IN_APP 且 pkg!=target（用 `_stuck_frame` 语义）→ `(_, "pkg_guard")`。
- `test_notification_routes_to_pkg_guard`：NOTIFICATION 场景 → `(_, "pkg_guard")`。

场景构造复用 test_home_locate 的 `_home(nodes)` / `_minus_one()`。
`RouteContext` 用 `FakeLLM` 充当 escape_llm。

**再写实现** `server/app/decision/scene_router.py`：
```python
from __future__ import annotations
from dataclasses import dataclass
from app.decision.home_locate import home_locate_action
from app.decision.pkg_guard import Scene, pkg_guard_action
from app.decision.llm import LLM
from app.decision.types import Action, DecisionSource
from app.protocol import Perception

@dataclass
class RouteContext:
    frame: Perception
    target_pkg: str
    aliases: list[str]
    guard: dict
    escape_llm: LLM

def route_by_scene(
    scene: Scene, ctx: RouteContext,
) -> tuple[list[Action], DecisionSource] | None:
    if scene in (Scene.HOME, Scene.MINUS_ONE):
        located = home_locate_action(ctx.frame, ctx.target_pkg, ctx.aliases, ctx.guard)
        return (located, "home_locate") if located is not None else None
    if scene == Scene.IN_APP and ctx.frame.pkg == ctx.target_pkg:
        return None
    guarded = pkg_guard_action(ctx.frame, ctx.target_pkg, ctx.guard, ctx.escape_llm)
    return (guarded, "pkg_guard") if guarded is not None else None
```

**验证**：`uv run pytest tests/test_scene_router.py -q` 全绿。

---

## Task 2：engine.decide 接入 route_by_scene（含复现 bug 的回归测试）

**先写/改测试** `server/tests/test_engine.py`：
- 新增 `test_decide_minus_one_reaches_home_locate_not_shortcircuited`（复现 bug 的核心回归）：
  MINUS_ONE 场景 + 目标飞书有 aliases + pkg!=target → `d.source == "home_locate"`（原 bug 下会是 pkg_guard swipe right）。
- 保留 `test_decide_home_locate_wired_after_pkg_guard_before_llm`（L792）：HOME → home_locate，应继续通过。
- 检查 `test_pkg_guard_stall_escalates_to_llm_level1`（L414）等：`_stuck_frame()` 是 IN_APP 非目标 → 走 pkg_guard 分支，source 仍为 pkg_guard，应继续通过（若失败进 Task 3 迁移）。

**再改实现** `server/app/decision/engine.py`（L420-431 收敛）：
```python
scene = detect_scene(d.frame)
profile = _ui_profile_for_pkg(d.target_pkg)
aliases = profile.aliases if profile else []
ctx = RouteContext(d.frame, d.target_pkg, aliases, d.guard, self._escape_llm)
routed = route_by_scene(scene, ctx)
if routed is not None:
    actions, source = routed
    return Decision(actions=actions, source=source)
return self._llm_decide(d)
```
- 顶部 import：`from app.decision.scene_router import RouteContext, route_by_scene`。
- 移除 L420-429 旧的 `pkg_guard_action` / `home_locate_action` 直调块。
- `pkg_guard_action` / `home_locate_action` 的直接 import 若仅此处用则清理。

**验证**：`uv run pytest tests/test_engine.py -q` 全绿。

---

## Task 3：迁移 pkg_guard 桌面场景测试用例（主要风险点）

pkg_guard 现有测试中若有构造 HOME/MINUS_ONE 帧并断言 `source=="pkg_guard"` 的用例，
语义已变更（桌面场景现归 home_locate）。逐个处理：
- grep `test_engine.py`/`test_pkg_guard*.py` 中 workspace bounds / Scene.HOME / Scene.MINUS_ONE 构造的用例。
- 若断言的是 pkg_guard 的桌面归位行为 → 改为断言 home_locate，或改用 IN_APP 非目标帧保留 pkg_guard 语义。
- pkg_guard 内部逻辑与单测（`test_pkg_guard.py` 若存在）保持不动：只删路由层的桌面分派，不删 pkg_guard 能力。

**验证**：相关测试文件全绿，无语义漂移遗留。

---

## Task 4：全量回归 + 真机复验

- `cd server && uv run pytest -q` → 419（或当前基线数）全 passed。
- 真机复验（铁律：只用本 App 无障碍采样，禁 uiautomator/截图/screencap）：
  1. nohup 启动服务端：`nohup uv run uvicorn app.main:create_app --host 0.0.0.0 --port 8000 --factory > logs/uvicorn.out 2>&1 &`
  2. 手机在负一屏/桌面触发「打开飞书」→ 观察 logcat 出现 `source=home_locate`，动作为找飞书图标 tap / 翻页 swipe。
  3. 无障碍采样 sample.capture 落盘 server/data/samples/*.json 确认页面。
- 验收标准：日志中桌面场景出现 `source=home_locate`（不再是 pkg_guard 反复 swipe right → LOOP_GUARD_ABORT）。

---

## 执行方式（Task 全部就绪后由用户选择）

- 推荐 subagent-driven：每个 Task 派一个子 agent TDD 执行 + 回归。
- 或 inline executing-plans：主线程逐 Task red-green-refactor。