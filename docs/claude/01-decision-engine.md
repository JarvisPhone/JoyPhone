# 01 · 决策引擎分级回退

> 源码：`server/app/decision/{engine,types,skills,cache,pkg_guard,llm}.py`

## 核心契约

决策引擎的唯一入口是 `DecisionEngine.decide(input) -> Decision`。

`Decision` 是数据类（`decision/types.py`），`__post_init__` 断言 `actions` 非空——
**引擎恒定产出至少一个可执行动作**，永不返回"无事可做"。这条不变量是整个系统
"每帧必有响应"的地基：任务循环拿到的一定是能下发给端侧的动作。

```
Decision(actions: list[Action], source: str, meta: dict)
```

`source` 标识动作来自哪一级（cache / skill / pkg_guard / llm），既用于日志追踪，
也用于任务内核判断后续对账策略（例如 cache/skill 命中才推进 cursor）。

## 四级回退顺序

`decide()` 按"确定性从高到低、灵活性从低到高"依次尝试：

```
1. cache      —— 命中过往成功轨迹的当前步 → 直接回放，最快
2. skill      —— 场景技能模板 cursor 未 failed 且 misses < MAX → 按模板推进
3. pkg_guard  —— 不在预期场景（如误入负一屏/锁屏）→ 场景脱困动作
4. LLM        —— 前三级都不适用 → 大模型自由决策，兜底
```

任一级命中即返回，不再下探。这样设计的收益：

- **高频路径零 LLM 开销**：已学会的任务直接走 cache 回放，省 token、省延迟。
- **确定性优先**：cache/skill 是被验证过的确定路径，比 LLM 每帧重新推理更稳。
- **永不卡死**：LLM 作为最后兜底，保证任何未知界面都有决策。

## 关键细节

### cache 级：回放 + 熔断

- 命中的步骤只有经端侧 ack `ok` 后，才由 handler 调 `cursor.advance()` 推进。
- 同一步连续 ack 失败达 `CACHE_STEP_MAX_FAILS` 时，本场任务禁用该 cache，
  防止"无限重放一个必败步骤"（历史事故）。
- `_validate_steps` 粗筛危险动作：含"群设置/群公告"等子串的 tap、把目标名当
  搜索词的 input 片段等，避免回放被污染的轨迹。

### skill 级：cursor 推进与 verify 闸门

- 技能模板（`SkillTemplate`）是有序 `SkillStep` 列表，`BoundSkill.bind` 把
  `{contact}` 等占位符实例化为真实参数；未能绑定则返回 `None`（不残留占位符）。
- `SkillCursor` 逐步推进：命中步 ack ok → `advance()`；`verify_title` 步一旦
  FAIL（当前会话标题不匹配目标）→ `cursor.fail()`，**同帧回落到 LLM**，
  而非继续往下 tap 发送——这道闸门堵住了"进错群还继续发"的致命路径。
- cursor 累计 miss 达上限或已 failed，则该级不再命中，交给下一级。

### pkg_guard 级：场景状态机脱困

详见 `pkg_guard.py`，识别 8 种场景（HOME / MINUS_ONE / NOTIFICATION /
CONTROL_CENTER / IN_APP / LOCK_SCREEN / RECENT_APPS / UNKNOWN），当设备漂到
非预期场景时产出脱困动作（三级阶梯：LLM 脱困 → 机械降级 → abort）。

### LLM 级：语义锚点解析 + 节点裁剪

`_llm_decide` 是兜底核心，几个要点：

- **系统提示（`_SYSTEM_PROMPT`）** 明确硬约束：App 边界（不得跳出目标 App）、
  负一屏识别、`done` 的四条件、`idle` 行为约束等。
- **节点裁剪**：`_cap_nodes` 把节点数压到 `MAX_LLM_NODES=80`，优先保留可交互节点，
  控制 prompt 体积。
- **语义锚点抽取**：LLM 输出 tap/input 后，从命中节点提取 `match_text[:50]` /
  `match_rid` / `occurrence` 作为**语义锚点**下发，**绝不注入坐标**（见 03 文档）。
  完全匿名的节点才走 `tap_at` 坐标逃生舱。
- **批处理截断**：解析动作序列时遇到首个 tap/input 即 `break`，一帧只下发到第一个
  变更动作为止，把后续判断交还给"下一帧感知 + 对账"，避免连发导致的失控。

## LLM 客户端抽象

`llm.py` 提供 `LLM` 抽象接口：

- `FakeLLM`：测试用，返回预置脚本，让 CI 无需真实模型即可跑决策链路。
- `RealLLM`：接真实模型，`_clean_text` 会剥掉 `<think>...</think>` 之类推理标签，
  只保留可解析的结构化输出。
- `build_llm` 按配置构造，实现了"测试/生产"无缝切换。

## 设计取舍小结

| 取舍 | 选择 | 理由 |
|------|------|------|
| 命中即返回 vs 全级合议 | 命中即返回 | 简单、可预测、省算力 |
| 坐标 vs 语义锚点 | 语义锚点 | 帧过期坐标会点歪（错群事故根因） |
| 一帧连发 vs 单动作截断 | 单动作截断 | 每步都经真实反馈对账，可控 |
| verify 失败继续 vs 回落 LLM | 回落 LLM | 堵住"进错群还发送"的致命路径 |

## 延伸阅读

- 决策产出后如何被策略拦截/放行 → [02-task-kernel.md](02-task-kernel.md)
- 锚点在端侧如何重定位执行 → [03-semantic-anchor.md](03-semantic-anchor.md)
- cache 轨迹如何泛化沉淀 → [05-skill-cache.md](05-skill-cache.md)