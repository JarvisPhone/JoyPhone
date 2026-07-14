<div align="center">

# JoyPhone

### 说一句话，手机自己干。

一个端云协同的开源 AI 手机代理 · 云端当大脑，手机当手眼

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-≥3.14-3776AB.svg)](https://www.python.org/)
[![Kotlin](https://img.shields.io/badge/kotlin-2.x-7F52FF.svg)](https://kotlinlang.org/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](#-贡献)

</div>

---

JoyPhone 是一个**端云协同的开源 AI 手机代理**：云端大模型作「大脑」决策，安卓真机以无障碍权限（`AccessibilityService`）作「手眼」操控任意 APP。无需任何厂商 SDK，无需 root，无需厂商配合——像人一样看屏幕、点按钮、敲输入框、翻页滚动。你只需一句话，剩下的交给它。

灵感来自豆包手机这类「语音一句话操控整机」的设想，但走的是**完全开源、端云协同、模型可替换**的路线：不绑定任何一家厂商的大模型，不锁定任何一款手机品牌，把「让 AI 像人一样用手机」这件事变成一个**人人可参与、可复现、可迭代**的开放项目。

> 长期愿景：用户对着手机说一句话——「给妈妈发微信说我今晚回家吃晚饭」「打开抖音搜一下最近的猫咪视频」「把上次会议的纪要转发到工作群」——手机自己听懂、自己点开、自己输入、自己确认。不再一层层翻菜单，不再跨应用搬数据，不再把人困在小屏幕上做重复劳动。

## 核心亮点

1. **零 SDK 依赖**：基于安卓无障碍权限操控任意真实 APP UI，绕开厂商封禁与限流，一套方案覆盖飞书 / 企微 / 微信 / 短信 / 抖音等全社交通道，抗风控、不挑品牌。
2. **端云协同「手眼脑」分离架构**：手机只负责感知（节点树 + 截图）与执行（点击 / 输入 / 滑动），云端负责多模态大模型决策——决策可热更、模型可替换、算力无上限，迭代成本远低于端侧集成方案。
3. **技能库自沉淀护城河**：每次成功操控的步骤序列被自动固化为可复用「技能」，命中即脚本执行、未命中回退大模型探索；越用越快、越用越准，社区共建技能库形成长期飞轮。
4. **语音一句话驱动**（路线图）：从纯文本目标向「语音指令 → 云端 ASR → 决策 → 协商」演进，目标是像豆包手机一样一句话搞定复杂多步跨应用操作，但完全开源、模型自选。

## 架构总览

```
┌──────────────────────── 云端 (FastAPI + Python) ─────────────────────────┐
│  任务管理 │ WS网关+会话状态机 │ 决策引擎 │ 协商机器人 │ LLM抽象层 │ 技能库 │
└────────────▲──────────────────────────────┬──────────────────────────────┘
             │ WebSocket（感知↑ / 动作↓）   │
             │  双向实时长连接              │
┌────────────┴──────────────────────────────▼──────────────────────────────┐
│                    安卓端 (Kotlin / AccessibilityService)                 │
│      感知模块（节点树+截图）   │   执行模块（点击/输入/滑动）            │
│      事件监听（新消息上报）     │   连接管理（断线重连）                  │
└───────────────────────────────────────────────────────────────────────────┘
                         ↑ 操控真实 APP（飞书/企微/微信/抖音…）
```

两端通过 WebSocket 双向实时通信：

- **上行**（App → 云端）：`perception`（节点树 + 截图）、`action.result`、`event.newMessage`、`heartbeat`、`task.request`
- **下行**（云端 → App）：`task.start`、`action`、`task.done`、`task.abort`

会话状态机：`NAVIGATING → IN_CHAT → SENT → WAITING_REPLY → NEGOTIATING → DONE / ABORT`，由 `server/app/session.py` 约束合法转移并设步数预算防失控。

## 路线图

JoyPhone 是一个长期演进的开源项目，按里程碑推进：

| 阶段 | 目标 | 状态 |
|------|------|------|
| M1 端云协同最小闭环 | 文本目标 → 真机无障碍操控 → 决策 + 执行 + 回报 | ✅ 已跑通 |
| M2 技能自沉淀 | 成功路径自动固化「技能」，命中即脚本回放 | ✅ 雏形 |
| M3 多 APP 接入 | 微信 / 企微 / 抖音等节点适配与技能库 | 🚧 进行中 |
| M4 语音一句话驱动 | 云端 ASR → 意图解析 → 决策，像豆包手机一样开口即用 | 🔜 规划 |
| M5 多设备并发调度 | 一台云端管多台手机，运营后台与任务队列 | 🔜 规划 |
| M6 WS 网关高性能化 | Rust 重写网关，承压更多设备并发 | 🔬 研究 |
| M7 语音外呼 / 呼叫中心 | 接入呼叫中心，AI 主动呼出与对方多轮语音协商 | 🔬 研究 |

## 仓库结构

```
JoyPhone/
├── server/                 # 云端：FastAPI + Python ≥3.14
│   ├── app/
│   │   ├── gateway.py        # WebSocket 网关 + 单任务会话主循环
│   │   ├── decision.py       # 决策引擎（缓存→技能→LLM 三级回退）
│   │   ├── protocol.py       # 上下行消息协议（Pydantic 模型）
│   │   ├── session.py        # 会话状态机 + 步数预算
│   │   ├── llm.py            # LLM 抽象层（FakeLLM / RealLLM）
│   │   ├── skills.py         # 静态技能库
│   │   ├── skill_cache.py    # 运行期自学习技能缓存
│   │   └── negotiation.py    # 协商机器人
│   ├── tests/                # pytest 单元/集成测试 + 回放夹具
│   ├── scripts/e2e_feishu.sh # 真机端到端联调脚本
│   ├── pyproject.toml
│   └── .env.example          # LLM 配置模板（OpenAI 兼容接口）
│
├── android/                # 安卓端：Kotlin + Compose + Hilt
│   └── app/src/main/java/com/example/phoneagent/
│       ├── accessibility/   # PhoneAgentService / Executor / Perception / NodeFlattener …
│       ├── net/             # WsClient / WsDispatcher（长连 + 断线重连）
│       ├── protocol/        # 与云端对齐的序列化模型
│       ├── domain/          # TaskState / TraceEvent / ActionLog
│       ├── data/            # AgentStateRepository（调试面板状态）
│       ├── ui/              # AgentScreen / DebugPanel / MainViewModel（Jetpack Compose）
│       └── MainActivity.kt
│
└── docs/
    └── superpowers/         # 设计与实施计划（specs / plans，按日期归档）
```

## 云端设计要点

### 决策引擎三级回退（`server/app/decision.py`）

每收到一帧感知，按以下优先级产出下一步动作：

1. **技能缓存命中**：按 `(goal, pkg)` 查 `SkillCache`，命中则按已沉淀步骤序列回放；若某步无法在当前节点树重定位则回退下一级。
2. **静态技能库**：按 `skill_name` 查 `SkillLibrary`，按 `match_text` 在当前节点树定位节点回放。
3. **大模型推理**：把任务目标 + 结构化屏幕状态（`[序号] 类型 "文本"`，可交互节点优先，最多 `MAX_LLM_NODES=80`）+ 动作历史交给 LLM，要求其只输出一个 JSON 动作对象。

LLM 决策的 `tap` 会在云端先用节点 `id` / `match_text` 解析为精确坐标中心再下发，避免端侧全屏子串匹配误命中（如负一屏磁贴）。System prompt 内置「负一屏识别」「桌面翻屏找应用」等常识约束。

### LLM 抽象层（`server/app/llm.py`）

- `FakeLLM`：按预设响应序列回放，供离线 / CI 测试。
- `RealLLM`：基于 OpenAI 兼容 SDK，默认对接 MiniMax-M2.x（`extra_body={"thinking":{"type":"disabled"}}` 关闭推理）；自动剥离 `` 推理段、提取首个平衡 JSON，保证下游 `json.loads` 可用。**任何 OpenAI 兼容的模型（豆包 / DeepSeek / Qwen / 自部署 vLLM 等）改一行配置即可接入。**
- 无 `LLM_API_KEY` 时自动退化为 `FakeLLM`，开箱即跑，不依赖任何外网服务。

### 技能自沉淀（`server/app/skill_cache.py`）

任务以 `done` 正常结束时，把本轮 `applied_steps` 以 `(goal, pkg)` 为键写回缓存；下次同目标同应用直接脚本回放，不耗 LLM 配额。某步无法重定位则整条失效等待重新学习——MVP 策略简洁可靠，也是社区共建技能库的底层原语。

## 安卓端设计要点

### `PhoneAgentService`（`accessibility/PhoneAgentService.kt`）

继承 `AccessibilityService`，是无障碍服务核心：

- `onServiceConnected` 时启动 WebSocket、注册回调，按 `ANDROID_ID` 作设备号上报。
- 收到 `task.start` 后首帧感知上报；后续窗口变化经 `DEBOUNCE_MS=400` 去抖再上报，避免抖动。
- `onAccessibilityEvent` 仅在 `taskActive` 时响应；`action` 带只读调试模式（目标以 `[DEBUG-ONESHOT]` 前缀触发）：只上报一帧、不执行返回动作，便于人工导航到目标页面后单帧验证云侧决策。
- 默认连接地址写在 `PhoneAgentService.WS_URL` 常量，按你的环境修改。

### `Executor`（`accessibility/Executor.kt`）

把云端动作指令翻译为无障碍 API 调用：

- `tap`：优先按云端下发的 `x/y` 坐标 `dispatchGesture` 点击，缺失时回退 `match_text` 子串匹配节点中心点击。
- `input`：找到首个可编辑节点执行 `ACTION_SET_TEXT`。
- `swipe` / `back` / `home`：标准手势与全局动作。
- `home_first_page` / `next_page`：桌面翻屏算子，用「翻页前后屏幕指纹一致」判定是否已到最左第一屏 / 最后一屏（`atEnd`），让 LLM 像真人一样翻桌找应用图标。坐标几何全部抽到可单测的 `GestureGeometry`。

### 感知与节点裁剪（`accessibility/NodeFlattener.kt` / `Perception.kt`）

读取 `rootInActiveWindow` 节点树，只保留可见且含文本 / 可交互的节点，序列化为与云端协议对齐的 `Node` 列表上传，显著降低链路负载与 LLM token 成本。

### 技术栈

Jetpack Compose（单 Activity + Compose UI）+ Hilt（`@AndroidEntryPoint` 注入 `WsClient` / `AgentStateRepository`）+ OkHttp WebSocket + kotlinx.serialization。`minSdk=26 / targetSdk=36 / JVM 17`。

## 快速开始

### 云端

```bash
cd server
cp .env.example .env            # 填入 LLM_API_KEY（任何 OpenAI 兼容接口）
# 建议 Python ≥3.14，使用 uv：uv sync
uv run uvicorn app.gateway:create_app --factory --host 0.0.0.0 --port 8000
```

无 `LLM_API_KEY` 时自动用 `FakeLLM`，可离线跑通协议链路。

### 安卓端

1. USB 连接真机（`minSdk≥26`），`adb devices` 确认可见。
2. 在 `android/local.properties` 配置 SDK 路径（已 gitignore）。
3. Android Studio 打开 `android/` 工程，Run `app`。
4. 系统设置 → 无障碍 → 启用「PhoneAgent」服务。
5. 修改 `PhoneAgentService.WS_URL` 指向你的云端地址。

### 真机端到端联调

```bash
server/scripts/e2e_feishu.sh
# 重绑无障碍服务触发 WS 连接 → 回桌面 → 打开飞书 → 观察 uvicorn 日志的 perception / decided op 输出
```

App 内顶部「任务目标」输入框下发自然语言目标（如「在飞书给张三发消息：明天上午开会」），`task.request` 上行后云端开始决策循环。

## 测试

```bash
cd server
uv run pytest                          # 全量
uv run pytest tests/test_decision.py  # 决策引擎单测
PHONEAGENT_FAKE_LLM='[...]' uv run pytest tests/test_gateway_loop.py  # 注入假 LLM 跑网关主循环
```

安卓单元测试位于 `android/app/src/test/`，覆盖 `GestureGeometry` / `NodeFlattener` / `Perception` / `ScreenFingerprint` / `WsDispatcher` / `MainViewModel` 等可纯逻辑验证的部分。

## 关键可测性设计

真机采集的感知序列存为「回放夹具」（如 `server/tests/fixtures/feishu_happy_path.json`），云端可离线回放完整决策闭环——**不依赖真机即可在 CI 中反复验证 AI 决策逻辑**。这是项目的质量底座与 TDD 落点，也是「端侧不可控、云侧可复现」的关键工程自律。

## 🤝 贡献

JoyPhone 是一个**完全开源**的项目，欢迎任何形式的贡献——一行代码、一个技能、一个新 APP 的节点适配、一个 bug 报告、一段文档优化，都会让这个项目离「说一句话，手机自己干」更近一步。

### 我能贡献什么

- **云端**：决策引擎、协商机器人、新 APP 的技能库、LLM 适配、WS 网关性能优化、测试与回放夹具。
- **安卓端**：节点裁剪算法、新 APP 的无障碍适配、手势执行、断线重连、UI 调试面板。
- **技能库**：把你跑通的某条「目标 → 成功步骤序列」沉淀下来，成为人人可复用的技能。这是社区共建飞轮的核心。
- **文档**：README 优化、架构图、使用教程、新 APP 接入指南。
- **测试**：补充单测 / 集成测试、增加边界场景回放夹具。

### 如何提 PR

1. **Fork** 本仓库到你的 GitHub 账号。
2. 从 `main` 拉一条特性分支：

   ```bash
   git checkout -b feat/your-feature
   ```

3. 做改动，保持每个 commit 聚焦一件事，遵循 [Conventional Commits](https://www.conventionalcommits.org/) 风格，例如：

   ```text
   feat(decision): 支持微信聊天页节点裁剪
   fix(android): 修复断线重连偶发 NPE
   test(server): 增加飞书 happy path 回放夹具
   docs: 补充新 APP 接入指南
   ```

4. 提交前确保本地通过校验：

   ```bash
   # 云端
   cd server && uv run pytest
   # 安卓端
   cd android && ./gradlew test
   ```

5. Push 到你的 fork，向 `main` 提交 **Pull Request**：

   - **标题**用 Conventional Commits 格式（如 `feat(android): 支持微信发消息技能`）。
   - **描述**说明：解决了什么问题 / 为什么这么做 / 怎么测试的。如果改动决策逻辑，附一段回放夹具或日志更佳。
   - 如果 PR 对应某个 issue，请关联（`Closes #123`）。

6. 等待 review。小改动通常当天合入；涉及决策主循环或协议变更的会多轮讨论。

### PR 约定

- **一个 PR 一件事**：混合多个无关改动的 PR 拆成多个。
- **保持可测**：新逻辑尽量配单测；真机相关改动附日志或回放夹具。
- **不改协议格式**：需要扩展上下行消息协议时，先开 issue 讨论向后兼容方案。
- **不引入强依赖**：云端遵循 `pyproject.toml`，安卓端遵循 `libs.versions.toml`，不擅自加大依赖体积。
- **安全**：不 commit 任何密钥、`.env`、`local.properties`，不引入可能外泄设备信息的代码。

有任何想法也欢迎先开 [Issue](../../issues) 讨论，避免重复工作或方向跑偏。早期阶段我们对方向保持开放，「先沟通，再动手」远比闷头改一通更高效。

## 设计与计划文档

历史的设计与实施计划按日期归档在 `docs/superpowers/`（`specs/` 设计稿 / `plans/` 实施计划），便于追溯演进脉络。

## License

本项目基于 **MIT License** 开源，欢迎自由使用、修改、分发。社区贡献默认遵循 MIT 授权。