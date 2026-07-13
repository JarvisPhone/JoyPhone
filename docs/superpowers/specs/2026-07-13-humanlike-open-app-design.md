# 真人式打开应用（移除 open_app 命令直启）设计

日期：2026-07-13
分支：feat/app-driven-goal（不 push）
状态：已批准，待实施

## 背景与动机

当前打开应用走 `open_app` 算子：端侧 `openApp` → `getLaunchIntentForPackage` → `startActivity` 命令直启，
若给的是 app 名则先 `resolvePackageByLabel` 枚举包名反查。这条路存在两个根本问题：

1. **不通用（像作弊）**：`startActivity` 直启不是真人操作，用户明确要求「在桌面上找到图标、点击图标」才通用。
2. **包名枚举被系统限制**：targetSdk≥30（本项目 36）下 `queryIntentActivities`/`getInstalledApplications`
   受 Package Visibility 过滤（实测 launchables=10，飞书 `com.ss.android.lark` 被过滤掉），
   需 `QUERY_ALL_PACKAGES`（上架高危）或硬编码 `<queries>`（用户已否决）。

**关键洞察**：无障碍权限本就能读当前屏幕完整 view tree（端侧早已 `rootInActiveWindow` +
`NodeFlattener.flatten` 上报），根本不需要枚举包名。正确做法 = 回桌面 → 读 view tree 找图标 →
tap；找不到就翻屏；翻到底还没有就放弃并提示用户。全程只用无障碍已有能力，不碰包名、不碰 startActivity。

## 目标

- 移除 `open_app` 命令直启（端侧算子 + 云端 op + prompt），代码不留作弊后门。
- 让云端 LLM 用「home 回桌面 → 找图标 tap → 翻屏 → 到底 abort」的真人式流程打开任意 app。
- 端侧保持「纯算子、不懂业务」；除桌面遍历的归位/线性扫描外，决策全云端 LLM。

## 非目标

- 不做常见 app 名→包名映射表（用户已否决）。
- 不引入 uiautomator dump（用户强令禁止），观测只用 view tree / screencap。
- 不做翻页手势的真机参数最终校准（留待联调阶段）。

## 整体架构与数据流

```
用户点按钮 → task.request(goal) ↑
云端 TaskStart ↓ → 端侧 taskActive=true → reportScreen ↑(view tree)
云端 engine.decide(LLM) → 决定单步 op ↓
  · 打开 app：home_first_page 归位第一屏 → 读屏找图标 → 命中 tap / 未命中 next_page
端侧执行 op → action.result(ok, atEnd) ↑
  · next_page / swipe 执行前后各拍一帧 view tree，一致=翻到底 → atEnd=true
云端 LLM 看 history 里的 {op, atEnd:true} → 判定图标找不到 → abort ↓
端侧收 TaskAbort → 现有 UI 链路提示用户"未找到目标应用"
```

原则：
- **端侧纯算子**：swipe/next_page 只多做「拍前后帧对比得出 atEnd」这一通用能力，不知道「在找图标」。
  例外：`home_first_page` 含「回桌面 + 连续 left 翻到头归位」这一半业务的端侧内部循环（B2 决策）。
- **决策在云端 LLM**：找图标/翻屏/放弃靠 prompt 引导。
- **提示用户复用现有链路**：走 TaskAbort → UI，不新增机制。

## 组件设计

### 1. 端侧 swipe「到底检测」（Executor.kt）

引入结构化返回类型替代裸 Boolean：

```kotlin
data class ExecResult(val ok: Boolean, val atEnd: Boolean = false)
```

- `execute(op, params)` 签名由 `Boolean` 改为 `ExecResult`。
- 除翻页类算子外，其它算子（tap/input/back/home/read_screen/wait）返回 `ExecResult(ok=..., atEnd=false)`。

**屏幕指纹对比**：
- 翻页前：对 `rootInActiveWindow` 用 `NodeFlattener.flatten` 得 nodeTree，取每节点 `text/desc/bounds`
  拼成字符串指纹（`fingerprint(nodes): String`，纯函数可单测）。
- 派发手势 → 等约 500ms 稳定（经验值，联调可调）。
- 翻页后再拍指纹。两次一致 → `atEnd=true`（翻不动/到底）；不一致 → `atEnd=false`。
- 用 text/desc/bounds 而非整树深比：轻量稳定，避免动画/时间戳微差误判。

