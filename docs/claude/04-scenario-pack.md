# 04 · 场景包与 App 适配

> 源码：`server/app/scenario/{base,send_message,ui}.py`、`scenario/profiles/`

场景层把"业务知识"从内核里剥出来，做成**可插拔的场景包**。内核（见 02）只管
安全与时序，场景包管"这个任务该怎么做"。

## 三个角色

### 1. ScenarioPack（协议）

`base.py` 用 `typing.Protocol` 定义结构约束（不做 isinstance 检查）。一个场景包
= 意图匹配 + 目标解析 + 技能模板 + 前后置策略 + UI profile：

```python
class ScenarioPack(Protocol):
    name: str
    def matches(self, goal: str) -> float      # 意图匹配得分，0 = 不命中
    def resolve_target(self, goal: str)         # 解析目标（pkg + 标识 + bindings）
    def skills(self) -> list                     # 技能模板
    def pre_policies(self) -> list               # 决策前策略
    def post_policies(self) -> list              # 决策后策略
    def ui_profile(self, pkg) -> AppProfile|None # L2 UI 识别特征
```

`select_scenario` 遍历所有注册 pack，取 `matches()` 最高分那个。**全 0 分返回
`None`，走纯 LLM 通用模式**——注意此时内核的安全策略（预算/LoopGuard/确认）
依然生效，只是没有场景特化逻辑，**不硬失败**。这保证了对未适配的 App/任务也能
兜底运行。

### 2. AppProfile（纯数据）

`AppProfile`（pydantic BaseModel）承载单个 App 的 UI 识别特征，**只有数据没有
逻辑**：

```python
pkg / aliases / title_rid_keywords / send_button_keywords
    / search_hints / message_input_hints
```

它替代了旧代码里散落的硬编码。`profiles/` 目录下：

- `feishu.py` / `wechat.py`：飞书、微信的**完整** UI 关键词（微信目前是占位，
  标 TODO 待真机 `sample.capture` 探针校准）。
- `misc.py`：QQ / 钉钉 / 淘宝 / 京东 / 高德 / 电话 / 设置 等 16 个 App 的
  **最小 profile**——只有 `pkg + aliases`，无 UI 关键词。它们的作用是让
  `resolve_pkg` 能识别 goal 里的 App 名，从而让 `pkg_guard` 的 App 边界约束生效
  （防止任务跳出目标 App），但不参与聊天 UI 识别。

### 3. UI 识别 helpers（纯函数）

`ui.py` 是一组无副作用纯函数，关键词一律从 `AppProfile` 参数传入，与具体 App
解耦：

- `resolve_pkg(goal, profiles)`：从 goal 里按别名识别目标 App。
- `extract_target(goal)`：三层提取消息接收方——引号 > 书名号 > 结构化句式
  （"给 X 发消息"里的 X）。
- `is_send_button(node, profile)`：区分 rid 关键词与 label 关键词分流匹配，
  避免 "message_sender_avatar" 之类 rid 误判为发送按钮。
- `is_message_input(node, profile)`：**保守识别**聊天正文框——非 editable 直接
  False，命中 search_hints 判为搜索框返回 False，只有命中 message_input_hints
  才 True。宁可漏拦也不误拦搜索框。
- `resolve_anchor_node`：语义锚点解析（与端侧同语义，见 03）。

## SendMessagePack：一个完整场景包

`send_message.py` 是目前唯一的完整场景，实现"给 X 发消息"：

- `matches`：goal 能识别出聊天 App（飞书/微信）且含发送意图词（发/发送/发给…）
  时给 0.9 分。
- `resolve_target`：解出 `pkg` + `chat` + bindings（`{contact}` / `{query}`）。
- `skills`：飞书发消息模板（搜索 → 输入联系人 → **verify_title** → tap 发送）等。
- `classify_entry`：**保守**只识别"已在目标会话"一种可行动状态（用于 skill
  cursor 快进），其余一律 unknown——避免误判后在别人群里乱 back。

## 五道策略：安全护栏

场景包注入的策略是这套系统"不发错、不乱发"的护城河，从旧 `gateway.py` 抽取
并管道化（策略只返回 Verdict，不直接收发）：

**前置（PRE）：**

| 策略 | 作用 |
|------|------|
| `PreSendRevertPolicy` | AWAITING_CONFIRM 观察窗内用户切到桌面 → 视为撤回，abort |
| `PostSendForceDonePolicy` | 已 ack + 仍在目标会话 + 标题匹配 → 强制 done（无视 LLM） |
| `PostSendPatrolPolicy` | 发送 ack 后 LLM 还在操作，巡逻计数超阈值 → abort |

**后置（POST，读 `ctx.decided_actions`）：**

| 策略 | 作用 |
|------|------|
| `SendGuardPolicy` | 未真实发送就 done（幻觉 done）→ 拦截改发 read_screen，连续超阈值 abort |
| `ConfirmInterceptPolicy` | tap 发送按钮 + 标题匹配目标群 → **拦下不发**，转 `task.confirm` 走用户确认 |
| `WrongChatInputPolicy` | 往正文框输正文但标题不匹配（进错群）→ 拦截改发 back，超阈值 abort |

这三道后置策略共同实现了"**发送前必确认、错群绝不输正文、不许幻觉完成**"的
安全语义。其中 `ConfirmInterceptPolicy` 会把发送动作暂存进 `ctx.confirm`，迁移
到 AWAITING_CONFIRM，端侧弹 Toast 让用户 5 秒内可取消（配合 03 的
`UplinkConfirmResponse`）。

## 如何新增一个场景/App

1. **只加 App 识别**（让边界约束生效）：在 `profiles/misc.py` 加一个最小
   `AppProfile`（pkg + aliases）并注册进 `MISC_PROFILES`。
2. **加完整聊天适配**：写完整 `AppProfile`（含 UI 关键词，建议先用探针采样校准），
   放 `profiles/`。
3. **加新业务场景**：新建一个实现 `ScenarioPack` 协议的类，提供 matches /
   resolve_target / skills / pre_policies / post_policies / ui_profile，注册进
   场景列表即可。内核无需改动。

## 设计取舍小结

| 取舍 | 选择 | 理由 |
|------|------|------|
| 硬编码 App 特征 vs AppProfile 数据 | AppProfile | 数据与逻辑分离，易扩展/校准 |
| 无匹配即失败 vs 纯 LLM 兜底 | 纯 LLM 兜底 | 未适配也能跑，内核安全仍在 |
| 激进识别输入框 vs 保守识别 | 保守（漏拦不误拦） | 误拦搜索框会污染正文 |
| 直接发送 vs 确认拦截 | 确认拦截 | 发错不可逆，必须人确认 |

## 延伸阅读

- 技能模板如何回放/verify → [01-decision-engine.md](01-decision-engine.md)
- 策略管道机制 → [02-task-kernel.md](02-task-kernel.md)
- 锚点解析同语义 → [03-semantic-anchor.md](03-semantic-anchor.md)