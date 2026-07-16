# 屏幕场景状态机重构（阶段二） 设计

- 日期：2026-07-16
- 状态：设计已与用户对齐，待写实现计划
- 前置：`docs/superpowers/specs/2026-07-16-screen-scene-state-machine-design.md`（阶段一探针采样，已落地 8 份 fixtures）
- 关联问题：PKG_GUARD 死循环（`server/app/decision.py:200-208`）—— 无脑下发 `home_first_page`，端侧黑盒失败即兜圈

## 1. 背景与问题

阶段一（探针采样）已完成：8 份真机采样落盘 `server/tests/fixtures/scenes/*.json`，覆盖 home_first / home_other / minus_one / notification / control_center / in_target_app_lark / lock_screen / recent_apps。基于这些真帧，阶段二的场景识别规则也已落地——`server/app/scene.py` 的 `detect_scene()` 通过 8 场景全绿测试（11 个），`next_action()` 转移表通过 9 个转移测试（累计 20 全绿）。

但**决策链路尚未接入 scene 状态机**：
1. `decision.py:200-208` 仍是无脑 `home_first_page`，pkg 不匹配即兜圈；
2. 端侧 `Executor.homeFirstPage()` 是**黑盒复合动作**（内含 HOME + 循环翻页 + `ScreenFingerprint` 指纹判定 + 负一屏 hack），云端看不见中间态；
3. LLM 提示词教它输出具体 op（`home_first_page`/`next_page`/`tap` 等），语义层与执行层耦合；
4. 归位若失败无从降级，历史上表现为 PKG_GUARD 死循环。

## 2. 目标

把「归位」从端侧黑盒复合动作，重构为**云端逐帧驱动的显式状态机**：
- 端侧退化为哑执行器，只做原子动作；
- 云端持有 scene 状态机 + 转移表，逐帧感知场景并下发单个原子动作，直到收敛到目标场景；
- LLM 只输出语义（目标场景），不再直接输出具体 op；
- 卡死（停滞/振荡）时先上抛 LLM 脱困，LLM 也救不了再机械降级/abort。

根治 PKG_GUARD 死循环，同时把「土法归位」的隐式流程改为可测、可观察的显式状态机。

## 3. 架构总览

### 3.1 分层职责

```
LLM(语义层)   → 输出「目标场景」 target_scene(如 HOME)
                (pkg guard 场景使用；正常任务决策仍输出具体 op)
云端(导航层)  → detect_scene(perception.nodeTree) 得当前 scene
             → next_action(current, target) 查转移表 → 下发【单个原子动作】
端侧(执行层)  → 哑执行器,只做原子 op:tap/input/swipe/back/home/read_screen/wait
             → 执行后上报 perception
云端(收敛层)  → 收新 perception 重判 scene → 未到位再下发
             → 收敛守卫(停滞/振荡)防兜圈
             → 卡死时三级脱困阶梯
```

### 3.2 端云职责一句话

- **端侧**：无状态哑执行器。删除 `homeFirstPage`/`nextPage`/`HomeDetector`/`ScreenFingerprint`，删除 `home_first_page`/`next_page` 复合 op。
- **云端**：`scene.py`（已完成的 `detect_scene` + 转移表 `next_action`） + `decision.py` 逐帧收敛循环 + 收敛守卫 + 三级脱困。
- **LLM**：pkg guard 场景输出 `target_scene:` 语义；正常任务决策保留具体 op（收窄集合）。

### 3.3 收敛循环基于现有 WS 逐帧往返

不新增端侧内循环、不新增协议字段。每次端侧上报 perception 触发一次云端 `decide()`，pkg guard 段按 scene 状态机逻辑下发单个原子动作，往返直到收敛。

## 4. 云端收敛守卫 + 三级脱困阶梯

### 4.1 卡死的两种形态

| 形态 | 表现 | 检测手段 |
|------|------|---------|
| **停滞(stall)** | 连续同一 scene，动作无效原地不动 | 相邻两帧 `(scene, op)` 元组相同 → `stall_count++`，否则清零；`stall_count ≥ STALL_THRESHOLD` 判停滞 |
| **振荡(oscillation)** | scene 在几个态间来回横跳（如 HOME↔MINUS_ONE 左右滑不停） | `scene_history` 窗口内某非目标 scene 出现次数 ≥ `CYCLE_THRESHOLD` |

