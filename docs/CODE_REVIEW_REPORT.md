# JoyPhone 深度代码审查报告

> 审查版本：**v4.0（架构重构验收版）**
> 审查时间：2026-07-21
> 当前 HEAD：`bd22947`（merge：全面架构重构 L0 内核 + L1 场景包 + L2 AppProfile，协议 v2）
> 上一版基线：`5a7bbfa`（重构前，v3.0 报告基线）
> 审查范围：`server/`（协议 / 网关 / 任务内核 / 场景包 / 决策引擎 / 基础设施）+ `android/`
> 验证方式：逐文件精读当前源码 + `grep` 核验调用点 + 运行全量测试（`207 passed`）

---

## 〇、重构验收总览

v3.0 报告列出的一批 P0/P1/P2 问题，在本轮重构中已被**系统性解决**。重构落地了六层分层管道架构：

```
protocol/   协议模型与编解码（v2）
gateway/    连接封装 + 上行路由
task/       任务内核：TaskContext / TaskFSM / Policy 管道 / handlers
scenario/   场景包（L1）+ AppProfile（L2）
decision/   决策引擎 + 技能绑定 + cache + pkg_guard + LLM
infra/      config / metrics
```

核心结论：**这是一次高质量的架构级重构**。状态收拢、契约诚实、语义修复三条主线都落到实处，测试从 162 增至 207 且全绿。以下逐条验收 v3.0 遗留问题。

### v3.0 问题修复对账表

| 编号 | v3.0 问题 | 状态 | 证据 |
| --- | --- | --- | --- |
| P0-2 | 技能占位符从未实例化 | **已修复** | [`BoundSkill.bind`](server/app/decision/skills.py) 对 `_BIND_FIELDS`(input_text/match_text/text/desc) 替换 `{key}`，残留 `{` 则 warn 并返回 None 放弃技能 |
| N2 | verify_title FAIL≈PASS | **已修复** | [`engine._skill_step`](server/app/decision/engine.py) FAIL 调 `cursor.fail()`+return None 回落 LLM；PASS 返 read_screen；cursor 仅在 ack ok 且 source∈(cache,skill) 时 advance |
| N3 | task.request 漏重置状态 | **已修复** | [`TaskStore.new_task`](server/app/task/context.py) 整体新建 TaskContext（全字段 default_factory），state 走 `fsm.force(RUNNING)` |
| N4 | decide 签名说谎 | **已修复** | [`decide`](server/app/decision/engine.py) 恒返回 `Decision`，无决策回落 `Decision([read_screen],"llm")` |
| N5 | 节点未回收 | **已修复** | Android 侧 input 按坐标定位 + 节点回收（重构提交） |
| P2-6 | metrics.start_task 参数错位 | **已修复** | [`handlers`](server/app/task/handlers.py) 传 `ctx.target_pkg` 作 pkg；pkg_guard 决策不计 llm_call 防虚增 |
| — | seq 未消费 | **已修复** | perception 入口 `seq <= last_consumed_seq` 丢弃乱序/重复帧 |
| — | atEnd 契约漂移 | **已修复** | 协议 v2 已删除该字段 |
| — | WS_URL 硬编码 | **已修复** | 移入 BuildConfig；服务端 `?v=` 版本握手，不符回 4402 |
| P2-5 | requires-python=3.14 锁死 | **维持不改** | 见下文「三、遗留 / 待观察」，属明确取舍非缺陷 |

---

## 一、重构后代码质量评估

### 亮点

