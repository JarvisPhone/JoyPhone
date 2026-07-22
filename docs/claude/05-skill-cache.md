# 05 · 技能缓存与泛化沉淀

> 源码：`server/app/decision/cache.py`、`server/app/task/handlers.py:_learn_cache`

系统希望"做过一次的任务，下次更快、更省 LLM"。但**不能**简单地"一次成功就把
机械步骤录下来重放"——那会把当次偶然的坐标、导航路径、错群探索都固化成"技能"，
反而更危险。本篇讲这套缓存如何在**多次验证 + 泛化清洗 + 危险粗筛**三重门槛下，
把成功轨迹沉淀为可安全回放的技能。

## 一、为什么不能"一次 done 就固化"

一次成功任务的 `applied_steps` 里混着大量**当次偶然产物**：

- 从桌面进 App 的导航段（home/back）——每次落地页可能不同；
- 坐标 tap——坐标随机型/分辨率/列表滚动而变（见 03）；
- 进错群后又搜索纠正的探索动作——是失败的补救，不是通用路径。

直接录制这些 = 把噪声当经验。所以沉淀前必须先**泛化清洗**。

## 二、泛化：`generalize_steps`

`_learn_cache` 在任务成功时调用，先把原始 `applied_steps` 喂给
`generalize_steps(steps, target_pkg, bindings)` 清洗成通用轨迹，规则：

| 规则 | 目的 |
|------|------|
| 只留 `pkg == target_pkg` 的步骤 | 丢弃桌面导航段 |
| 只留 `ack ok` 的步骤 | 失败/未对账动作不入库 |
| 剔除 `home/back/read_screen/wait`（`_NAV_OPS`） | 导航/占位动作与"从哪进"强相关，不通用 |
| `tap` 只保留语义锚点（match_text/text/desc），坐标-only 丢弃 | 坐标不可复用（见 03） |
| `input` 文本若等于某个 binding 值 → 参数化为 `{placeholder}` | 让"给张三发"能泛化到"给李四发" |
| 返回 `[]` 表示无可学内容 | 调用方跳过沉淀 |

`_learn_cache` 之后还有两道守门：泛化后为空 → 跳过；**不含任何 tap** → 拒绝
（说明连发送类动作都没发生，不是完整成功路径）。

## 三、参数化与回放绑定：`bind_params`

泛化时把联系人名之类替换成 `{contact}`；回放时 `bind_params(params, bindings)`
用当场 bindings 把 `{placeholder}` 还原。**若绑定后仍残留 `{`，说明参数缺失，
返回 `None`，调用方放弃本次回放**——宁可回落 LLM 也不下发半成品步骤。

## 四、多次验证转正：candidate → active

`SkillCache.record_success(goal, context, steps)` 不是一次成功就固化：

- 轨迹按 `(goal, context)` 为 key 暂存为 **candidate**；
- 同 key 再次成功、且泛化序列**完全一致**才 `count + 1`；
- 序列不一致 → 用最新候选替换、计数归零（`CACHE_CANDIDATE_RESET`）；
- 累计达到 `Config.SKILL_LEARN_THRESHOLD` 才转 **active**（`CACHE_PROMOTE`）；
- `get()` **只返回 active**，candidate 绝不参与回放。

`context` 由任务层给出，形如 `com.ss.android.lark|target_chat`（pkg + 入口状态
分类，见 04 的 `classify_entry`）。**不同入口页各学各的路径**——从会话列表进和
已在会话里进，步骤本就不同。

## 五、危险粗筛：`_validate_steps`

转正前再过一遍安全粗筛，命中即拒绝并清除候选：

- `tap` 的 `match_text` 命中 `群设置/群公告/群管理/设置/group_setting/settings`
  等子串 → 判为"群设置探索"，拒绝（这类动作不该出现在发消息的正路里）；
- `input` 文本是**目标名片段**（去空格后 ≥4 字且是 goal 子串、且非占位符）→
  判为"进错群后再搜索纠正"的探索特征，拒绝。

这道粗筛专门防止把 03/04 里那些"错群补救探索"误学成技能。

## 六、回放侧与熔断（呼应 01/02）

- 回放由决策引擎 cache 级承担（见 [01](01-decision-engine.md)）：命中 active
  entry → 逐步下发 → cursor 对账推进。
- 单步失效（`mark_miss`）：**整条 entry 失效等待重新学习**（MVP 策略，不做局部
  修复）。
- 回放熔断：同一 cache 步连续失败达 `CACHE_STEP_MAX_FAILS` → 放弃回放、同帧
  回落 LLM（防"无限重放必败步骤"，见 02 的 cursor 对账）。

## 七、并发与持久化

- 写盘用全局 `threading.Lock` 保护 `_flush()`，JSON 落盘 `data/`。
- MVP 未做版本演进：active entry 一旦转正，后续成功不再改内容。

## 设计取舍小结

| 取舍 | 选择 | 理由 |
|------|------|------|
| 一次固化 vs 多次验证 | 多次验证转正 | 避免把偶然/失败路径当经验 |
| 录制原始步骤 vs 泛化清洗 | 泛化清洗 | 坐标/导航/探索是噪声 |
| 硬编码联系人 vs 参数化占位 | 参数化 | 一条技能泛化到不同接收方 |
| 单步修复 vs 整条失效 | 整条失效重学 | MVP 求简单可靠，避免部分损坏 |
| 无校验入库 vs 危险粗筛 | 危险粗筛 | 挡住群设置/错群探索污染技能库 |

## 延伸阅读

- 回放/熔断/cursor 对账 → [01-decision-engine.md](01-decision-engine.md)
- applied_steps 从哪来、ack 对账 → [02-task-kernel.md](02-task-kernel.md)
- 为什么坐标不可复用 → [03-semantic-anchor.md](03-semantic-anchor.md)
- classify_entry 与 context 分类 → [04-scenario-pack.md](04-scenario-pack.md)