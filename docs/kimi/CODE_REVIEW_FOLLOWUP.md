# JoyPhone 三次代码审查报告（Kimi）

> **审查时间**: 2026-07-20
> **审查基准**: `docs/CODE_REVIEW_REPORT.md`（v1.0）→ 修复 `c85fa2a` → 本报告 v1.0（2026-07-17）→ 后续修复 `5b874d6` / `f4161ae` / `5a7bbfa`（当前 HEAD，工作区干净）
> **审查方式**: 全量源码精读 + 服务端测试实跑（**162 passed, 0 failed**）+ Android 单元测试实跑（**BUILD SUCCESSFUL**）+ 关键路径调用点核验
> **本文档定位**: v1.0 的原地更新版。逐条核验 v1.0 结论在当前代码上的状态（已修复 / 部分修复 / 未修复 / 修复引入回退），并补充本轮新发现问题，作为后续代码修改的前置依据。

---

## 〇、两版本文档结论核验总览

### 0.1 v1.0 报告判对的（当前代码证实属实）

- P0-2 技能模板 `{contact}`/`{query}` 从未实例化 —— **仍属实**（`skills.py:73,76,87`，`next_step()` 无参数绑定环节）。
- seq 只加字段不消费、`action.result.seq` 恒 0 —— **仍属实**（`WsClient.kt:123-125` 未传 seq；云端无乱序检测）。
- `pendingConfirmCancelled` 声明了从不置位 —— **仍属实**（`PhoneAgentService.kt:58`，全库无置 true 点）。
- `check_awaiting_confirm_timeout()` 零调用点 —— **仍属实**（`session.py:91`，仅测试外无任何调用）。
- `GatewayConfig` 建了不用 —— **仍属实**（仅 `DEFAULT_GOAL` 被引用，`gateway.py:66`）。
- `skill_name` 死逻辑迷宫 —— **仍属实**（`gateway.py:486`）。
- 心跳回 `read_screen` 空转 —— **仍属实**（`gateway.py:196-200`）。
- 硬编码 WS_URL 内网 IP —— **仍属实**（`PhoneAgentService.kt:35`）。
- P1-2 守卫补丁驱动状态流转、P2 系列（pkg 子串误伤、Executor.input 首个 editable、双 LLM 实例、metrics pkg 错传、inline import time 等）—— **均仍属实**，位置见下文表格。

### 0.2 v1.0 报告判对的、且此后已修复的

| v1.0 条目 | 修复 commit | 当前状态 |
|-----------|-------------|----------|
| P0-1 `decide()` 返回 None 崩溃 | `f4161ae` | ✅ 崩溃已防（`gateway.py:499-503`），但**引入新回退 N2**，且类型契约仍在说谎（见 N4） |
| P0-3 步数预算失效 | （含于后续提交） | ✅ `session.record_step()` 已接线（`gateway.py:508`），每次决策计一步，`test_gateway_budget_exhausted_aborts` 转绿 |
| P1-1 task.request 状态重置不完整 | `5a7bbfa` | ⚠️ 局部修复：v1.0 点名的 9 个散变量已全部重置（`gateway.py:206-227`），但**漏了 Session 内部 3 处状态**（见 N3） |
| 4 个红测试 | `5b874d6` | ✅ 162 passed / 0 failed；但修复方式引入新问题 N1（FakeLLM 重复定义） |
| P2-5 前半：`decision.py` Optional 未导入 | `5b874d6` | ✅ 已导入（`decision.py:4`）；后半 `gateway.py:133` 的 `Node` **仍未导入** |

### 0.3 v1.0 报告需要修正/补充的

- v1.0 称「修复过程没有跑测试验证」—— 对 `c85fa2a` 成立；但后续 `5b874d6`/`f4161ae`/`5a7bbfa` 三个 commit 把测试修绿了，**当前测试全绿**（162 passed）。测试纪律问题已从「红测试提交」转为「绿测试下仍有空城计」（见 N2/N3/N4，均无测试锁住行为）。
- v1.0 P0-1 建议「返回 `[]` 或 LLM 回落」—— 实际落地是 read_screen 兜底，**语义与 decision.py 日志宣称的「回退 LLM 决策」不一致**（N2）。
- v1.0 称 gateway 688 行 —— 当前 **710 行**，单点问题继续恶化。

### 0.4 原报告（v1.0 docs/CODE_REVIEW_REPORT.md）结论的当前有效性

原报告的大部分条目已被 v1.0 覆盖核验，此处只补充变化：
- 原 P0「修复 confirm 超时竞态」：标志已加但从不置位，**竞态防护仍未生效**，兜底仍靠云端 state+confirmId 校验（`gateway.py:234-246`）——维持 v1.0「假修复」判定。
- 原「状态转移无历史记录」：`_state_history` 已实现（`session.py:53,75`），但 `gateway.py:204` 直接赋值绕过 `transition()` 的盲区**仍在**。
- 其余条目（架构、协议、质量）判定与 v1.0 一致，不再重复。

