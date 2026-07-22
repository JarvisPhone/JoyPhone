# 02 · 任务内核

> 源码：`server/app/task/{context,fsm,policies,handlers}.py`

任务内核是**与具体业务无关的安全底座**：它管理任务状态、驱动感知-决策-执行循环、
用策略管道拦截危险动作、用因果对账保证时序正确。场景包（见 04）挂在它之上提供业务。

## TaskContext：唯一 per-task 状态载体

`context.py` 的 `TaskContext` 是一个任务从生到死的全部状态，包括：

- `cursor`（技能/缓存回放游标）、`confirm`（发送确认态）、`post_send`（发送后态）
- `loop_guard`（停滞守卫状态）、`entry_state`（入口分类）、`cache_context`
- `pending_sources` / `pending_mutating`（因果对账用的在途动作集）、`guard`（场景守卫态）

**关键设计：每次 `task.request` 到达，整体 new 一个新 TaskContext**（历史上因
"状态重置遗漏"出过 bug，改为整体新建后彻底根治）。`TaskStore` 按设备/任务维度
持有这些 context。

## TaskFSM：通用五态状态机

`fsm.py` 定义任务生命周期状态：

```
IDLE → RUNNING → (AWAITING_CONFIRM | WAITING_EVENT) → DONE / ABORT
```

- 迁移受 `_ALLOWED` 迁移表约束，非法迁移被拒绝，保证状态流转可预测。
- `transition(target, reason=...)` 每次迁移都记 `TransitionRecord`（含原因），
  便于事后追溯"为什么会走到 ABORT"。
- 提供 `force` 通道绕过迁移表（用于异常兜底），但**依然留痕**，不做"静默跳转"。
- 内置超时检查（如 AWAITING_CONFIRM 停留过久）。

## 策略管道：Verdict + run_pipeline

`policies.py` 是内核的"安全阀"。每个策略实现 `inspect(frame, ctx) -> Verdict`：

```
Verdict = continue_()          # 放行，继续跑后续策略/决策
        | terminate(reason,    # 立即结束任务（completed / aborted）
                    outcome)
        | intercept(actions)   # 拦截，改用给定动作（可为空 = 吞掉本帧决策）
```

`run_pipeline` 顺序执行策略，遇到 `terminate` / `intercept` 立即**短路**返回。
策略分两段挂载：

- **PRE（决策前）**：`BudgetPolicy`（预算/步数上限）、`ConfirmTimeoutPolicy`
  （确认超时）+ 场景注入的 pre 策略。它们基于原始 perception 帧判断，可在决策前
  就终止或改写。
- **POST（决策后）**：场景注入的 post 策略 + `LoopGuardPolicy`。它们经
  `ctx.decided_actions` 读取本帧已产出的决策动作，据此拦截。

这个"策略返回裁决、调用方负责收发"的解耦，是从旧 `gateway.py` 一大坨 if/else
重构而来——策略不再直接发消息，只表达意图。

### LoopGuardPolicy：停滞守卫

防"原地打转"的核心 POST 策略：

- 计算**帧签名**（`frame_signature`：对节点特征做 md5）× **决策签名**
  （`decision_signature`：op + 锚点）。
- 同一 (帧签名, 决策签名) 重复达 `LOOP_GUARD_TRIGGER` 次，判定卡住，改发 `back`
  尝试脱困。
- 累计 back 超过 `LOOP_GUARD_MAX_BACKS` 仍无进展 → `terminate(stuck_loop)`。

## 上行分派：handlers.py

`handle_uplink` 是所有上行消息的总入口，按类型分派：

| 上行消息 | handler | 职责 |
|----------|---------|------|
| `task.request` | `_on_task_request` | 新建 TaskContext、选场景包、装配 cursor/策略 |
| `perception` | `_on_perception` | 主循环（见下） |
| `action_result` | `_on_action_result` | 对账推进 cursor、回放熔断、F2 补帧 |

### `_on_perception` 主循环

一帧感知到达后的处理顺序（每一步都可能短路）：

```
1. seq 闸门          —— 丢弃乱序/过期帧
2. PRE 策略管道      —— 预算/确认超时/场景前置，可 terminate/intercept
3. AWAITING_CONFIRM  —— 若在等确认，短路（不决策）
4. pending_mutating 闸门（F2，见下）
5. classify_entry    —— 场景对入口界面分类如"已在目标会话"）
6. engine.decide()   —— 调决策引擎产出动作
7. POST 策略管道     —— 场景后置 + LoopGuard，可拦截本帧决策
8. dispatch          —— 下发最终动作
```

### F2 因果对账闸门

这是保证"不用旧帧做终态决策"的关键机制：

- 变更类动作（tap / input / swipe 等 mutating）下发后，记入 `pending_mutating`。
- **只要 `pending_mutating` 非空，`_on_perception` 就跳过 decide**——因为此刻收到的
  帧可能还是动作生效前的旧帧，基于它决策会误判（历史上"旧帧终态决策"出过事故）。
- `_on_action_result` 里，当这些 mutating 动作全部 ack 后，云端**主动补发一个
  `read_screen`** 去抓真正的新帧，再恢复决策。

一句话：**变更动作 → 等 ack → 主动抓新帧 → 才允许下一步决策**，因果严格对齐。

### `_on_action_result` 的三件事

1. **cursor 推进**：cache/skill 命中的步骤 ack ok → `cursor.advance()`；
   verify FAIL → `cursor.fail()`（回落 LLM）。
2. **回放熔断**：cache 同一步连续失败达阈值 → 本场禁用该 cache。
3. **F2 补帧**：mutating 全部 ack 后补 `read_screen` 抓新帧。

此外 `_learn_cache` 在任务成功时把轨迹交给缓存层沉淀（要求轨迹含 tap 才学，
见 05）；`_maybe_classify_entry` 处理"热启动"——若一进 App 就已在目标会话，
直接把 cursor 快进到 `verify_title` 步，省掉前面的搜索导航。

## 设计取舍小结

| 取舍 | 选择 | 理由 |
|------|------|------|
| 状态重置 vs 整体新建 context | 整体新建 | 根治"重置遗漏"类 bug |
| 策略直接收发 vs 返回 Verdict | 返回 Verdict | 解耦、可测、可组合 |
| 允许乱序决策 vs F2 闸门 | F2 闸门 | 杜绝旧帧终态决策 |
| 非法迁移静默 vs 迁移表+留痕 | 迁移表+留痕 | 状态可预测、可追溯 |