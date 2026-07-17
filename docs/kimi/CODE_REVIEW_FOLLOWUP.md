# JoyPhone 二次代码审查报告（Kimi）

> **审查时间**: 2026-07-17
> **审查基准**: `docs/CODE_REVIEW_REPORT.md`（v1.0）+ 修复 commit `c85fa2a` + 当前工作区未提交改动
> **审查方式**: 全量源码精读 + 服务端测试实跑 + Android 单元测试实跑 + 关键路径运行时实证
> **注意**: 审查期间工作区被并发修改（16:36 前后），测试失败数从 7 降至 4。本报告以当前工作区状态为准。

---

## 一、原报告问题修复核验

### 1.1 架构问题

| # | 原问题 | 状态 | 证据与说明 |
|---|--------|------|-----------|
| 1 | 云端单点瓶颈（gateway.py 500+ 行） | **❌ 恶化** | 502 行 → 688 行（`server/app/gateway.py`）。确认拦截、错群守卫、发送后巡逻、10s 观察窗等新逻辑全部继续堆在单文件里，职责比审查时更重 |
| 2 | 状态机双重维护（Session/Scene 无关联） | **❌ 未修复** | 仍无编排层。且 gateway 里大量特判补丁直接驱动状态流转（见新发现 P1-2），两套状态机关联性进一步弱化 |
| 3 | 技能库与 LLM 边界模糊（关键词匹配） | **❌ 未修复** | `SkillLibrary.select()` 仍是关键词子串匹配（`skills.py:140-150`）。更严重的是技能模板从未实例化，技能路径已实质损坏（见新发现 P0-2） |

### 1.2 协议问题

| # | 原问题 | 状态 | 证据与说明 |
|---|--------|------|-----------|
| 1 | `atEnd` 语义不清 | **⚠️ 假修复** | commit `c85fa2a` 移除了该字段，但 `gateway.py:180` 仍在使用 `uplink.atEnd`，工作区又把字段加回双端协议（`protocol.py:36`、`Messages.kt:37`）。字段照旧保留，语义照旧不清。`test_protocol.py:88` 注释写「atEnd 字段已移除」，与实现自相矛盾 |
| 2 | 缺少消息序列号/乱序校验 | **⚠️ 部分修复** | `seq` 字段双端已加（`protocol.py:26,35`、`Messages.kt:26,36`），端侧 `perceptionSeq` 递增（`PhoneAgentService.kt:168`）。但：**云端完全没有消费 seq**（无乱序检测、无去重、无 `expect_seq`）；且 `action.result` 的 seq 永远为 0（`WsClient.kt:123-125` 未传）。修复停留在「只加了字段」 |
| 3 | confirm 双重超时竞态 | **⚠️ 假修复** | `pendingConfirmCancelled` 标志已声明并在 Runnable 中检查（`PhoneAgentService.kt:58-63`），但**全代码库没有任何地方把它置为 true**——死代码。`onTaskEnd` 也不清理 `pendingConfirm` / `handler` 回调。真正兜底靠云端 state+confirmId 校验（`gateway.py:224-235`），竞态实际影响有限，但报告建议的修复并未落地 |
| 4 | `sample.capture` 与决策链路耦合 | **❌ 未修复** | 仍复用 Node 结构（`protocol.py:67-75`），影响低 |

### 1.3 状态机问题

| # | 原问题 | 状态 | 证据与说明 |
|---|--------|------|-----------|
| 1 | 状态转移无历史记录 | **✅ 已修复（有盲区）** | `session.py:53,75` 实现 `_state_history`。但 `gateway.py:204` 在 `task.request` 时**直接赋值** `session.state = State.NAVIGATING` 绕过 `transition()`，历史记录存在盲区 |
| 2 | AWAITING_CONFIRM→IN_CHAT 语义冲突 | **❌ 未修复** | `session.py:21` IN_CHAT 自迁移仍在，未引入 RECONSIDERING 或状态机框架 |
| 3 | 缺少超时守卫 | **⚠️ 假修复** | `Session.check_awaiting_confirm_timeout()` 已实现（`session.py:91-98`），但**全代码库零调用点**——死代码。AWAITING_CONFIRM 超时保护实际仍未生效 |
| 4 | 步数预算与状态转移耦合 | **❌ 未修复且引入 P0** | 耦合依旧（`gateway.py:358`），且 `session.record_step()` **从未被任何生产代码调用**（仅测试调用），`budget_exhausted()` 永远为 False——步数预算完全失效。失败测试 `test_gateway_budget_exhausted_aborts` 可证 |

