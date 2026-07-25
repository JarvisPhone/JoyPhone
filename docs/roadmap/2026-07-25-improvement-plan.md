# JoyPhone 改进计划

> 生成日期: 2026-07-25
> 状态: 进行中
> 来源: 用户复盘反馈 + 代码库全面审查

---

## 一、安卓客户端交互升级

### 1.1 问题

当前「运行测试任务」按钮写死 `打开飞书，给群「Android AI 开发组」发一条消息`，用户无法自定义任务目标。

### 1.2 目标

将测试按钮替换为 **文本输入框 + 发送按钮**，用户可自由输入任务指令。

**后续扩展**: 发送按钮同时作为**语音输入触发器**，支持按住说话 → 语音转文字 → 自动填入输入框 → 点击发送。

### 1.3 设计方案

```
┌──────────────────────────────────────────────┐
│  JoyPhone Agent                              │
├──────────────────────────────────────────────┤
│  [无障碍服务] [云端连接] [当前任务]            │
│                                              │
│  ┌────────────────────────────────────────┐  │
│  │  你想让我做什么？                        │  │ ← TextField (EditableText)
│  └────────────────────────────────────────┘  │
│  [🎤/发送]                                  │  ← 按钮: 点击=发送; 长按=语音输入
│                                              │
│  [场景采样] [当前任务状态]                     │
└──────────────────────────────────────────────┘
```

**Voice Input 实现路径** (优先级 P2):
- 短期: 用 `Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)` 调用系统语音输入 Activity
- 中期: `SpeechRecognizer` + continuous listening + VAD
- 回调: 语音结果填入 TextField，用户确认后点发送

**WS 消息格式不变**: `task.request { goal: string }` — Android 只负责把 TextField 内容透传给云端。

### 1.4 任务卡片设计调整

```
任务状态: Idle / Running(描述) / Done / Failed(原因)
Running 时: 显示当前步骤描述 + 中止按钮
Done/Failed 时: 显示摘要 + 重新输入入口
```

---

## 二、云端日志分析与死循环根因

### 2.1 问题

日志中出现重复性或死循环的策略发送，可能原因:
1. **LLM 拿到信息不足**: 不清楚当前页面状况，不知道该做什么，反复重试
2. **退出路径不明确**: 进入二级页面后出不来，一直 back+home 循环
3. **widget/负一屏误识别**: 把不可点磁贴当图标反复点
4. **context 被截断**: LLM 不知道走了多少步、离目标多远

### 2.2 诊断工具: LLM 决策日志打点

当前已有 `llm.log`，但缺乏决策原因记录。建议在 `_llm_decide` 里新增结构化打日志:

```
[LLM_DECIDE] seq=47 | goal="打开飞书发消息" | scene=launcher.home
  pkg=com.coloros.launcher | target_pkg=com.ss.android.lark | feedback=""
  nodes=32(clickable=8,input=1,label=23) | cursor_step=2/5
  [llm_output] "tap 5" | [action_dispatched] tap@node5 | latency_ms=1243
```

每次 LLM 决策后打一行结构化日志，含: `seq`、`scene`、`nodes 统计`、`cursor 进度`、`LLM 输出`、`下发 action`、`延迟`。这样从日志里可以直接算「同一个意图重复了多少帧」。

### 2.3 根因分类与对策

| 根因 | 症状 | 对策 |
|---|---|---|
| 退出路径缺失 | 连续 3+ 次 back 或 home | 见 §三·退出路径体系 |
| 信息不足 | LLM 连续 read 或 wait | 见 §三·上下文扩充 |
| widget 误点 | tap 了 label 被拦截 | 已有 §三·widget 规则强化 |
| scene 误判 | LLM 误以为在 app 内 | 见 §二·scene 检测强化 |
| cursor 走偏 | 同一步骤连续 ack fail | cache 熔断已实装，继续优化 |
| feedback 不明确 | LLM 收到反馈但不知道修什么 | 见 §三·结构化 feedback |

---

## 三、云端交互格式与指令体系