---

## 一、当前仍成立的问题清单（按优先级，含位置核验）

### P0 — 生产路径实质损坏

#### P0-2（沿用编号）: 技能模板变量从未实例化 —— 技能系统仍全损

`skills.py:73,76,87` 的 `{contact}`/`{query}` 占位符无任何绑定环节：`SkillLibrary.next_step(skill_name, nodes, cursor)` 签名不含 goal/target，模板原样下发：

- cursor=2 的 input 步会把字面量 `{contact}` 敲进搜索框；
- cursor=3 的 verify_title 步期望标题为字面量 `{contact}`，**永远失败**。

叠加 N2 后行为变为：verify 必败 → read_screen 兜底 → cursor 照样 +1 → 直接跳到 cursor=4「tap 发送」——**在不含任何消息正文的情况下点发送**。三级回退的中间一级从未可用，目前全靠 LLM 兜底；`record_skill_hit` 指标（`gateway.py:510-511`）持续产生误导。

**修法**: `next_step()` 增加 `bindings: dict` 参数（gateway 用 `extract_target(goal)` 的结果填充），在 `to_dict()` 前对 `input_text`/`match_text` 做 `{placeholder}` 替换；或短期先摘除 verify_title 步并把技能命中降级为实验特性。

### P1 — 架构与正确性

#### N2（新，P1）: verify_title 失败路径与成功路径行为趋同 —— f4161ae 引入的回退

`f4161ae` 的兜底（`gateway.py:499-503`）把 `decide()==None` 统一改成 read_screen。但 cursor 的推进规则是「任意 `action.result.ok=true` 即 +1」（`gateway.py:181-182`），read_screen 恒 ok，于是：

- verify **PASS** → decide 返回 read_screen → ok → cursor+1；
- verify **FAIL** → decide 返回 None → gateway 兜底 read_screen → ok → cursor+1。

**PASS/FAIL 对技能步进完全等价**。`decision.py:247` 的日志「回退 LLM 决策」与实际行为不符——LLM 根本不会被咨询，校验失败的技能会继续走到「tap 发送」。这是「修崩溃」时把「校验语义」一起修没了。测试无一覆盖此路径（`grep verify_title server/tests` 零命中）。

**修法**: FAIL 时不应消耗技能 cursor（如返回带特殊标记的 action，gateway 识别后不推进/回退 cursor 并转 LLM），并把该行为用测试锁住。

#### N3（新，P1）: task.request 重置遗漏 Session 内部状态 —— 5a7bbfa 的残留盲区

`gateway.py:206-227` 重置了全部局部散变量，但**未重置**：

- `session.steps` —— 同连接第二个任务继承上一任务的步数，预算提前耗尽（`budget_exhausted()` 误判 abort）；
- `session.guard` —— pkg_guard 的 stall_count / escalation_level / scene_history 跨任务泄漏；
- `session._state_history` —— 历史无限增长且跨任务混杂；
- `gateway.py:204` 仍是 `session.state = State.NAVIGATING` 直接赋值，绕过 `transition()`（历史记录盲区 + 不触发超时计时清理）。

**修法**: 在 `Session` 上加 `reset_for_new_task(goal)` 方法（重置 steps/guard/state/计时器），gateway 调一处即可；同时把直接赋值改为走 `transition()` 或显式 `force_state()` 并记录历史。

#### P1-2（沿用）: 守卫补丁驱动状态流转 —— 未动

POST_SEND_FORCE_DONE（`gateway.py:386-405`）、POST_SEND_PATROL（:409-426）、INPUT_GUARD（:592-638）、10s 观察窗（:437-484）四道防线仍全是 gateway 特判，直接 `session.transition()` / `session.active=False`。`_ALLOWED` 表无法描述系统真实行为，状态机穷举测试仍缺。

#### P1-3（沿用）: 心跳空转 —— 未动

`gateway.py:196-200`：heartbeat → 回 read_screen → 端侧 reportScreen → perception 因 `active=False` 被丢弃。每心跳一次无意义往返。

#### P1-4（沿用）: `skill_name` 死逻辑 —— 未动

`gateway.py:486`：`skill_name = engine._select_skill(...) if skill_name is None else None`。行为碰巧正确（decide 内部 `decision.py:227-228` 会重选），写法仍是迷宫。

### P2 — 健壮性与一致性（全部核验仍成立，位置已更新）

