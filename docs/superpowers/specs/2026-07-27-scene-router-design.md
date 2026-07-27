# SceneRouter：决策链场景路由重构设计

- 日期：2026-07-27
- 状态：已确认，待实施
- 关联：`docs/superpowers/specs/2026-07-27-home-locate-guard-design.md`

## 背景与问题

真机首次验证 home_locate_guard 时暴露致命 bug：任务「打开飞书发消息」全程
**从未出现 `source=home_locate`**，桌面/负一屏的归位与找图标全被 pkg_guard
接管，最终因 `swipe right` 反复无效触发 LOOP_GUARD_ABORT (stuck_loop) 放弃。

### 根因（结构性，非代码 bug）

当前 `engine.decide()` 是一串扁平的 if-return 短路链：

```
cache → skill → pkg_guard → home_locate → llm
```

每个守卫靠「返回 None 就放行」隐式表达「这帧不归我管」。而
`pkg_guard_action` 与 `home_locate_action` **各自调用 `detect_scene`、各自
对 HOME/MINUS_ONE 场景主张管辖权**：

- `pkg_guard_action` 触发条件只看 `pkg != target_pkg`，对 MINUS_ONE 直接
  `next_action(MINUS_ONE, HOME)` = `swipe right` 并 return，短路了下游。
- `home_locate_action` 设计为在 HOME **和** MINUS_ONE 场景接管找图标。

两者职责重叠，边界靠「谁排在前 + 返回 None 的时机」这种脆弱的隐式约定维系。
pkg_guard 排在前面，于是桌面场景被它抢走，home_locate 永远走不到。

对通用 agent 来说，正确的抽象是：**先有一个权威的「当前处于哪个场景」判断，
再由场景显式决定走哪条决策路径**，而不是让每个守卫各自猜场景、抢着 return。

## 目标

- 消除 pkg_guard 与 home_locate 的场景管辖权冲突（修复真机 bug）。
- 让「场景 → 决策路径」成为**显式、唯一**的映射，不再依赖守卫排序。
- 保持端侧、协议零改动；保持 pkg_guard / home_locate 内部逻辑基本不变。

## 方案：方向 A + 独立 SceneRouter

`detect_scene` 已是全局唯一的场景真相源。将它升格为决策链调度中枢：
**入口只判一次场景，结果作为唯一真相分派到对应 handler。**

### 决策链新形态

```
decide():
  cache / skill            (不变，保持在最前)
    ↓
  scene = detect_scene(frame)   ← 只调用一次
    ↓
  route_by_scene(scene, ctx)    ← 新增中枢 (scene_router.py)
    ├─ HOME / MINUS_ONE                          → home_locate
    │     (无 aliases → home_locate 返回 None → 路由器返回 None → LLM 兜底)
    ├─ IN_APP 且 pkg == target                    → None (交 LLM)
    └─ 其余 (IN_APP 非目标 / NOTIFICATION /
             CONTROL_CENTER / RECENT_APPS /
             LOCK_SCREEN / UNKNOWN)               → pkg_guard 收敛回桌面
    ↓
  routed is None → self._llm_decide(d)
```

### 职责边界（修 bug 核心）

| 场景 | 归属 handler | 理由 |
|---|---|---|
| IN_APP 且 pkg == target | llm | 已到目标 App，正常任务决策 |
| IN_APP 且 pkg ≠ target | pkg_guard | 跑进别的 App，收敛回桌面 |
| NOTIFICATION / CONTROL_CENTER / RECENT_APPS / LOCK_SCREEN / UNKNOWN | pkg_guard | 系统界面 / 异常，收敛回桌面 |
| **HOME / MINUS_ONE** | **home_locate** | **桌面找图标的正确战场——本次 bug 就是被 pkg_guard 抢走了** |

**无 aliases 兜底**：目标 App 未配 aliases 时，home_locate 内部返回 None，
路由器随之返回 None，最终 fall-through 到 LLM——保留通用 agent 在桌面自行
找图标的灵活性，不再由 pkg_guard 做确定性归位（避免重新引入场景交叉）。