### 4.2 每 task 守卫状态

```python
guard = {
    "scene_history": [最近 WINDOW 帧的 scene 序列],
    "stall_count": int,
    "last_op": str,
    "escalation_level": int,   # 0=正常 / 1=已问过LLM脱困 / 2=已机械降级
}
```

存在 decision 的 per-task 上下文里（随 task 生命周期，task.end 清空），不落盘、用完即弃。

### 4.3 三级脱困阶梯

```
① 正常收敛(转移表逐帧驱动)
   └─ 停滞 or 振荡命中 → escalation_level=1,进入 ②
② LLM 脱困(升级)：喂「卡死上下文」回 LLM
   输入:current_scene / target_scene / scene_history / 卡死类型
   输出:target_scene(可换目标或坚持原目标),云端据此重走转移表
   └─ 执行 LLM_ESCALATION_TRIES 次后仍卡 → escalation_level=2,进入 ③
③ 机械降级 + abort(兜底)：
   尝试 _FALLBACK 备选动作表(如 MINUS_ONE 主动作 swipe right 失效则试 home)
   备选 FALLBACK_TRIES 次仍卡 → abort 任务,上报 error
```

### 4.4 常量（写在 `scene.py` 顶部可调）

- `STALL_THRESHOLD = 3`：连续同 scene 同 op 判停滞
- `CYCLE_THRESHOLD = 2`：非目标 scene 在窗口内重复次数判振荡
- `WINDOW = 6`：scene_history 长度
- `LLM_ESCALATION_TRIES = 1`：给 LLM 几次脱困机会
- `FALLBACK_TRIES = 2`：机械降级动作尝试次数

## 5. 端侧改动

### 5.1 删除清单（4 块土法逻辑）

| 删除 | 文件 | 原因 |
|------|------|------|
| `homeFirstPage()` | `android/.../accessibility/Executor.kt` | 黑盒复合归位 → 判定权移云端 |
| `nextPage()` | `android/.../accessibility/Executor.kt` | 翻页 + atEnd 判定 → 云端看 scene |
| `HomeDetector`（整文件） | `android/.../accessibility/HomeDetector.kt` | 满屏判定 → 云端 `detect_scene` |
| `ScreenFingerprint`（整文件） | `android/.../accessibility/ScreenFingerprint.kt` | 指纹判定 → 云端 scene 序列 |

`Executor.execute()` 的 when 分派中移除 `home_first_page` / `next_page` 两个 case。

### 5.2 保留的原子 op

```
tap / input / swipe / back / home / read_screen / wait
```

`swipe` 已是原子动作（带 `direction` 参数），云端转移表下发 `("swipe", {"direction":"right"})` 直接用。

### 5.3 协议改动（`Messages.kt` / `protocol.py`）

- **DownAction**：结构不变。协议层 op 取值集合收窄，删 `home_first_page` / `next_page`。
- **UplinkPerception**：不变。scene 检测在云端跑，端侧不上报 scene（保持哑执行器）。
- **UplinkActionResult.atEnd**：暂留字段，端侧恒为 false（因 `nextPage` 已删）。云端不再依赖 `atEnd` 导航（改看 scene）。彻底删字段留到 plan 里评估（YAGNI，暂留）。

## 6. LLM 提示词改造

### 6.1 三个决策点，不同输出语义

| 调用点 | 输入上下文 | 期望输出 |
|--------|-----------|---------|
| **A. pkg 不匹配需归位** | 当前 scene、目标 pkg | `target_scene: HOME`（就一行语义指令） |
| **B. pkg 匹配后正常任务决策** | 感知节点、goal、skill、cursor | 保留现有具体 op（**移除** `home_first_page`/`next_page`） |
| **C. 脱困(escalation)** | 当前 scene、目标 scene、`scene_history`、卡死类型 | `target_scene: X`（可换目标或坚持） |

### 6.2 parse 层改动