### 1.4 编码质量

| # | 原问题 | 状态 | 证据与说明 |
|---|--------|------|-----------|
| Py-1 | gateway.py 过长 | **❌ 恶化** | 688 行，且新增 4 处 `engine._cache` / `engine._select_skill` 私有成员访问（`gateway.py:386,475,501`），封装泄漏 |
| Py-2 | 日志格式不统一 | **⚠️ 部分修复** | gateway 已统一 `%` 格式；`negotiation.py:82,124`、`llm.py:74,77` 仍是 f-string |
| Py-3 | 魔法数字 | **⚠️ 假修复** | `GatewayConfig`（`gateway.py:52-63`）、`SceneConfig`、`SessionConfig` 类已建立，但 **gateway 内硬编码原封不动**：`hex[:8]`（:537）、`timeoutMs=5000`（:547）、巡逻阈值 `>= 2`（:400）、观察窗 `10.0`（:428）、错群阈值 `>= 2`（:593）。配置类常量基本无人引用——为审查而建的摆设 |
| Py-4 | 异常处理不一致 | **⚠️ 部分修复** | gateway 内已统一；negotiation 的宽 `except Exception` 仍在 |
| Py-5 | SkillCache 无并发保护 | **⚠️ 部分修复** | `threading.Lock` 只护住 `write_text` 一行（`skill_cache.py:96-98`）；`learn()` 的读-改-写不在锁内；进程级锁**无法解决原报告指出的「多实例部署写冲突」**；写入非原子（无 tmp+rename），进程崩溃可致 cache 文件损坏 |
| Kt-1 | 硬编码 WS_URL | **❌ 未修复** | `PhoneAgentService.kt:35` 仍硬编码内网 IP `ws://10.253.61.158:8000`（仅加了注释）。该 IP 已提交进仓库 |
| Kt-2 | deviceId 空检查 | **✅ 已修复** | `WsClient.kt:61` `require(deviceId.isNotBlank())` |
| Kt-3 | Coroutine 作用域 | **✅ 已修复** | `Dispatchers.Main.immediate`（`PhoneAgentService.kt:81`） |
| Kt-4 | NodeFlattener 资源泄漏 | **✅ 已修复** | try/finally recycle（`NodeFlattener.kt:109-113,128-130`）。注：API 34+ `recycle()` 已 deprecated（编译告警），长期需调整；`Executor.findEditable/findByText` 仍有未回收节点（次要） |

### 1.5 测试现状（实跑结果）

**服务端**: `158 passed, 4 failed`（审查开始时为 155 passed / 7 failed，期间有并发修复）

| 失败测试 | 性质 |
|----------|------|
| `test_gateway_budget_exhausted_aborts` | **真实 P0**——步数预算失效（见 1.3-4） |
| `test_skill_hit_without_llm` | 测试过时——技能改名 `feishu_send_message` 且步骤插入 `verify_title`，测试仍引用旧名 `feishu_send` |
| `test_fake_llm_returns_last_when_exhausted` | 语义分歧——`FakeLLM` 耗尽后从「停最后一个」改为「取模循环」（`llm.py:32`），测试与实现必有一方是错的；循环语义还会改变回放夹具行为 |
| `test_llm_is_abstract` | 测试断言过时——`LLM` 非 ABC，实例化不抛 TypeError |

**Android**: `:app:testDebugUnitTest` BUILD SUCCESSFUL（全量重编验证通过）。

**关键结论**: commit `c85fa2a` 声称「修复代码审查报告中的所有问题」，但提交时测试是红的——**修复过程没有跑测试验证**。

---

## 二、新发现问题（本次审查）

### P0 — 必须立即修复

#### P0-1: `decide()` 返回 `None` 导致 WebSocket 崩溃（已运行时实证）

`decision.py:249` verify_title 校验失败时 `return None`，但函数签名声明 `-> list[Action]`，且 `gateway.py:494` 直接 `for action in actions:` 迭代：

```
[VERIFY_TITLE_FAIL] skill=feishu_send_message expected='{contact}' current='其他群' 回退 LLM 决策
TypeError: 'NoneType' object is not iterable
```

WS 处理循环没有对 `decide()` 调用做异常保护，连接直接断开、任务无提示终止。**已实际复现**。

#### P0-2: 技能模板变量 `{contact}` / `{query}` 从未实例化——技能系统生产路径全损