## 接口设计

### scene_router.py（新建，纯函数式）

依赖通过参数注入，避免循环依赖与长参数列表；**不依赖 Decision 类型**，
保持纯净，由 engine 组装 Decision（解耦）。

```python
@dataclass
class RouteContext:
    frame: Perception
    target_pkg: str
    aliases: list[str]
    guard: dict
    escape_llm: LLM

def route_by_scene(
    scene: Scene, ctx: RouteContext
) -> tuple[list[Action], DecisionSource] | None:
    """按场景分派到对应 handler。

    返回 (actions, source)：命中某个守卫。
    返回 None：fall-through，交给 LLM 决策。
    """
    if scene in (Scene.HOME, Scene.MINUS_ONE):
        located = home_locate_action(ctx.frame, ctx.target_pkg, ctx.aliases, ctx.guard)
        return (located, "home_locate") if located is not None else None
    if scene == Scene.IN_APP and ctx.frame.pkg == ctx.target_pkg:
        return None
    guarded = pkg_guard_action(ctx.frame, ctx.target_pkg, ctx.guard, ctx.escape_llm)
    return (guarded, "pkg_guard") if guarded is not None else None
```

### engine.decide 收敛

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

## 数据流

- `detect_scene(frame)` 在路由器入口调用一次，作为唯一场景真相。
- `guard` dict 由 pkg_guard（`stall_count` / `scene_history` / `escalation_level`）
  与 home_locate（`home_locate` 子字典）各自读写，key 不冲突，路由切换安全。
- source 语义准确：路由器显式返回，不再由 engine 按顺序推断。

## 测试策略

### 新增回归测试（复现真机 bug）

- engine：目标 App 有 aliases + MINUS_ONE → `source == "home_locate"`
  （当前错误地得到 pkg_guard——这是 bug 的直接断言）。
- engine：目标 App 有 aliases + HOME → `source == "home_locate"`。
- engine：无 aliases + HOME/MINUS_ONE → fall-through 到 llm。

### SceneRouter 单元测试（新模块）

- 每个场景 → 正确 handler 的分派断言。
- IN_APP 且 pkg == target → 返回 None（交 LLM）。
- IN_APP 且 pkg ≠ target → 走 pkg_guard。
- HOME/MINUS_ONE 且 home_locate 返回 None → 路由器返回 None。

### 现有测试迁移（主要风险点）

pkg_guard 现有测试中「HOME/MINUS_ONE 收敛」相关用例语义变了——那两个场景
不再路由给 pkg_guard。需逐个评估：删除、或迁移到 home_locate / router 层。

### 全量回归

现有 419 passed 必须保持绿（迁移后总数可能变动，因用例归属调整）。

## 迁移风险

1. **pkg_guard 桌面用例**：`_TRANSITIONS[(MINUS_ONE, HOME)]`、`_FALLBACK` 等
   与桌面相关的分支在新路由下不再被触达。**保留 pkg_guard 内部逻辑不删**
   （防其他路径复用 / 降低改动风险），仅在路由层不再把桌面场景分给它。
2. **guard 状态**：确认 pkg_guard 与 home_locate 的 guard key 无冲突（已分析
   无冲突，需测试兜底）。

## 真机复验

- 服务端以 `nohup` 后台运行（避免终端信号杀进程）。
- 复验目标：负一屏 / 桌面场景下出现 `source=home_locate`，找到飞书图标并 tap 进入。
- 确认页面唯一合法手段：本 App 无障碍采样（`sample.capture` → `server/data/samples/*.json`
  + logcat `↑ sample.capture`）。**禁用** uiautomator dump / 截图 / screencap。

## 非目标（YAGNI）

- 不引入守卫协议 / applies_to 优先级链（当前仅三条路径，过度设计）。
- 不合并 pkg_guard 与 home_locate 为单一状态机（改动大、关注点耦合）。
- 不改动端侧、协议、感知采样格式。