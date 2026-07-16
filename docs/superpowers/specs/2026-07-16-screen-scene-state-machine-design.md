# 屏幕场景状态机 + 探针采样 设计

- 日期：2026-07-16
- 状态：已与用户对齐，阶段一（探针采样）待实现
- 关联问题：PKG_GUARD 死循环（`server/app/decision.py:202`），桌面 launcher 被误判为「跑错 app」导致每帧强制翻屏

## 1. 背景与问题

当前「当前处于什么屏幕场景」这一判断散落在两处，且口径不一致：

1. **Prompt 文字**（`decision.py` `_SYSTEM_PROMPT`）：用自然语言教 LLM 识别「跑错 app 要回桌面」「负一屏要右滑」「通知横幅忽略」。属概率遵守，不可靠。
2. **代码硬约束 PKG_GUARD**（`decision.py:200-208`）：`if target_pkg and pkg and pkg != target_pkg: return home_first_page`。桌面 launcher 包名（本机 OPPO 为 `com.android.launcher`）不等于目标 app，被判成「跑错 app」，每帧强制 `home_first_page`，永远走不到「tap 图标」→ **死循环**。

两处逻辑对「当前在哪个场景」的判断打架，是死循环根因。

## 2. 目标

引入一个**显式、单一口径的「屏幕场景状态机」**，把「人眼现在看到的是哪类界面」收拢成确定性的识别层，作为决策的场景上下文，从根本上消除 prompt 与硬 guard 的冲突。

## 3. 架构：两个正交状态机并存

| 维度 | 回答的问题 | 载体 | 是否本次改动 |
| --- | --- | --- | --- |
| **场景态**（新增） | 人眼现在看到哪类界面 | 云端纯规则识别，每帧必跑 | 阶段二 |
| **任务态**（已有） | 任务推进到哪一步 | `server/app/session.py`（NAVIGATING→…→DONE） | 不动 |

两者独立并存，决策时都参考。任务态保持现状，不改。

### 场景枚举（初版）

- `LOCKED` 锁屏
- `HOME_FIRST` 桌面第一屏
- `HOME_OTHER` 桌面非第一屏
- `MINUS_ONE` 负一屏（小布建议/智能助手页）
- `NOTIFICATION` 通知栏（下拉浮层）
- `CONTROL_CENTER` 控制中心（下拉浮层）
- `IN_TARGET_APP` 目标 App 内
- `IN_OTHER_APP` 其它 App 内

### 场景识别策略：纯规则，分三层

1. **第①层 包名**：`pkg == target_pkg` → `IN_TARGET_APP`；`pkg` 非 launcher 且非目标 → `IN_OTHER_APP`；`pkg` 为 launcher 包 → 进第②层。
2. **第②层 桌面族细分**：`HOME_FIRST` / `HOME_OTHER` / `MINUS_ONE` / `NOTIFICATION` / `CONTROL_CENTER` 这些 pkg 相同或相近、无法靠包名区分，改用**真机采样帧提取的节点特征**（如负一屏含「小布建议」、通知栏含清除/日期控件等）判别。特征必须来自真机采样，不拍脑袋。
3. **第③层 机型适配**：launcher 包名与各页面特征因 ROM 而异。特征表按机型（或 launcher 包名）配置。本次只填这台 OPPO（launcher = `com.android.launcher`），配置结构预留机型扩展位。

**决策原则**：场景识别是确定性地基，不依赖 LLM 概率输出；LLM 只负责「在正确场景里干什么」。

## 4. 分阶段路线

- **阶段一（本设计文档聚焦，现在做）**：实现探针采样功能 → 采集 OPPO 桌面族各场景真帧 → 人工分析特征。
- **阶段二（后续单独 brainstorm）**：据特征实现场景识别层 + 场景驱动决策，收编/替换 PKG_GUARD，修死循环。阶段二须等阶段一拿到真帧、看清特征后再设计，避免悬在假设上。

## 5. 阶段一详细设计：探针采样

### 5.1 交互流程（延时抓帧）