### 3.1 现状分析

**Prompt 格式 (已是非 JSON)**: `_llm_decide` 用自然语言 system prompt，LLM 返回纯文本指令（`tap 5` / `input 3 你好` 等），服务端 `parse_actions` 解析为 `Action` 结构。

当前 prompt 传给 LLM 的字段:
- `goal`: 任务目标
- `pkg`: 当前前台应用
- `target_pkg`: 目标应用
- `scene`: 场景标签（launcher.home / launcher.minus_one / app / systemui.* 等）
- `screen`: `_encode_nodes` 输出的节点列表，格式 `[序号] 类型 "文本"`

**问题**:
1. `screen` 输出信息单一，只有序号+类型+文本，缺少**语义层级**（哪些是顶部标题/搜索框/列表项/底部导航）
2. 没有**退出路径的显式描述**，LLM 需要自己推理"现在怎么出去"
3. `feedback` 格式是自然语言，LLM 解析不稳定
4. 缺少**任务进度指示**（cursor 已完成几步/共几步，离目标多远）

### 3.2 screen 格式升级

把 `_encode_nodes` 升级为**带结构化语义**的输出，LLM 拿到的不只是"第 N 个可点元素"，而是知道每个元素在 UI 层级里的角色:

```
[SCRREN]
pkg: com.ss.android.lark   scene: app
screen:
  [0] header "Android AI 开发组"           ← 当前页标题
  [1] input "输入消息..."                   ← 消息输入框
  [2] button "发送"                        ← 发送按钮
  [3] list_item "张三: 你好"               ← 聊天列表项
  [4] list_item "李四: 在吗"               ← 聊天列表项
  [5] nav "通讯录"                         ← 底部导航
  [6] nav "工作台"
  [7] nav "我的"

nav_map: header | input | [2]button | list | [5-7]nav

goal_progress: step 2/3 | done: tap 搜索框 | current: 在输入框输入文本 | next: tap 发送
exit_hint: 按一次 [back] 返回上一级列表，再按一次回到通讯录首页

actions available: tap | input | swipe up/down | back | home | done | abort | expect
```

**关键改动**:
- `type` 从 4 态(input/button/label/text)扩展为带语义的: `header` / `input` / `button` / `list_item` / `nav` / `fab` / `drawer` 等
- 新增 `nav_map`: 屏幕布局结构摘要，让 LLM 一眼知道顶部/中部/底部/侧边有什么
- 新增 `goal_progress`: cursor 进度指示，让 LLM 知道离目标还有几步
- 新增 `exit_hint`: 当前场景的标准退出路径描述（launcher.home→swipe right退出负一屏，app内→back返回上级）

### 3.3 指令集扩充 (Action Space)

当前支持: `tap` / `input` / `swipe` / `back` / `home` / `wait` / `read` / `done` / `abort` / `expect`

**扩充方向**:

| 新指令 | 用途 | 示例 |
|---|---|---|
| `longpress n` | 长按元素（触发上下文菜单） | `longpress 3` |
| `open_notifications` | 拉下通知栏 | `open_notifications` |
| `open_quick_settings` | 拉下控制中心 | `open_quick_settings` |
| `press enter` | 键盘回车 | `press enter` |
| `scroll_to top` / `scroll_to bottom` | 滚动到顶/到底 | `scroll_to bottom` |
| `get_clipboard` | 读取剪贴板内容（部分 app 支持） | `get_clipboard` |

### 3.4 结构化 Feedback

把 feedback 从自然语言改为结构化 JSON 片段，LLM 解析更稳定:

```
feedback:
  last_action: tap | input | ...
  result: ok | fail
  reason: "节点 [5] 不存在" | "action.result.ok=false" | "被 ConfirmInterceptPolicy 拦截"
  page_changed: true | false       ← 页面是否变化
  screen_diff: 0.3                  ← 与上一帧相比的节点变化率(0-1)
  stuck_frames: 3                   ← 连续同决策帧数(>0 说明可能循环)
```

