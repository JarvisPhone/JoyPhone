# 完整飞书闭环 + 路径缓存机制 设计文档

日期：2026-07-09
状态：已确认，待实现

## 1. 背景与目标

现有工程中，云端决策组件（`session.py` / `decision.py` / `skills.py` / `llm.py`）与端侧骨架（`WsClient` / `Perception` / `Executor` / `PhoneAgentService`）均已存在，但**从未串联**：

- 云端 `gateway.py` 只硬编码下发 `read_screen` / `done`，未使用 `DecisionEngine`。
- 端侧 `PhoneAgentService.onAccessibilityEvent` 为空实现，`WsClient` 从未被调用，`Executor` 仅返回 `true`。

**本次目标**：打通完整飞书场景端到端闭环，并新增路径缓存机制减少 LLM 调用。

完整场景：开无障碍后 App 自动连 WS → 真实识别屏幕 → 滑动桌面找到飞书图标 → 打开飞书 → 搜索联系人 → 输入并发送消息。

## 2. 已确认的关键设计决策

| 决策项 | 结论 |
| --- | --- |
| WS 地址注入 | 硬编码默认地址（常量/BuildConfig），改一处即可 |
| 目标场景 | 完整飞书场景（真滑桌面找图标 → 打开 → 搜联系人 → 输入 → 发送） |
| 云端决策驱动 | 真实 LLM（OpenAI 兼容接口，`base_url + api_key + model`），发送处理过的结构化 node tree（非图片） |
| tap 执行方式 | LLM 返回节点 id / match_text，端侧用节点 bounds 中心做真实手势点击 |
| 滑桌面找图标 | 首次交给 LLM 兜底（看到没飞书就 swipe，看到就 tap），成功后进缓存 |
| 端侧序列化 | 引入 kotlinx.serialization 替代手写 JSON |
| 缓存键 | `(goal, context)`，context = 当前屏幕 pkg |
| 缓存值 | 语义步骤序列（不含绝对坐标），命中后逐步重定位再执行 |
| 缓存学习 | 成功跑到 task.done 才写入；命中后某步失败则从该步回退 LLM 并更新缓存 |
| 缓存存储 | JSON 文件 `server/data/skill_cache.json`，启动加载内存、写时落盘 |

## 3. 整体架构与数据流

```
┌─────────────── Android 端 ───────────────┐         ┌──────── 云端 (FastAPI) ────────┐
│  MainActivity                              │         │  gateway.py (WS 端点)           │
│   └ 硬编码 WS_URL，显示服务状态             │         │   └ 每个连接 = 一个 Session     │
│  PhoneAgentService (AccessibilityService)  │◄──WS──►│  Session (状态机 + budget)      │
│   ├ onServiceConnected → 启动 WsClient     │  JSON   │   └ 收 perception → DecisionEngine│
│   ├ onAccessibilityEvent → 抓根节点树       │         │  DecisionEngine.decide()        │
│   ├ 提取 NodeInfo → NodeDto(含 bounds/desc) │         │   ├ 查缓存命中 → 语义步         │
│   ├ PerceptionFilter 裁剪 → 上报 perception │         │   ├ 命中 skills → 脚本步         │
│   └ 收 action → Executor → 回传 result      │         │   └ miss → RealLLM(结构化nodes) │
│  Executor                                  │         │  SkillCache (JSON 持久化)       │
│   └ tap: nodeId/match_text→bounds→手势点击  │         │   └ get / learn / mark_miss     │
│   └ input/back/home/swipe/open_app         │         │  RealLLM (OpenAI 兼容)          │
└────────────────────────────────────────────┘         └─────────────────────────────────┘
```

数据流（一个 step）：
1. Service 抓屏 → `perception(nodeTree + pkg + activity)` ──WS──▶ Session → DecisionEngine
2. DecisionEngine 先查 SkillCache，命中且当前屏幕可重定位 → 直接返回步；否则查 skills 脚本；再 miss → RealLLM
3. `action(op, params{nodeId/match_text/text})` ──WS──▶ Executor 执行
4. `action.result(ok/error)` ──WS──▶ Session 记录 → 触发下一 step
5. 收到 `task.done` → SkillCache.learn(key, applied_steps)

## 4. 组件职责与接口

### 云端

1. **`llm.py` 新增 `RealLLM(LLM)`**
   - 构造：`base_url` / `api_key` / `model`（从环境变量读，缺失则 fallback FakeLLM）
   - `complete(system, user, image_b64=None)` → openai SDK `chat.completions`，返回 content
   - system prompt 约束：只输出 JSON `{"op":..., "params":{...}}`