1. App 主界面常驻新增「场景采样」卡片（无需解锁，方便逐场景反复采样）。
2. 卡片含：场景标签输入框（如 `home_first` / `minus_one` / `notification` / `control_center`）+「抓当前帧」按钮。
3. 点按钮后**倒计时 10 秒**（可配），期间用户手动滑到目标场景（含下拉通知栏/控制中心）。
4. 倒计时结束，App 自动抓当前帧 nodeTree，组成 `sample.capture` 消息（带 label）上报云端。
5. 云端网关收到后落盘 `server/data/samples/<label>-<ts>.json`，含 `pkg` / `activity` / `nodeTree` 原文。
6. 逐场景采完，一起分析落盘样本，提取判别特征。

**为何延时抓帧**：通知栏/控制中心是系统下拉浮层，前台不是 App，无法「切过去再回 App 点按钮」。延时给用户时间切场景，10 秒足够，且无需悬浮窗权限，最轻量。

### 5.2 改动范围

**Android 端**（`android/app/src/main/java/com/example/phoneagent`）：

- `ui/AgentScreen.kt`：主界面常驻加「场景采样」卡（标签输入框 + 按钮 + 倒计时提示）。
- `ui/MainViewModel.kt`：加 `onCaptureSample(label)`，启动 10 秒延时后触发抓帧。
- `net/WsClient.kt`：加 `sendSample(label)`。
- `accessibility/PhoneAgentService.kt`：暴露「抓当前帧 nodeTree」能力供采样复用（复用现有 perception 抓帧逻辑）。
- `protocol/Messages.kt`：加 `sample.capture` 上行消息类型（含 `label`）。

**云端**（`server/app`）：

- `protocol.py`：加 `SampleCapture` 上行类型（`type="sample.capture"`, `label`, `nodeTree`, `pkg`, `activity`, `ts`），并注册进 `_UPLINK_MAP` / `Uplink`。
- `gateway.py`：收到 `sample.capture` → 落盘到 `server/data/samples/<label>-<ts>.json`。
- 新建 `server/data/samples/` 目录。

**明确不动**：`decision.py` / PKG_GUARD / `session.py`。采样与决策完全解耦。

### 5.3 落盘格式（`server/data/samples/<label>-<ts>.json`）

```json
{
  "label": "minus_one",
  "pkg": "com.android.launcher",
  "activity": "...",
  "ts": 1784168979000,
  "device": "OPPO",
  "nodeTree": [ { "id": "...", "text": "...", "desc": "...", "className": "...", "bounds": [l,t,r,b], "clickable": false, "editable": false } ]
}
```

nodeTree 结构与现有 `Perception.nodeTree`（`protocol.py` 的 `Node`）完全一致，保证采样帧与决策时看到的一致。

## 6. 错误处理

- 采样时若无障碍服务未连接/未抓到节点 → App 提示「抓帧失败，请确认无障碍已开启」，不上报空帧。
- WS 未连接 → 采样按钮禁用（复用现有 `ConnectionState.CONNECTED` 判断）。
- 云端落盘失败（目录不可写等）→ 记日志，回一个失败提示（可选，MVP 阶段先记日志即可）。
- 下拉浮层可能抓不到节点（系统权限限制）：这是本次采样要**验证的核心未知数**，若抓到空/不全，样本如实落盘，作为「该场景不可靠识别」的证据，反过来影响阶段二场景清单。

## 7. 测试策略

- 云端：为 `protocol.py` 的 `SampleCapture` 解析加单元测试（合法/缺字段）；为 gateway 落盘加一个测试（收到 `sample.capture` 后 `server/data/samples/` 生成对应文件）。
- Android：采样为手动实机操作，本阶段不写自动化测试，靠实机逐场景验证落盘。
- 不引入对现有决策链路的回归风险（采样路径独立）。

## 8. 非目标（YAGNI）

- 本阶段不实现场景识别规则、不改决策、不修 PKG_GUARD（阶段二）。
- 不做多机型（小米等）采样与适配（先单机 OPPO）。
- 不做悬浮窗/adb 触发采样（延时抓帧够用）。
- 不做采样样本的自动特征提取（人工分析）。