# 通用 Agent：目标由 app 端指定 — 设计文档

日期：2026-07-10
方案：A'（通用化 —— 核心代码场景无关，goal 由端侧上行指定）

## 背景与核心约束

最终形态是**通用手机操作 Agent**：云端只负责通用决策，**不得硬编码任何单一场景**
（如飞书 / Android 群 / 环球资讯等具体业务词）。飞书找群仅为一次性测试任务。

当前架构：端侧连上 → 云端主动下发 `task.start(goal)` 用硬编码 `_DEFAULT_GOAL` → 端侧被动执行。
问题：goal 硬编码在云端 `gateway.py`，且连接即自动开跑，不符合通用 Agent 形态。

## 目标

1. 云端 `gateway.py` 不含任何具体场景 goal，`_DEFAULT_GOAL` 改为通用中性兜底。
2. goal 由 **app 端指定**：新增上行消息 `task.request`，端侧把 goal 发给云端。
3. 连接后**不自动开跑**，必须点 app 里的测试按钮才下发 goal 并开始任务。
4. 飞书找 Android 群的 goal 文本作为**测试用常量放在端侧 UI 层**，不进核心逻辑。

## 改动范围

### 端侧（android）

- `protocol/Messages.kt`：新增 `UplinkTaskRequest(type="task.request", goal: String)`。
- `net/WsClient.kt`：新增 `sendTaskRequest(goal: String)`。
- 测试 UI：新增"运行测试任务"按钮，点击调用 `sendTaskRequest(TEST_GOAL)`；
  `TEST_GOAL` 为测试常量（飞书找 Android 群任务描述），置于 UI 层。
- `accessibility/PhoneAgentService.kt`：引入 `taskActive` 门控——待命期 `onAccessibilityEvent`
  不触发 `reportScreen()`；收到 `task.start` 置 true 开始上报；收到 task.done/abort 置 false 停止上报。

### 云端（server）

- `gateway.py`：
  - `_DEFAULT_GOAL` 改为通用中性描述（不含任何场景词）。
  - 连接后**不再自动下发 task.start 开跑**；仅在收到上行 `task.request` 后，
    用其 goal 覆盖 session.goal，再下发 `task.start` 启动决策循环。
  - WS 接收循环新增分支：解析 `task.request`，取 `goal` 字段。

## 测试用 goal 文本（端侧常量，仅测试）

> 在飞书里完成以下任务链，全程不发送任何消息：
> 1. 打开飞书后检测当前账号；
> 2. 若当前为企业账号"环球资讯"，切换到个人账号"飞书个人用户"；
> 3. 找到群名包含 "Android" 的群聊并进入；
> 4. 点击输入框使其获得焦点（弹出键盘/光标在输入框）即完成；
> 5. 禁止发送任何消息。

## 任务激活开关（关键决策）

端侧引入"任务激活"状态（`taskActive: Boolean`），默认 false：

- **待命期（未点按钮 / taskActive=false）**：`onAccessibilityEvent` **不触发 `reportScreen()`，端侧完全不上传 perception**。省流量、不采集、更干净。
- **点测试按钮**：端侧置 `taskActive=true`，发 `task.request(goal)`；云端下发 `task.start`；
  端侧收到 `task.start` 后开始上报 perception，进入决策循环。
- **任务结束（收到 task.done / task.abort）**：端侧置 `taskActive=false`，恢复待命、停止上报。

这样"没有明确 goal 时端侧不上传，只有开始执行需要 LLM 决策时才上传"。

## 数据流（新）

1. 端侧连接（待命，taskActive=false，**不上报 perception**）
2. 用户点测试按钮 → 端侧 taskActive=true，发 `task.request(goal)`
3. 云端收 goal → 覆盖 session.goal → 下发 `task.start`
4. 端侧收 `task.start` → 开始 reportScreen → 上行 perception
5. 云端 perception → engine.decide → 下发 action → … 循环
6. 收到 task.done / task.abort → 端侧 taskActive=false → 停止上报，回待命

## 错误处理

- 待命期端侧不上报，云端自然不决策；无需云端侧特殊忽略逻辑。
- 极端情况：若云端在无 active goal 时仍收到 perception（如时序竞态），直接忽略不决策（防御）。
- LLM 输出非 JSON：`decision.py` 已有兜底，返回 `read_screen`，不受影响。

## 测试

- 云端单测：`_DEFAULT_GOAL` **不含**任何场景硬编码词（不含"飞书""Android""环球资讯"）。
- 云端单测：收到 `task.request` 后 session.goal 被正确覆盖并下发 `task.start`。
- 端侧：`task.request` 序列化格式正确（如已有协议测试则补一条）。

## 实时可读日志（app 内，本次一并做）

### 现状

- Debug 后门：主界面连点标题 7 次解锁 `DebugPanel`（`MainViewModel.UNLOCK_THRESHOLD=7`）。
- 已展示：WS_URL / deviceId / 重连次数 / 最近动作(op ✓✗) / WS 底层事件。
- 短板：非流式、看不到收发内容（LLM 决策 params、感知上报、task.start/done/abort）、无人话状态。

### 方案：DebugPanel 内新增「实时事件流」

- `domain/AgentModels.kt`：新增统一日志模型 `TraceEvent(ts, direction, kind, summary)`，
  direction ∈ {UP, DOWN, INFO}，kind 如 perception/action/task.start/task.done/task.request 等。
- `data/AgentStateRepository.kt`：新增 `traceEvents` StateFlow + `appendTrace()`（takeLast(MAX_LOG)）。
- 在收发关键节点埋点：
  - 上行：发 perception（pkg/节点数）、发 action.result、发 task.request(goal)。
  - 下行：收 task.start(goal)、收 action(op+params)、收 task.done、收 task.abort(reason)。
- `ui/DebugPanel.kt`：新增「实时事件流」区块，按时间倒序滚动展示 `TraceEvent`，
  格式如 `12:34:56 ↑ perception pkg=lark nodes=30` / `12:34:57 ↓ action tap {id:0-0-6}`，
  等宽字体、方向箭头(↑↓·)、彩色/图标区分，一眼看懂当前收发。
- 顶部再加一行「当前状态」人话摘要（复用已有 TaskState.Running(description)）。

### 端侧日志测试

- `AgentStateRepository`：`appendTrace` 追加与 `takeLast(MAX_LOG)` 截断正确。
- `TraceEvent` 格式化字符串符合预期（便于阅读）。

## 不做（YAGNI）

- 不做多任务队列、不做 goal 输入框（先用固定测试按钮）。
- 不做账号切换状态机（交给 LLM）。
- 不改系统提示词。
- 不做日志导出/持久化到文件（先内存流式；云端已有 gateway.log 兜底）。

## 安全约束

核心代码（云端 gateway/decision/llm）保持场景无关；任何飞书专属内容只允许出现在
端侧测试 UI 常量与联调脚本中，绝不进入决策核心。