2. **`skill_cache.py`（新增）**
   - `SkillCache(path)`：启动加载 JSON 到内存
   - `get(goal, context) -> CachedSkill | None`
   - `learn(goal, context, steps)`：成功后写入并落盘
   - `mark_miss(goal, context, cursor)`：标记某步失效
   - 数据结构：`{key, steps[], hits, created_ts, updated_ts}`；步骤支持变量占位（如 `$MESSAGE_TARGET`）

3. **`decision.py` 改造 `DecisionEngine.decide`**
   - 先查 SkillCache：命中且当前屏幕能重定位目标节点 → 返回缓存步（不调 LLM）
   - 缓存未命中/失效 → 原有 skills 脚本 → LLM 兜底

4. **`gateway.py` 重写 WS 循环**
   - 连接建立 → 建 `Session` + `DecisionEngine(RealLLM, SkillLibrary, SkillCache)` → 发 `TaskStart`
   - 循环：收 perception → decide → 发 action；收 action.result → 记录、推进 cursor；budget 耗尽 → TaskAbort
   - 收 done → SkillCache.learn；done/abort 发对应下行并结束

5. **配置**：gateway 读 `os.environ`：`LLM_BASE_URL / LLM_API_KEY / LLM_MODEL`

### 端侧

6. **`Messages.kt`**：`NodeDto` 补 desc/bounds/className；引入 kotlinx.serialization 替代手写 JSON

7. **`WsClient.kt`**：内部实现 `WebSocketListener`，`onMessage` 解析下行 → 交给注入的回调 lambda

8. **`PhoneAgentService.kt`**：
   - `onServiceConnected`：初始化 WsClient 并 connect
   - `onAccessibilityEvent`：debounce 抓 `rootInActiveWindow` → 递归成 NodeDto → 上报 perception
   - 收到 action → Executor 执行 → 回传 action.result

9. **`Executor.kt` 真实实现**：
   - `tap`：按 nodeId/match_text 找 bounds → `dispatchGesture` 点中心
   - `input`：找 editable 节点 → `ACTION_SET_TEXT`
   - `back/home`：`performGlobalAction`
   - `swipe`：`dispatchGesture` 直线手势
   - `open_app`：`packageManager` launch intent（保留作 LLM 可选手段）

10. **`MainActivity.kt`**：`onResume` 检查服务是否 enabled，刷新 UI 状态文字

## 5. 错误处理

- **LLM 返回非法 JSON**：DecisionEngine 捕获 → 降级 `read_screen`，连续 N 次失败 → TaskAbort
- **LLM key 缺失/不可用**：gateway 启动 fallback FakeLLM，日志告警
- **端侧节点未命中**（tap match_text 未命中）：`action.result{ok:false, error:"node_not_found"}`，云端据此下发 swipe 继续找
- **缓存命中后某步失败**：从该 cursor 回退 LLM，任务完成后覆盖更新缓存
- **WS 断连**：WsClient `onFailure/onClosed` → 固定间隔重连（MVP 不做指数退避）
- **budget 耗尽**：Session `budget_exhausted()` → TaskAbort
- **手势失败/超时**：dispatchGesture callback 失败 → action.result ok:false

## 6. 测试策略（TDD）

- 云端（pytest，可离线）：
  - `RealLLM`：mock openai client，验证请求组装 + JSON 解析 + 非法响应降级
  - `SkillCache`：get / learn / mark_miss / 持久化读写
  - `DecisionEngine` 缓存路径：命中不调 LLM、失效回退 LLM、done 后学习
  - `gateway` 重写：FakeLLM + FastAPI TestClient WS 回放 perception→action→result 全流程
  - 现有 27 测试保持绿
- 端侧（JVM 单测）：
  - NodeDto 序列化/反序列化（kotlinx.serialization）
  - 下行 action JSON 解析
  - PerceptionFilter（已有）
  - 无障碍真实操作无法单测 → 真机手测（已知风险）

## 7. 生命周期串联

```
开无障碍 → onServiceConnected → new WsClient(WS_URL, listener) → connect(deviceId)
   → WS onOpen → 收 TaskStart → 记录 goal
   → onAccessibilityEvent (debounce 500ms) → 抓树 → 上报 perception
   → WS onMessage(action) → Executor.execute → 回传 action.result → 触发下一轮抓树
   → 收 TaskDone/TaskAbort → 停止上报，MainActivity 显示结果
   → 服务关闭 → WsClient.close()
```

## 8. 已知风险

1. 无障碍读桌面/飞书节点树的稳定性依赖具体 ROM 与飞书版本
2. dispatchGesture 需 Android 7+（minSdk 26 满足）
3. 真机联调需手机与跑 server 的 Mac 同一局域网，WS_URL 填 Mac 的局域网 IP
4. 缓存的语义步序列在飞书大版本更新后可能失效，依赖失败回退机制自愈