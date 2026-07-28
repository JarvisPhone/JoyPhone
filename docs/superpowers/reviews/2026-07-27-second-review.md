# JoyPhone 二审报告 (2026-07-27)

> 复盘对象:server `3464cd0` + `165b4d3` 及更早 P2 expansion commit
> 范围:protocol / handlers / decision / scenario / android 端
> 思路:质量优先,发现设计不合理之处并归类严重度

---

## 严重度定义

| 级别 | 含义 |
|---|---|
| **CRIT** | 真实用户能立即触发的 UX bug / 协议破坏,必须修 |
| **HIGH** | 边界 case 触发一致性问题 / 文档与实现漂移,影响维护 |
| **MED**  | 设计/命名可优化,影响代码可读性 / 二次开发成本 |
| **LOW**  | 微小不一致 / 边界 hardens,优先级低 |

---

## CRIT-1: 用户取消后 UI 被 task.abort 下行覆盖成 "失败: user_cancel"

**位置**:`android/app/.../MainViewModel.kt:121-137` + `accessibility/PhoneAgentService.kt:103-113`

**重现**:
```
t=0:   用户点击「中止任务」
t=δ1:  MainViewModel.onCancelTask() 发 task.cancel 上行
       + 乐观更新 UI → TaskState.Idle
t=δ2:  服务端 _on_task_cancel → _terminate → 下行 task.abort(reason="user_cancel")
t=δ3:  端侧 WsDispatcher → onTaskEnd(done=false, "user_cancel")
       → PhoneAgentService.updateTask(TaskState.Failed("user_cancel"))
t=δ4:  UI 显示「失败: user_cancel」← UX 误报
```

**根因**:服务端取消成功时仍下行 `task.abort`,与端侧乐观更新产生 race。我之前在 `165b4d3` 修的是「silent noop」(no-task / DONE / ABORT 状态不发下行),但**遗漏了 active cancel 路径**——服务端 cancel 成功仍下行 task.abort。

**修复方案**(取 C,综合 A/B 最简):
1. **Repo 加 `pendingCancelledTaskIds: Set<String>`** + `markTaskCancelled(taskId)` + `consumeCancelledTask(taskId): Boolean`
2. **WsDispatcher / WsClient 改 onTaskEnd 签名**:`(done: Boolean, taskId: String, detail: String) -> Unit`
3. **PhoneAgentService.onTaskEnd**: 收到 taskId 后先 `consumeCancelledTask(taskId)`,若 true → 忽略(taskActive=false 收尾仍跑,UI 不变)
4. **MainViewModel.onCancelTask** 发 task.cancel 后立即 `repo.markTaskCancelled(taskId)`
5. 测试:`WsDispatchTest` 新增 case:task.abort(taskId="t1") 被 markCancelled("t1") 消费后,**不调 onTaskEnd** 或调但不传 UI

**工作量**:6 文件改 / 3 个新增测试 / 2 个 docstring 同步 / 1 AGENTS.md 说明。预计 ~80 行 diff,1 个 commit。

---

## CRIT-2: TaskStore 持久性在重连后丢失,旧 taskId 上行 cancel → silent noop 但服务端无防御

**位置**:`server/app/task/handlers.py:_on_task_cancel` + `TaskStore`

**场景**:
- 设备断连瞬间发 task.cancel(待发,服务端未收)
- 重连后服务端 store.current = 新 task,旧 taskId 上行 → silent noop
- 客户端**不知道 cancel 失败**,UI 已 Idle

**修复方案**:
- 加 ws 连接级 staleness check:每 frame 的 `uplink.taskId` 与当前 store.current.task_id 比对,不匹配 silent noop + log warning
- 已在 `_on_task_cancel` 写过 store.mismatch 检查,**只需把这段逻辑提为公共 helper,所有 taskId-bearing uplink 都过一遍**(防 ConfirmResponse / ActionResult 同样问题)

**工作量**:1 helper + 5 个 uplink 调用点过一遍 / 2 测试。

---

## HIGH-1: TaskCancel docstring 与实现不一致

**位置**:`server/app/protocol/models.py:89-101` + `server/app/task/handlers.py:380-389`

docstring 还写「其他状态拒收并回 task.done(cancelled_noop)」,实际 `165b4d3` 改成 silent noop 不发下行。

**修复**:同步 docstring,删除 cancelled_noop 字眼。

---

## HIGH-2: cache mark_miss 行为与 AGENTS.md 描述不符

**位置**:`server/app/decision/cache.py:217-220` + `AGENTS.md:cache 同一步 ack 失败达 N 次整条作废+本场禁用`

实际 `_data.pop` 是**永久丢弃**(写文件 flush),不是"本场禁用"。AGENTS.md 表述与技术债现实不一致。

**修复**:
- 选 A: 实装"本场禁用"机制(`_disabled_in_session: Set[key]`),session 重启后 cache.json 中无该 key 仍可重学
- 选 B: AGENTS.md 改写,与现状一致("cache 同一步 ack 失败达 N 次整条**永久丢弃**,直到下次显式 record_success 重新学习")

工作量 A>B,但语义更对。**选 A**。

---