- 新增解析 `target_scene: HOME` 语义 → 云端返回 `next_action(current, HOME)` 得到的单个原子 Action。
- `_NOARG_OPS` 移除 `home_first` / `next_page`。

## 7. 数据流与错误处理

### 7.1 正常收敛示例（当前 MINUS_ONE 目标 HOME）

```
帧1: perception → scene=MINUS_ONE → next_action(MINUS_ONE,HOME)=("swipe",{direction:"right"}) → 下发
帧2: perception → scene=HOME → target 达成 → 清 guard → 放行给正常任务决策
```

### 7.2 振荡示例（LLM 脱困路径）

```
帧1: scene=HOME → next_action(HOME,IN_APP)="tap(icon)" → 下发
帧2: scene=MINUS_ONE(误触右滑) → next_action(MINUS_ONE,IN_APP)="swipe right" → 下发
帧3: scene=HOME → 再 tap
帧4: scene=MINUS_ONE → 命中振荡(HOME/MINUS_ONE 各出现2次)
     → escalation_level=1 喂 LLM: "你想去 IN_APP,但在 HOME↔MINUS_ONE 兜圈,重新想办法"
     → LLM 输出 target_scene: HOME (先稳到桌面再说)
帧5: 按新目标重走转移表 → 收敛
```

### 7.3 错误处理

- LLM 脱困返回无效 target_scene → escalation_level=2 进入机械降级
- 机械降级 `_FALLBACK` 表也无匹配 → abort 任务上报 error
- 端侧原子动作失败（ok=false）不影响 scene 判定，云端下一帧看新 perception 决策
- task.end 时清空 guard 状态，避免跨任务污染

## 8. 测试策略（TDD 铁律）

### 8.1 云端

- `test_scene.py`：**已完成** —— detect_scene(8场景) + next_action(转移表) 20 测试全绿。
- `test_decision.py` 新增 pkg guard 三级阶梯：
  - 正常收敛：MINUS_ONE 下发 `swipe right`（不再是 `home_first_page`）
  - 停滞触发 LLM 脱困：连续同 scene 同 op ≥ 阈值，验证走 LLM 分支
  - 振荡触发 LLM 脱困：喂 HOME→MINUS_ONE→HOME→MINUS_ONE 序列，验证走 LLM 分支
  - LLM 脱困后仍卡触发机械降级 / abort
  - 前序已 RED 就位的 3 个测试按新架构改断言（`swipe right` 等原子动作）
- LLM mock：脱困路径 mock LLM 返回 `target_scene:` 语义，验证解析 + 重走转移表。

### 8.2 端侧

- Executor 单测：删 `homeFirstPage` / `nextPage` 相关测试；保留原子 op 测试。
- `HomeDetector` / `ScreenFingerprint` 测试文件整体删除。

## 9. 提交点安排（穿插在 plan 里）

- **提交点 1**：先把前序积压 commit —— UI 重构 + 8 份采样重命名 + `scene.py`+测试。单独一次 clean commit。
- **提交点 2**：端侧删除土法逻辑（4 块 + Executor when 分支收窄），单独 commit。
- **提交点 3**：云端 `decision.py` 接入 scene 状态机（含收敛守卫 + 三级脱困），带测试 commit。
- **提交点 4**：LLM 提示词改造 + parse `target_scene`，带 mock 测试 commit。
- **提交点 5**：全量回归 + 真机 e2e 验证后 commit。

## 10. 交给 plan 评估的细节

- `atEnd` 字段是否彻底删（YAGNI，暂留）。
- 收敛守卫阈值（`STALL_THRESHOLD` / `CYCLE_THRESHOLD` / `WINDOW` / `LLM_ESCALATION_TRIES` / `FALLBACK_TRIES`）—— 常量放 `scene.py` 顶部可调。
- 脱困 prompt 文本细节。
- `_FALLBACK` 备选动作表具体内容（每个非目标 scene 至少一个备选）。

## 11. 非目标（YAGNI）

- 不引入端侧 scene 检测（保持哑执行器）。
- 不新增协议字段（DownAction/UplinkPerception 结构不变）。
- 不做多机型适配（沿用阶段一 OPPO 单机采样）。
- 不做 scene 状态机可视化/监控面板（后续如需再加）。