---

## 四、退出路径体系 (最高优先级)

### 4.1 问题

进入 app 二级页面后出不来，是最大痛点。用户反馈"但凡我们多点进来一步，进入了飞书的二级页面，可能就没法出来了"。

### 4.2 根因分析

1. **scene=app 时**，LLM 收到的是 `scene: app`（不够细），不知道现在在 app 的哪一页
2. **没有层级信息**: LLM 不知道当前页是"联系人列表"还是"聊天会话"还是"设置页"
3. **back 策略不明确**: 连续 back 不知道要 back 多少层才能出去
4. **LoopGuard** 只在「完全重复帧+完全重复决策」时触发，但「稍微不同」的 back+home 循环不被检测

### 4.3 方案: 页面拓扑感知

**A. 页面类型检测（app 内）**

在 `detect_scene` 基础上，新增 app 内页面分类:

```
AppPageDetector:
  - INBOX_LIST:     通讯录 / 消息列表 (有输入框 + 列表)
  - CHAT:           会话页 (有消息气泡 + 输入框 + 发送按钮)
  - CONTACT_INFO:   联系人详情页 (无输入框，有头像/菜单项)
  - SETTINGS:       设置页 (有开关/菜单项列表)
  - SEARCH:         搜索结果页
  - GROUP_INFO:     群详情页
```

检测规则（飞书为例）:
- `CHAT`: 同时含 `[输入框]` + `[发送按钮]` + 有聊天消息节点
- `INBOX_LIST`: 有输入框(搜索用) + 列表，无消息气泡
- `CONTACT_INFO`: 无输入框，有「发消息」「音视频通话」等按钮
- `SEARCH`: 输入框有文字 + 结果列表

**B. 退出路径模板库**

每个 `AppPage` 有标准退出路径:

```
LAUNCHER_HOME:
  exit_hint: "点击桌面图标即可进入应用，无需退出"
LAUNCHER_MINUS_ONE:
  exit_hint: "swipe right 向右滑退出负一屏"
  emergency: "连按两次 home"
NOTIFICATION:
  exit_hint: "swipe down 或 back"
CONTROL_CENTER:
  exit_hint: "swipe down 或点击空白处"
APP.INBOX_LIST:
  exit_hint: "无需退出，在列表内找目标；进入会话后用 back 返回"
APP.CHAT:
  exit_hint: "按一次 back 返回会话列表，从列表内选其他目标"
APP.CONTACT_INFO:
  exit_hint: "按一次 back 返回上一级"
APP.SETTINGS:
  exit_hint: "按一次 back 返回上一级，多层设置需多次 back"
APP.SEARCH:
  exit_hint: "按一次 back 或点左上角返回"
APP.GROUP_INFO:
  exit_hint: "按一次 back 返回会话页"
```

**C. LoopGuard 升级**

扩展 `policies.py` 的 `LoopGuardPolicy`:
1. **同决策连续 N 帧 → abort**（已实装但阈值待调）
2. **back+home 振荡检测**: 若最近 5 帧内出现 `back`→`home`→`back`→`home` 这种模式，判定为退出路径迷失
3. **page_back 计数**: 记录本 app 内已 back 了多少层，超过阈值给出警告（不是 abort，而是给出 exit_hint）

---

## 五、架构与基础设施

### 5.1 协议层: screenshot 字段激活

协议 `Perception` 定义了 `screenshot: str | null`，但当前端侧没传、云侧没处理。

**目标**: 支持云端 LLM **按需**请求截图（`request_screenshot` op），用于视觉判断（如图标模糊、页面布局复杂时）。

路径:
1. 端侧: `PhoneAgentService` 截屏→Base64→通过 `perception.screenshot` 上报
2. 云侧: LLM prompt 里加 `[screenshot attached]` 标记
3. `RealLLM.complete()` 支持 `image_b64` 参数（已实装）
4. 控制频率: 只有 LLM 发了 `request_screenshot` 时才传，否则不传（节省带宽）

### 5.2 设备能力架构