| # | 问题 | 当前位置 | 状态 |
|---|------|----------|------|
| P2-1 | `resolve_target_pkg` 子串匹配误伤（goal 含「设置」即判系统设置） | `app_goal_resolver.py:37-49` | 未修复 |
| P2-2 | `classify_intent` 子串盖过 LLM 结果（「好的，但是再想想」误判 CONFIRM → done）；`negotiation_history` 任务内无界增长 | `negotiation.py:72-79`、`gateway.py:317` | 未修复 |
| P2-3 | `Executor.input()` 忽略 x/y/id，永远输入屏幕第一个 editable | `Executor.kt:61-68` | 未修复 |
| P2-4 | `dispatchGesture` 返回值=「已派发」非「已执行」，ok 语义乐观；POST_SEND_FORCE_DONE 拿它当强信号 | `Executor.kt:91-100` | 未修复 |
| P2-5 | `gateway.py:133` `Node` 未导入（仅 PEP 649 惰性注解兜底，`get_type_hints` 即 NameError）；`requires-python = ">=3.14,<3.15"` 锁死 | `gateway.py:133`、`pyproject.toml:4` | 半修复（decision.py 侧已修） |
| P2-6 | `metrics.start_task` 把 `device_id` 当 `pkg` 传；`metrics.log` 追加无轮转 | `gateway.py:116`、`metrics.py:86-89` | 未修复 |
| P2-7 | `detect_chat_title` 兜底弱启发式被 POST_SEND_FORCE_DONE 当强信号 | `chat_title_helpers.py:73-79`、`gateway.py:386-394` | 未修复 |
| P2-8 | 双 LLM 实例：`_build_engine()` 一个、`build_llm()` 又一个，每连接两份 client | `gateway.py:106-108` | 未修复 |
| P2-9 | 热路径 `import time as _t` 两处；注释写 `time.time()` 实际用 `monotonic()` | `gateway.py:438,578,150` | 未修复 |
| N5（新） | `Executor.findByText` 的 `matches` 列表与 `findEditable` 递归中未命中节点均未 recycle —— NodeFlattener 修好后执行器侧仍是泄漏源 | `Executor.kt:35-40,70-78` | 新发现 |
| N6（新） | `sent_at_step`、`last_pkg_before_confirm` 为只写不读死变量（赋值 :291/:580，零读取点） | `gateway.py:142,157` | 新发现 |
| N1（新） | `llm.py` 重复定义两个 `FakeLLM`（:22-36 取模循环语义 / :46-62 停最后一个语义），后者覆盖前者，前者为死代码；`5b874d6`「补充缺失的 FakeLLM 类」实际制造了两个类 | `llm.py:22,46` | 新发现 |
| N4（新） | `decide()` 签名仍 `-> list[Action]` 但 `decision.py:250` 仍 `return None` —— 崩溃防住了，类型契约仍在说谎 | `decision.py:220,250` | 新发现 |

### P3 — 长期项（仍未动）

- 协议无版本号；Session 无持久化；`Action.op` 的 `request_confirm`（`protocol.py:134`）定义后从未使用。
- `atEnd` 字段仍保留在双端协议（`protocol.py:36`、`Messages.kt:37`）且 `gateway.py:180` 仍在读取；`test_protocol.py:88` 注释「atEnd 字段已移除」与实现**依旧自相矛盾**——要么删字段，要么改注释。
- seq 乱序检测云端侧仍未落地（字段双端都有，消费为零）。
- `pendingConfirmCancelled` / `check_awaiting_confirm_timeout` 两处死代码：要么接线要么删除（`PhoneAgentService.kt:58`、`session.py:91`）。
- `SkillCache._flush` 仍非原子写（无 tmp+rename），`learn()` 读-改-写仍在锁外；进程级 `threading.Lock` 不解决多实例写冲突（`skill_cache.py:28-51,94-98`）。
- `GatewayConfig` 常量仍闲置：`hex[:8]`（:559）、`timeoutMs=5000`（:569）、巡逻阈值 `>= 2`（:411）、观察窗 `10.0`（:439）、错群阈值 `>= 2`（:615）全部硬编码原封不动。
- 日志 f-string 残留：`negotiation.py:82,124`、`llm.py:95,98,122`。
- 硬编码内网 IP `ws://10.253.61.158:8000` 仍在仓库中（`PhoneAgentService.kt:35`，仅加了注释）。
- gateway 单文件 502 → 688 → **710 行**，持续增长；`engine._cache` / `engine._select_skill` 私有访问仍在（`gateway.py:397,486,523`）。

---

## 二、测试现状（本轮实跑）

**服务端**: `162 passed, 0 failed`（`cd server && .venv/bin/python -m pytest tests/ -q`）。
**Android**: `:app:testDebugUnitTest` BUILD SUCCESSFUL。