## HIGH-3: MainViewModel.onCancelTask docstring 与实现不一致

**位置**:`android/.../MainViewModel.kt:112-119`

docstring 仍写「云端下行 task.abort / task.done(noop) 后会被 PhoneAgentService 覆盖 Running → Done/Failed」,165b4d3 后 server 不再发 task.done,UI 不再被覆盖。

**修复**:docstring 重写,与 silent noop 同步。

---

## MED-1: onCancelTask 命名混淆 + 职责过载

**位置**:`android/.../MainViewModel.kt:121`

`onCancelTask` 在 Done/Failed 时被用于"重置 UI",但函数名暗示"取消运行中任务"。两件事语义不同但共用入口。

**修复**:拆 `onAbortRunningTask()`(发 task.cancel 上行) + `onResetToIdle()`(只 UI 切 Idle,无网络)。UI 层分支:
- Running → onAbortRunningTask
- Done/Failed → onResetToIdle
- Idle → 不显示按钮

工作量:5 个 UI call sites / 2 个测试。

---

## MED-2: TaskDone.result 用 freeform 字符串 + 端侧硬编码 "失败: " 前缀

**位置**:`server/app/protocol/models.py:TaskDone.result: str` + `android/.../PhoneAgentService.kt:106`

`result: str` 类型不安全:"ok" / "failed" / "cancelled" / "true" 都可能。端侧靠 `if (done) detail else "失败: $detail"` 强加中文。

**修复**:TaskDone.result 改为 `Literal["ok", "failed", "cancelled"]`;端侧根据 result 类型显示对应 i18n key。但**协议 schema 是 breaking change**,需要 v3 协议版本号(下一轮)。

---

## MED-3: wechat profile 缺 sidebar_rid_keywords 字段

**位置**:`server/app/scenario/profiles/wechat.py`

feishu 有,wechat 没有,16 个 misc profile 也没有(占位 OK)。但 wechat 是"重点支持 app",迟早要补。

**修复**:留待真机校准时填,与 `llm_brief` 一起更新。

---

## MED-4: SkillCache cursor 参数收而不用

**位置**:`server/app/decision/cache.py:217` mark_miss(self, goal, context, cursor: int)

`cursor` 参数被定义但 body 没读。AGENTS.md 说"达 N 次"——但实际上 _data.pop 没累计计数器。

**修复**:要么 cursor 用起来(命中 N 次 step 才 pop),要么去掉 cursor 参数。MVP 简化为「同一步 ack 失败即 pop」与 `_disabled_in_session` 机制绑定。

---

## LOW-1: protocol literal 类型未导出 _Downlink / _Uplink 基类名

**位置**:`server/app/protocol/__init__.py`

`__all__` 没列 `_Downlink`,端侧 import 不到(其实不该 import,但搜索时容易困惑)。

**修复**:__all__ 加 `_Downlink` (用 `_` 前缀明示 private)。

---

## LOW-2: render_layout_summary 空屏返回 "" → LLM 看到 `layout: ` 后面空

**位置**:`server/app/decision/payload.py:99-101`

空 nodes 时输出空串,导致 LLM payload 的 `[OBSERVE]` 段 `layout: ` 行尾无内容。

**修复**:`layout: (empty)` 字面占位,让 LLM 知道这是空屏而非字段缺失。

---

## LOW-3: AGENTS.md `loop_guard 拦截处自动 record` 实际 handler 内 _record_decision_metrics 仅记 "source",loop_guard 计数手动 record_loop_guard_trigger

**位置**:`server/app/task/handlers.py:_dispatch` + AGENTS.md

docstring AGENTS.md 表述准确但路径混乱,grep 容易找不到。**非 bug,只 doc 化**。

---

## 二审结论

- **2 个 CRIT 必须修**:任务取消 race (CRIT-1) + taskId staleness helper 提取 (CRIT-2)
- **3 个 HIGH 应该修**:TaskCancel docstring 漂移 / cache mark_miss 行为 / ViewModel docstring 漂移
- **4 个 MED 优化**:onCancelTask 拆分 / TaskDone.result Literal / wechat sidebar / cache cursor
- **3 个 LOW 清理**:`_Downlink` 导出 / layout_summary 空屏 / AGENTS.md 措辞

**实施建议**:分 2 个 commit:
- `fix(cancel)` CRIT-1 + HIGH-1 + HIGH-3(都是 task.cancel race 修复 + 文档同步)
- `refactor(cache)` HIGH-2 + MED-4(cache 本场禁用机制 + cursor 清理)

MED / LOW 留待后续小批次处理。

---

## 旁路发现(本次不修,留作 backlog)

- **PROTOCOL_VERSION 不在线协议里**:仅 WS 握手 query check,client 启动时硬编码。升级协议时需配合端侧升级。**已知 trade-off,不算 bug**。
- **TaskStore 不是线程安全的**:仅 asyncio 单 loop 下安全。**已通过单 connection 单 loop 保证**。
- **discarded action_id 在 _terminate 后 metrics 仍计入**:取消前在途 action 的 ack 仍计入 metrics.record_action_result。**语义上动作确实成功了**,暂保留。