AGENTS.md 提到但未实装: `device.hello` 握手帧上报设备能力矩阵。

**目标**: 握手时端侧上报:
```json
{
  "type": "device.hello",
  "capabilities": {
    "screenshot": true,
    "speech_input": true,
    "gesture_multi_touch": true,
    "gesture_long_press": true,
    "max_nodes_per_frame": 500
  }
}
```

云端据此决定 action space（如设备不支持 long_press 则 LLM 不生成该指令）。

### 5.3 metrics 与监控

当前 `metrics.py` 较简单，建议增加:
- `task_duration_ms`: 任务从 start 到 done/abort 的总时长
- `llm_calls_per_task`: 每任务 LLM 调用次数
- `action_success_rate`: 各 op 的 ack ok 率
- `loop_guard_triggered_count`: 每任务 LoopGuard 触发次数

---

## 六、测试与验证

### 6.1 真机测试流程

每次代码改动后，在真机上跑以下场景:

```
场景 A (正向): 打开飞书 → 找群 → 发消息 → done
场景 B (负一屏退出): 桌面积木负一屏 → swipe right 退出 → 打开飞书
场景 C (二级页退出): 飞书内进入群设置 → back 退出 → 发消息
场景 D (widget 子入口): 点击「飞书 有 N 条通知」widget → 进入飞书会话
场景 E (搜索退出): 搜索不到目标 → abort 并给出原因
```

### 6.2 日志分析方法

联调时启动日志监控:
```bash
# 终端 1: 启动服务端
cd server && uv run python scripts/run_uvicorn_detached.py

# 终端 2: tail 实时日志
tail -F server/logs/uvicorn.log server/logs/comm.log server/logs/llm.log
```

分析重点:
- `LLM_DECIDE` 行: 连续同决策/同 action → 循环
- `CACHE_HIT` 行: cache 命中后的 ack fail → 整条作废
- `LoopGuard` 行: 触发原因
- `action.result` 行: ok=false 的原因

---

## 七、优先级与里程碑

### P0 (阻塞性，必须先修)

- [ ] **退出路径迷失**: LoopGuard 升级 + 页面拓扑感知 + exit_hint
- [ ] **screen 格式升级**: 带语义的 nav_map + goal_progress + exit_hint
- [ ] **结构化 feedback**: 让 LLM 收到稳定的反馈信号

### P1 (核心体验)

- [x] **Android 文本输入框 + 发送按钮**: 替换硬编码按钮 ✅ (2026-07-25)
- [ ] **Android 语音输入**: Intent 调用系统语音(推迟,先不做)
- [ ] **死循环诊断日志**: LLM_DECIDE 结构化打点
- [ ] **scene 检测强化**: app 内页面细粒度分类
- [x] **LLM 交互格式去除 JSON 包装**: user prompt 改为自然文本格式 ✅ (2026-07-25)

### P2 (功能完善)

- [ ] **指令集扩充**: longpress / scroll_to / press enter 等
- [ ] **screenshot 按需上报**: 视觉模态激活
- [ ] **device.hello 能力握手**: 协议层完善
- [ ] **metrics 监控增强**: 任务级指标

### P3 (优化)

- [ ] **cursor 进度感知增强**: 告诉 LLM 离目标还剩几步
- [ ] **cache 语义沉淀**: widget 子入口等 pattern 写入 cache
- [ ] **skill 模板库**: 常见 app 操作链标准化

---

## 八、待确认问题

1. **Android 语音输入**: 长按 vs 单独按钮，哪个交互更自然？
2. **screen 格式升级后 LLM prompt 长度**: 加了 nav_map + exit_hint + goal_progress 后 token 消耗增加多少，需要测一下
3. **app 内页面检测的可靠性**: 基于 text/desc/className 的规则在各家定制 ROM 上是否稳定
4. **用户是否需要中途干预能力**: 任务跑偏时用户能否手动中止/改目标
5. **多任务支持**: 当前一个任务进行中，用户能否发起新任务，还是必须等完成