### 2. 桌面遍历算子（B2：端侧归位 + 线性扫描）

**`home_first_page`（回桌面并归位第一屏）**：
- `performGlobalAction(HOME)` 回桌面。
- 连续 `swipe right`（向右滑=看左边屏）直到某次前后帧指纹一致（到最左第一屏）。
- 返回 `ExecResult(ok=true)`。含端侧「归位」半业务循环（200~500ms 间隔）。

**`next_page`（固定往右翻一屏）**：
- 执行一次 `swipe left`（向左滑=看右边屏）。
- 前后帧一致 → `ExecResult(ok=true, atEnd=true)`（已到最后一屏）；否则 `atEnd=false`。

LLM 找图标循环（prompt 引导）：
1. 打开 app → 先 `home_first_page` 归位第一屏。
2. 读当前屏节点找目标 app 图标：命中 → `tap`；未命中 →`next_page`。
3. `next_page` 回 `atEnd=true` 且当前屏仍无图标 → `abort`（未找到应用<名>）。

### 3. 协议 atEnd 字段（端云对称）

- 端侧 `UplinkActionResult` 加 `val atEnd: Boolean = false`。
- 云端 `ActionResult` 加 `atEnd: bool = False`。
- 均给默认 false，向后兼容。

### 4. 上报与消费链路

- 端侧 `WsClient.sendActionResult(actionId, ok, atEnd=false)`。
- `PhoneAgentService.onAction`：`execute` 返回 `ExecResult`，取 `ok`/`atEnd` 一起上报；
  日志 `↑ action.result <op> ok=.. atEnd=..`。
- 云端 `gateway.py` 处理 action.result：`history.append({"actionId":.., "ok":.., "atEnd":..})`，
  供 `engine.decide` → LLM 读取。

### 5. 云端决策改造（decision.py / protocol.py）

- `Action.op` 的 Literal：**删 `open_app`，加 `home_first_page`、`next_page`**。
- `_SYSTEM_PROMPT`：删 open_app 定义行与「看到飞书图标 → open_app」示例；
  写入 home_first_page → 找图标 → next_page → abort 的策略，
  明确 atEnd 含义，强调禁止假设包名 / 禁止命令直启，只能点真实可见图标。

## 死代码清理清单

- Executor.kt：删 `openApp`、`resolvePackageByLabel`、execute 中 `"open_app"` 分支。
- 删 `AppTarget.kt` 及 `AppTargetTest.kt`。
- AndroidManifest.xml：回退 `QUERY_ALL_PACKAGES`（tools namespace 若无其它用途一并回退）。
- 云端：删 `Action.op` 的 `open_app` + prompt 中 open_app 定义/示例。

## 测试策略（TDD 纯逻辑先行）

- 端侧单测：`fingerprint(nodes)` 生成 + 两指纹相等判定（纯函数）。
- 端侧序列化单测：MessagesTest 补 `atEnd` 序列化/反序列化断言。
- 云端单测：ActionResult 解析 atEnd；Action.op Literal 不含 open_app；gateway history 写入 atEnd。
- framework-only（真机验证，不写单测）：swipe 前后拍帧、home_first_page 归位循环、next_page 手势。

## 分 commit 计划（feat/app-driven-goal，不 push）

1. `refactor: 移除 open_app 命令直启（端侧 openApp/AppTarget/resolvePackageByLabel + 回退 QUERY_ALL_PACKAGES + 云端 op/prompt）`
2. `feat: action.result 增加 atEnd 字段（端云协议对称 + 序列化测试）`
3. `feat: swipe 到底检测（ExecResult + 屏幕指纹对比 + 单测）`
4. `feat: home_first_page/next_page 桌面遍历算子 + 云端 prompt 引导真人式打开 app`
5. （联调后）`fix: 真机翻页参数校准`

## 风险与待联调项

- 翻页手势能否真生效、指纹稳定等待时间、误判 atEnd —— 均需真机联调。
- 严禁 uiautomator dump；改 gateway/decision 后需重启 uvicorn。
- 重装 apk 可能致无障碍服务 / WS 短暂断连，联调需 app 前台确认已连接。
- 真实 LLM decide 较慢（60+秒/步），测试需耐心等待。