`skills.py:73,76,87` 定义了 `input_text="{contact}"`、`match_text="{contact}"`，但 `SkillLibrary.next_step()` 没有任何参数绑定环节（签名里连 goal 都没有），模板原样下发：

- input 步会把字面量 `{contact}` 敲进搜索框；
- verify_title 步期望标题为字面量 `{contact}`，**永远失败**（实证日志见 P0-1）。

两个 bug 叠加：`feishu_send_message` 技能走到 cursor=3 **必现** P0-1 崩溃。三级回退（缓存→技能→LLM）的中间一级实际是断的，目前全靠 LLM 兜底，技能命中指标（`record_skill_hit`）也会产生误导。

#### P0-3: 步数预算完全失效

`Session.record_step()` 零生产调用点 → `budget_exhausted()` 恒 False（`session.py:100-104`）。gateway 用 `cursor` 计数做技能步进，却从未同步给 session。**后果：LLM 失控循环时没有任何预算兜底**，任务可以无限空转直到用户手动断开。失败测试 `test_gateway_budget_exhausted_aborts` 即为铁证。

### P1 — 架构与正确性

#### P1-1: `task.request` 状态重置不完整——同连接第二个任务继承污染

`gateway.py:202-221` 只重置了 confirm 相关变量，**未重置**：`cursor`、`history`、`applied_steps`、`sent_acked`、`sent_at_step`、`post_send_patrol_count`、`wrong_chat_input_count`、`skill_name`、`last_pkg`。后果：

- 新任务 cursor 从旧值起步 → 技能/缓存步进错位；
- `applied_steps` 混入旧任务步骤 → `engine._cache.learn` 学到脏数据；
- 若旧任务 `sent_acked=True` 残留 → 新任务可能触发「发送后巡逻」误 abort。

**架构建议**: 把 per-task 散变量收拢为 `TaskContext` 对象，`task.request` 时整体新建，消除手工重置清单（已漏一半即是证明）。

#### P1-2: 守卫补丁绕过状态机——状态机已名存实亡（架构层面最重要发现）

修复期新增的四道防线（POST_SEND_FORCE_DONE、POST_SEND_PATROL、INPUT_GUARD、10s 观察窗）全部是 gateway 里的特判补丁，直接调用 `session.transition()` / 置 `active=False`，绕开状态机语义。原报告建议的「状态机穷举测试」未补，状态流转反而更不可追踪。**当前真实的状态流转由补丁驱动，`_ALLOWED` 表已无法描述系统行为**。再叠加新功能时，这是下一个事故温床。

#### P1-3: 心跳环路设计异味

`gateway.py:196-200`：收到 heartbeat → 回 `read_screen` action → 端侧执行后 `reportScreen()` → perception 上行 → 云端因 `active=False` 丢弃。每次心跳产生一个无意义的 action+perception 往返。协议语义上「心跳应轻量无响应」，建议云端对 heartbeat 不回 action（或回专用 ack）。

#### P1-4: `skill_name` 选择逻辑费解

`gateway.py:475`: `skill_name = engine._select_skill(...) if skill_name is None else None`——每帧实际都重选（选中后下一帧又置 None）。行为碰巧正确，但写法等价于每帧直接调用，属于死逻辑迷宫。

### P2 — 健壮性与一致性

| # | 问题 | 位置 |
|---|------|------|
| P2-1 | `resolve_target_pkg` 子串匹配误伤：goal 含「设置」即判目标 app 为系统设置，含「qq」子串即判 QQ → pkg guard 会把用户真正要用的 app 当「跑错应用」强制退出 | `app_goal_resolver.py:37-49` |
| P2-2 | `classify_intent` 用「好的」等子串直接盖过 LLM 分类结果（「好的，但是再想想」误判 CONFIRM → 直接 done）；`negotiation_history` 无界增长 | `negotiation.py:72-79`、`gateway.py:306` |
| P2-3 | `Executor.input()` 忽略 x/y/id 定位，永远输入到屏幕**第一个** editable 节点——搜索框与正文框共存时必错，与云端错群守卫的假设不一致 | `Executor.kt:61-68` |
| P2-4 | `dispatchGesture` 返回值只代表「已派发」不代表「已执行」，`action.result.ok=true` 语义偏乐观；POST_SEND_FORCE_DONE 又把这个 ok 当强信号 | `Executor.kt:94-100` |
| P2-5 | `decision.py:371` 使用 `Optional` 未导入、`gateway.py:133` 使用 `Node` 未导入——仅靠 Python 3.14 PEP 649 惰性注解求值才不炸；`requires-python` 锁死 3.14，任何 `get_type_hints` 调用即 NameError | 两处 |
| P2-6 | `metrics.start_task` 把 `device_id` 当 `pkg` 传（`gateway.py:116`）；`metrics.log` 追加无轮转 | `metrics.py:87-89` |
| P2-7 | `detect_chat_title` 兜底规则（首个非 editable text≥2 字）是弱启发式，却被 POST_SEND_FORCE_DONE 当强信号提前 done | `chat_title_helpers.py:73-79`、`gateway.py:375-394` |
| P2-8 | 双 LLM 实例：`ws_gateway` 里 `_build_engine()` 内建一个、`build_llm()` 又建一个（`gateway.py:106-108`），每连接两份 client | `gateway.py` |
| P2-9 | `import time as _t` 热路径内联 import 两处（`gateway.py:427,556`），且注释称用 `time.time()` 实际用 `monotonic()`——文档与实现不符 | `gateway.py:150` |

