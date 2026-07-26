# P2 扩展：action space + metrics + cache 沉淀

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **状态**: 脚手架阶段 (2026-07-26 真机尚未跑通,本期不开 cache/skill 回放)
> **来源**: `docs/roadmap/2026-07-25-improvement-plan.md` §五 + §七·P2 + 客户端反馈「少 4 个 op」
> **前置**: 2026-07-25 payload redesign 已落地(`docs/roadmap/2026-07-25-llm-payload-redesign.md` Phase 1~6 全 ✅)

**Goal**: 落实 roadmap §七·P2 三项补强:
1. **action space 扩到 15 verb**:`scroll_to` / `open_notifications` / `open_quick_settings` 端到端
2. **metrics 任务级**:加 `loop_guard_triggered_count` / `action_success_rate` / HTTP `/metrics/recent` 端点
3. **cache 沉淀自动钩子**:任务结束时根据结果走 `cache.record_success()` / `cache.mark_miss()`(数据沉淀等真机)

**Architecture:**
- 协议 v2 Action 模型加 3 op
- `parse_actions` 增 3 verb
- Android Executor 加 3 case(scroll_to 用 SwipeHelper,open_notifications/quicksettings 用 SwipeHelper + coordinate)
- metrics:TaskMetrics 加字段 + 暴露 HTTP GET
- cache:TaskContext 在 `_terminate` 时根据 verdict 触发记录

**Tech Stack:** Python 3.14 / pytest / pyright;Kotlin 端侧无障碍服务;协议 v2 不变(向后兼容老 Action)。

---

## 文件结构

| 文件 | 责任 |
|---|---|
| **修改** `server/app/protocol/models.py` | `Op` 增 3 项:`scroll_to` / `open_notifications` / `open_quick_settings` |
| **修改** `server/app/decision/engine.py` | `_NOARG_OPS` 加 3 项;`parse_actions` 加 `scroll_to` |
| **修改** `server/app/decision/payload.py` | `[TOOLS]` 段加 3 op 描述 |
| **修改** `server/app/infra/metrics.py` | `TaskMetrics` 加 `loop_guard_triggered_count` / `action_ok_count` / `action_total_count`;增 `record_loop_guard_trigger` / `record_action_result`;计算 `action_success_rate` |
| **修改** `server/app/gateway/router.py` | 注册 `/metrics/recent` endpoint |
| **修改** `server/app/task/handlers.py` | `_on_action_result` 调 `metrics.record_action_result`;`_terminate` 触发 cache 沉淀 |
| **修改** `server/app/decision/cache.py` | 加 `record_for_task(ctx, success)` 业务封装 |
| **修改** `android/app/src/main/.../Executor.kt` | 新增 `scrollTo` / `openNotifications` / `openQuickSettings` case |
| **新增测试** `server/tests/test_actions.py` | `parse_actions` 3 op 单测 |
| **新增测试** `server/tests/test_metrics.py` | 新指标字段 + 派生计算单测 |
| **修改** `server/tests/test_*.py` | 相关已有测试同步调整 |

---

## Task 1: 协议 + parse_actions 加 3 op

**Files:**
- Modify: `server/app/protocol/models.py`
- Modify: `server/app/decision/engine.py`
- Modify: `server/app/decision/payload.py`
- Test: `server/tests/test_actions.py`

- [ ] **Step 1: 写失败测试(`test_scroll_to_verb`、`test_open_notifications_verb`、`test_open_quick_settings_verb`)**

---

## Task 2: 端侧 Executor 3 op 实现

**Files:**
- Modify: `android/app/src/main/.../Executor.kt`

- [ ] **Step 1: 加 scroll_to case(SwipeHelper 滑到顶/底)**
- [ ] **Step 2: 加 open_notifications case(从顶部下拉)**
- [ ] **Step 3: 加 open_quick_settings case(下拉后再下拉,或直接从 right top)**

---

## Task 3: metrics 补字段 + record API

**Files:**
- Modify: `server/app/infra/metrics.py`
- Test: `server/tests/test_metrics.py`

- [ ] **Step 1: TaskMetrics 加 `loop_guard_triggered_count` / `action_ok_count` / `action_total_count`**
- [ ] **Step 2: 加 `record_loop_guard_trigger()` / `record_action_result(ok: bool)`**
- [ ] **Step 3: 加 `action_success_rate` 属性(0.0~1.0)**

---

## Task 4: HTTP `/metrics/recent` endpoint

**Files:**
- Modify: `server/app/gateway/router.py`
- Modify: `server/app/infra/metrics.py` (加 `recent(N)` 聚合)

- [ ] **Step 1: metrics 模块加 `recent(limit: int = 10) -> list[dict]` 聚合**
- [ ] **Step 2: router 注册 GET `/metrics/recent?limit=10`**

---

## Task 5: 任务终止触发 cache 沉淀

**Files:**
- Modify: `server/app/decision/cache.py` (加 `record_for_task`)
- Modify: `server/app/task/handlers.py` (_terminate 调用)

- [ ] **Step 1: SkillCache 加 `record_for_task(ctx, success: bool)`**
- [ ] **Step 2: handlers._terminate 根据 verdict.ok 触发 record_for_task**
- [ ] **Step 3: 验证 REPLAY_ENABLED=False 时 record_for_task 仍跑(沉淀机制独立)**