1. **状态收拢彻底**：[`TaskContext`](server/app/task/context.py) 是唯一 per-task 载体，所有字段 `default_factory` 初始化，`new_task` 整体重建——根治了 N3 类「重置遗漏」。
2. **契约诚实**：`decide` 恒返 `Decision`（source/meta 可观测）；`parse_uplink` 对非 JSON / 非 object / 未知 type 统一抛 `ValueError`，由 [`route_loop`](server/app/gateway/router.py) 转 `TaskAbort(invalid_uplink)`，不静默吞。
3. **状态机通用化**：[`TaskFSM`](server/app/task/fsm.py) 六态 + `_ALLOWED` 迁移表 + `transition`（非法返 False 不抛）/`force`（绕表记 history），迁移全程留痕。
4. **策略管道**：[`run_pipeline`](server/app/task/policies.py) 首个非 continue 短路，内核安全策略（Budget/ConfirmTimeout）与场景策略解耦。
5. **cache 失败路径防污染**：[`SkillCache.learn`](server/app/decision/cache.py) 静态校验，含「进群设置」危险 tap、「把目标名当搜索词」的错群 input 特征，拒绝固化失败路径。
6. **pkg_guard 场景状态机**：[`detect_scene`](server/app/decision/pkg_guard.py) 用 resource-id 后缀 + workspace bounds 判据区分 8 个场景，配三级脱困阶梯（LLM→机械降级→abort），根治 launcher 兜圈死循环。

### 二、新代码中发现的次要问题（P2 / N 级，均非阻断）

| 级别 | 位置 | 问题 | 建议 |
| --- | --- | --- | --- |
| N | [`handlers._dispatch`](server/app/task/handlers.py) | `actions` 参数缺类型标注 | 补 `list[Action]` |
| N | [`send_message.py`](server/app/scenario/send_message.py) skills | feishu_send_message 的 keywords 中「发给」重复出现两次 | 去重 |
| N | [`PostSendPatrolPolicy`](server/app/scenario/send_message.py) | `inspect` 内自增 `patrol_count`，策略有副作用（非纯函数），与其他 policy 的纯判定风格不一致 | 若追求一致性可把计数移出 inspect；当前可用但需注释说明 |
| N | [`ConfirmInterceptPolicy`](server/app/scenario/send_message.py) | 返回 `intercept([])` 空动作 + handler 据 `confirm_id` 改发 TaskConfirm，是隐式约定（空 intercept 语义特殊） | 已有注释，建议在 Verdict 层显式表达「需要外发确认」意图 |
| 观察 | [`WECHAT_PROFILE`](server/app/scenario/profiles/wechat.py) | 关键词注释标注「暂与飞书相同待真机校准」 | 真机采样后校准 |

### 已复核为「非问题」的点

- **`_profile_for` 只认 FEISHU/WECHAT**：这是**合理设计**，非 bug。send_message 的 UI 识别策略只对飞书/微信备有关键词，其他 app（misc 中 16 个）在 [`resolve_pkg`](server/app/scenario/ui.py) 中仅用于 pkg 边界约束，`_profile_for` 返回 None 会走通用 LLM 路径，属保守失败方向。

---

## 三、遗留 / 待观察

1. **`requires-python = 3.14`（P2-5 维持）**：重构明确选择不动。风险是协作/CI 环境需锁定 3.14，运行环境已验证（`207 passed`）。若需扩大协作面，建议放宽下限至 3.11+ 并在 CI 加多版本矩阵——**这是取舍不是缺陷**。
2. **真机关键词校准**：微信 profile 关键词待真机采样验证，飞书路径已相对成熟。
3. **cache 危险子串为硬编码启发式**：`_DANGER_TAP_TEXT_SUBSTRINGS` 是经验规则，随场景扩展可能需要维护。

---

## 四、测试覆盖

- 全量 **207 passed**（v3.0 为 162），新增覆盖：fsm / policies / task_context / scenario_base / scenario_ui / send_message_pack / send_message_policies / decision_types 等重构模块。
- `test_import_order.py` 守护分层依赖方向，防止层间反向 import——架构约束被测试固化，是重构可维护性的关键保障。
- 契约测试（`test_contract.py` / `test_protocol.py`）覆盖 v2 协议编解码。

---

## 五、结论

本轮重构**验收通过**。v3.0 报告的 P0-2 / N2 / N3 / N4 / N5 / P2-6 及 seq/atEnd/WS_URL 等问题均已修复并有测试佐证；架构从「状态散落 + 契约说谎」演进为「状态收拢 + 契约诚实 + 分层管道」，代码可读性与可测性显著提升。

剩余项均为 P2/N 级细节（类型标注、关键词去重、策略副作用注释、真机校准、Python 版本取舍），不阻断功能，可在后续迭代中渐进处理。建议下一步聚焦真机采样以校准微信/飞书关键词与 cache 启发式规则。