测试已全绿，但绿得有水分——以下行为**无任何测试锁定**：

1. N2：verify_title FAIL 路径的 cursor 语义（零用例）；
2. N3：同连接第二任务的 steps/guard 重置（零用例）；
3. P0-2：技能模板参数绑定（零用例，技能路径靠 LLM 兜底掩盖）；
4. `pendingConfirmCancelled` / `check_awaiting_confirm_timeout` 死代码（无测试=无人发现没接线）。

**判据重申（沿用 v1.0）**: 修复完成的唯一判据是「有调用点 + 有测试锁住行为」。`f4161ae`/`5a7bbfa` 两个修复都只满足了前者的一半。

---

## 三、架构层面总结观察（更新版）

1. **「修复引入回退」成为新模式**。v1.0 的主题是假修复（保护代码存在但不生效）；本轮发现 `f4161ae` 属于更隐蔽的一类：崩溃防住了、测试绿了，但 verify_title 的校验语义被顺手抹掉（N2）。凡在兜底路径上改动，必须追问「原来的业务语义去哪了」。

2. **per-task 状态收拢仍是第一优先级**。`5a7bbfa` 手工列了 15 个重置项仍漏 4 处（N3），证明散变量清单式重置不可持续。收拢为 `TaskContext`（含 cursor/history/applied_steps/sent_*/confirm_*/guard/steps），`task.request` 时整体新建，是消除整类 bug 的唯一解。

3. **技能系统缺的那层「参数绑定」依然是最大设计缺口**（沿用 v1.0）。P0-2 不修，`record_skill_hit` 指标、缓存学习（`engine._cache.learn`）、verify_title 守卫全都建立在空转路径上。

4. **类型契约与日志都在说谎，且 CI 无从发现**。`decide() -> list[Action]` 返回 None（N4）、日志写「回退 LLM 决策」实际 read_screen（N2）、测试注释写「atEnd 已移除」实际字段还在——三类「文字与行为不符」问题，只有 `mypy --strict`/pyright + 行为测试能系统性拦截。建议本轮修改先把 pyright basic 接进 CI。

5. **绿测试 ≠ 修复完成**。当前 162 绿下仍有 P0-2/N2/N3/N4 四个实质问题。建议合并门槛在「全绿」之上加一条：本报告 P0/P1 条目逐条销号。

---

## 四、修改优先级建议（本轮刷新，供后续修改直接取用）

| 优先级 | 事项 | 预估 |
|--------|------|------|
| P0 | 技能模板参数绑定：`next_step()` 接收 bindings 并实例化 `{contact}`/`{query}`；配套测试 | 1 天 |
| P0 | N2：verify_title FAIL 不推进 cursor、真正回落 LLM；补行为测试 | 0.5 天 |
| P1 | N3：`Session.reset_for_new_task()` 收拢 steps/guard/state 重置；`gateway.py:204` 消除直接赋值 | 0.5 天 |
| P1 | N1：删除 `llm.py` 第一个死 `FakeLLM`，统一耗尽语义并在 docstring 写明 | 0.5 小时 |
| P1 | N4：`decide()` 签名改 `list[Action] | None` 或禁止返回 None；接 pyright 进 CI | 0.5 天 |
| P1 | per-task 状态收拢为 `TaskContext`（N3 的彻底解） | 1-2 天 |
| P2 | `GatewayConfig` 常量真正替换硬编码（:411,439,559,569,615）；删除死变量 `sent_at_step`/`last_pkg_before_confirm`（N6）；删除或接线 `pendingConfirmCancelled`/`check_awaiting_confirm_timeout` | 0.5 天 |
| P2 | `Executor.input` 按 x/y 定位 editable（P2-3）；`findByText`/`findEditable` 节点回收（N5）；心跳不再回 action（P1-3） | 1 天 |
| P2 | atEnd 字段二选一：协议删除 or 注释改口（消除 test_protocol.py:88 矛盾） | 0.5 小时 |
| P2 | gateway.py 按消息类型拆分 handler（710 行，比任何时候都更紧迫） | 1 周 |
| P3 | 协议版本号、Session 持久化、seq 乱序检测、SkillCache 原子写+进程间锁、metrics pkg 错传与日志轮转、双 LLM 实例合并 | 2 周 |

---

> **审查人**: Kimi (AI Code Reviewer)
> **报告版本**: v2.0（原地更新，取代 2026-07-17 v1.0）
> **验证命令**: `cd server && .venv/bin/python -m pytest tests/ -q`；`cd android && ./gradlew :app:testDebugUnitTest`
> **当前 HEAD**: `5a7bbfa fix: P1-1 修复 task.request 状态重置不完整`
