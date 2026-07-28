# Plan: Cancel Race & Stale TaskId Defense

> Plan-driven 实现;2026-07-28 立,架构质量优先

## 1. Goal

解决 2026-07-27 二审标记的 2 个 CRIT:
- **CRIT-1**: 取消按钮 race — 端侧乐观更新 UI 到 Idle,服务端下行 `task.abort` 把 UI 推回 `Failed: user_cancel`
- **CRIT-2**: 重连后旧 taskId 上行 — `TaskStore` 在重连时丢失,旧 taskId 到达 silent noop 但所有 taskId-bearing uplink 都缺统一防御

## 2. Architecture 设计

### 2.1 核心问题表述

两端状态在并发场景下的协调 = **镜像状态机(mirrored state machine)** 问题。client 端当前用 `TaskState` 单一字段做镜像,把「下行协议」和「上行用户意图」挤在同一字段,产生 race。

### 2.2 拆分维度

新增 `TaskUserIntent` model,与 `TaskState` 解耦:
- `TaskState`:仅由下行协议驱动 (Running / Idle / Done / Failed)
- `TaskUserIntent`:仅由上行用户行为驱动 (None / SentGoal / Cancelled)

UI 由两个独立维度合成:`Cancelled` 优先级最高,覆盖 `Running` 之外的协议收尾。

### 2.3 `Cancelled` 一次性语义

服务端下行 `task.abort` 到达端侧时:
1. 先 `consumeUserIntent(Cancelled)` — 若 UI 已经被切到 Idle,吃掉意图,不污染 TaskState
2. 若 Consume 失败(None / SentGoal)— 走正常 `TaskState.Done` / `Failed` 路径

**这是设计的关键**:`Cancelled` 是「我已主动 cancel」的 marker,服务端下行是「确认 cancel 完成」的回执,两者相遇时**意图吃协议**,因为意图代表用户主观决策,优先级最高。

### 2.4 服务端 helper

新增 `server/app/task/guard.py`:
- `current_task_or_none(uplink, store) -> TaskContext | None`:
  - 携带 taskId 且 ctx 匹配 → 返回 ctx
  - 携带 taskId 且 store 空 / mismatch → 返回 None (silent noop + 日志)
  - 非 taskId-bearing (心跳/perception/sample/action.result) → 透传
- `matches_current_task(uplink, store) -> bool`:布尔包装

未来加新的 taskId-bearing uplink 只需在入口调一次 `current_task_or_none`,无重复 patch。

## 3. 改动文件

| 文件 | 改动 |
|---|---|
| `server/app/task/guard.py` | 新增 — staleness helper + Logger |
| `server/app/task/handlers.py` | `_on_task_cancel` / `_on_confirm_response` 接入 helper;TaskCancel docstring 同步 |
| `server/tests/test_guard.py` | 新增 — helper 单测 9 项 |
| `server/tests/test_handlers.py` | 新增 — staleness e2e test 2 项 |
| `android/.../domain/AgentModels.kt` | 新增 `TaskUserIntent` sealed;`AgentStatus` 加 userIntent 字段 |
| `android/.../data/AgentStateRepository.kt` | 新增 `setUserIntent` / `consumeUserIntent` / `clearUserIntent` |
| `android/.../net/WsDispatcher.kt` | `onTaskEnd` 签名扩 `taskId` |
| `android/.../net/WsClient.kt` | `start()` 签名同步;manager 同步 |
| `android/.../accessibility/PhoneAgentService.kt` | `onTaskEnd` 接 `consumeUserIntent` 路由；onTaskStart 清 stale intent；Doc 解释 |
| `android/.../ui/MainViewModel.kt` | `onSendGoal` 标 SentGoal;`onCancelTask` 拆成 `onAbortRunningTask` + `onResetToIdle` |
| `android/.../ui/AgentScreen.kt` | `TaskStatusCard` 拆 `onAbort` / `onReset` 两个 callback |
| `android/.../MainActivity.kt` | 接 `onAbortRunningTask` + `onResetToIdle` |
| `android/.../test/.../WsDispatchTest.kt` | 同步签名 |
| `android/.../test/.../MainViewModelTest.kt` | 加 4 项 cancel race 测试 |
| `AGENTS.md` | 同步 task.cancel + TaskUserIntent + guard helper 说明 |

## 4. 风险与边界

### 4.1 SentGoal 漏清

`SentGoal` 在 `task.start` 到达时被 `clearUserIntent()` 兜底清;
若服务端 silent noop(`task.request` 不触发 `task.start`),SentGoal 会残留直到下次 task.start。

**接受**: 残留不显示(UI 仍按 TaskState 显),下次上行 task.cancel 时也不会进入 Cancelled 分支(因为意图是 SentGoal 不是 Cancelled)。

### 4.2 test mainviewmodel 改 currentTaskId 直读 repo

单测场景无 viewModelScope 启动,`SharingStarted.WhileSubscribed` 返回 initialValue,而 running taskId 存在 `repo.status.value.task`。改 `currentTaskId()` 直读 `repo.status.value.task` 而非 `uiState.value.status.task`。

### 4.3 cancel race 真机回归(留待用户)

端侧 consumeUserIntent + 服务端 silent noop 链路完整,但 **真机联调未跑**:
- 用户点取消 → UI 是否真的停在 Idle(不会短暂跳 Failed)
- 跨 connection 重连后旧 taskId 上行 → 不发下行,UI 保持

需要真机验证。代码无可见 fix 错误。

## 5. 不在本 plan 范围

- `TaskDone.result` 字面化(留 v3 协议)
- `cache mark_miss` 本场禁用机制(独立 commit)
- 主 activity :75 拆分 token 计数(other refactor)
- `wechat.py` sidebar_rid_keywords 补全(等真机校准)

## 6. Gates 目标

- 449 pytest passed(从 438 → +11)
- pyright 0 errors
- android `./gradlew :app:testDebugUnitTest` OK