### P3 — 原报告长期项（未动，确认仍缺）

- 协议无版本号，平滑升级无保障；
- Session 无持久化，重启丢状态；
- `Action.op` 中 `request_confirm`（`protocol.py:133`）定义后从未使用。

---

## 三、架构层面总结观察

1. **「假修复」比不修更危险**。`GatewayConfig` 建了不用、`check_awaiting_confirm_timeout` 实现了不调、`pendingConfirmCancelled` 声明了不置位、`record_step` 存在却不触发——读代码的人会以为保护已生效，实际全是空城计。建议以「是否有调用点 + 是否有测试锁住行为」作为修复完成的唯一判据。

2. **修复方式与架构方向背道而驰**。原报告 P2 建议「重构 gateway.py 拆分文件」，实际修复却把所有新守卫继续塞进 gateway，行数反增 37%。当前的正确动作不是继续打补丁，而是先完成 P1-1 的 `TaskContext` 收拢 + 按消息类型拆分 handler，否则每个新需求都会让 688 行继续膨胀。

3. **类型契约在说谎**。`decide() -> list[Action]` 实际返回 `None`；注解引用了未导入的名字靠 PEP 649 兜底。Python 3.14 的惰性注解让这类问题完全隐形——建议引入 `mypy --strict` 或至少 pyright basic 进 CI，这类 P0 会在编译期暴露。

4. **技能系统缺一层「参数绑定」**。`SkillStep` 的 `{contact}`/`{query}` 从设计起就没有实例化环节，`next_step()` 签名不含 goal/context。这是设计缺口而非实现 bug：三级回退的中间一级从未真正可用。

5. **测试纪律是当前最大杠杆**。修复 commit 带着 7 个红测试提交，说明没有 pre-commit/CI 卡点。建议：修红现有 4 个测试（其中 2 个只需更新断言），并把「pytest 全绿 + gradle test 全绿」设为合并硬门槛。

---

## 四、修复优先级建议

| 优先级 | 事项 | 预估 |
|--------|------|------|
| P0 | `decide()` 禁止返回 None（返回 `[]` 或 LLM 回落），gateway 对 decide 调用加异常保护 | 0.5 天 |
| P0 | 接通 `session.record_step()`（或改用 cursor 判断预算），恢复预算兜底 | 0.5 天 |
| P0 | 技能模板参数绑定（next_step 接收 goal/target 并替换占位符），或暂时禁用 verify_title 步 | 1 天 |
| P1 | per-task 状态收拢为 TaskContext，task.request 整体重建 | 1-2 天 |
| P1 | 修红 4 个失败测试 + 接入 CI 硬门槛 | 1 天 |
| P1 | 接线 `check_awaiting_confirm_timeout` 与 `pendingConfirmCancelled`，或删除死代码 | 0.5 天 |
| P2 | GatewayConfig 常量真正替换硬编码；移除未用 `pending_send_button_node` 死变量 | 0.5 天 |
| P2 | 引入 pyright/mypy CI；`Executor.input` 按坐标定位 editable；心跳不再回 action | 1 天 |
| P2 | gateway.py 按消息类型拆分 handler（原报告 P2 项，现更紧迫） | 1 周 |
| P3 | 协议版本号、Session 持久化、seq 乱序检测真正落地 | 2 周 |

---

> **审查人**: Kimi (AI Code Reviewer)
> **报告版本**: v1.0
> **验证命令**: `cd server && .venv/bin/python -m pytest tests/ -q`；`cd android && ./gradlew :app:testDebugUnitTest`
