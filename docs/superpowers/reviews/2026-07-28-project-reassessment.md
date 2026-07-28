# JoyPhone 项目健康度评估 (2026-07-28)

> 重新评估对象:master `dab456a`(自二审报告 26 个新 commit 后)
> 评估方式:量化 + 定性,7 维度打分 + 关键风险识别

---

## 量化指标

| 维度 | 数值 |
|---|---|
| 服务端测试 | 438 passed (上次 404, +34) |
| 服务端代码 | 12000 行 Python / 77 文件 |
| 端侧代码 | 2449 行 Kotlin / 9 文件 |
| 测试文件 | 33 server + 12 android |
| 文档 | 30 docs / 15 plans / 12 specs / 1 review |
| 最近 4 天 commits | 46 (节奏: 11/day) |
| pyright errors | 0 |
| android build | OK |

---

## 维度评分

| 维度 | 评分 | 原因 |
|---|---|---|
| **测试覆盖** | 8/10 | 438 通过,但端到端真机回归仍依赖人工 |
| **代码组织** | 9/10 | L0/L1/L2 三层清晰,边界明确 |
| **文档先行** | 9/10 | spec → plan → impl 节奏稳定,30 docs 沉淀 |
| **真机验证** | 6/10 | 8d8f055 真机回归有 RCA,但 swipe/home_locate 都是真机暴露才补 |
| **协议一致性** | 7/10 | v2 稳定,TaskDone.result 字段是 unknown string |
| **错误恢复** | 5/10 | 重连导致 TaskStore 丢失,旧 taskId 上行无声 noop |
| **状态机完整性** | 8/10 | FSM + LoopGuard + Budget + Confirm + SceneRouter 全覆盖 |
| **可观测性** | 8/10 | metrics endpoint + traceEvents + inspect_frames.py |
| **commit 质量** | 8/10 | 英文、scope 清晰、body 解释 why |
| **CRIT backlog** | 4/10 | 2 CRIT 仍未修(自 27 报告后停滞) |

综合:**7.2/10** — 中上,但有清晰短板。

---

## 重大正面变化(自二审 26 个 commits 内)

1. **SceneRouter 单一真相**:
   - 修复 pkg_guard 抢桌面的真机 bug
   - detect_scene 一次判定,route_by_scene 显式分派
   - 47 行纯函数,边界清晰
2. **home_locate 桌面找图标**:
   - 双向扫描 + 边界逃逸 + 安全上限
   - ColorOS 负一屏小布卡片 / smart-card 过滤
   - 真机 4 fix 闭环,带 RCA 注释
3. **executor animation settle**:
   - fire-and-forget → 阻塞 ack
   - 完整链路 RCA(抓过渡帧 → 误判 → 跳方向)
   - ColorOS 边界条件实测
4. **swipe direction 语义**:
   - 修了 direction 参数被忽略的 bug
   - 水平翻页 400ms / 垂直 300ms 区分
5. **UI flatten**:
   - 删 96 行,合并 178 行
   - 解决短屏 pin / 长屏空白
6. **inspect_frames.py**:
   - 调试工具,改善 dev experience

---

## 风险点(按严重度)

### 🔴 CRIT(仍未修)

**CRIT-1: cancel race bug** — 自 27 日报告后未修
- 用户点击「中止」 → UI 短暂显示「失败: user_cancel」
- 修复方案已就绪(80 行 diff),**未实施**

**CRIT-2: taskId staleness** — 自 27 日报告后未修
- 重连后旧 taskId 上行 cancel/confirm/ack 无统一防
- 修复方案已就绪(1 helper + 5 callsite),**未实施**

### 🟡 MED(已有 backlog)

- onCancelTask 命名混淆
- TaskDone.result: Literal
- wechat profile 字段不齐
- scene_router / home_locate 涉及 Scene enum, pkg_guard.py 现在被 3 模块共享,值得一 docstring 说明「Scene 是共享 API」

### 🟢 LOW

- cache mark_miss vs AGENTS.md 不一致
- SkillCache cursor 参数收而不用
- LOW-1/2/3(报告归档)

### 新观察(本次新增)

- **home_locate 内 `guard: dict` 可变输入**: 不是真纯函数, 但通过 caller 契约控制,**可接受**
- **`Thread.sleep` 阻塞 WS 线程**: 8d8f055 引入, sync 风险受服务端节流保护,**可接受**
- **Scene enum 跨文件共享**: pkg_guard.py → home_locate / scene_router,**缺单一来源 docstring**,**建议加**

---

## 推荐动作清单

### 立即(下个 sprint)

1. **修 CRIT-1**(cancel race),80 行 diff, 1 commit
2. **修 CRIT-2**(taskId staleness helper),1 helper + 5 callsite, 1 commit
3. **pkg_guard.py Scene 共享 docstring 补**,1 改动

### 中期(本月)

4. **真机回归自动化**: 现在 swipe / home_locate / executor settle 都是真机人工测试,**值得把关键 case 录成 simulator 录屏回放**
5. **协议 v3 规划**: TaskDone.result: Literal;`pendingCancelledTaskIds` 等 cleanup
6. **场景脚本 specs**: SendMessagePack / home_locate / scene_router 三个已经稳定,值得写更全面的 e2e 脚本

### 长期(下季度)

7. **TaskStore 持久化**: 内存 store 是核心可观测性盲点。Redis / SQLite 选项
8. **设备能力架构落地**: AGENTS.md 已写 design doc 但未实装
9. **协议 v3 升级**: 配合端侧版本兼容

---

## 决策建议

| 选项 | 推荐场景 |
|---|---|
| **A. 立即修 CRIT-1 + CRIT-2** | 当前 sprint 内(24h) |
| **B. 修 CRIT + 加 Scene docstring** | 适合质量优先迭代(我推荐) |
| **C. 继续加速 home_locate / 真机回归** | 适合发布下一个 app(微信朋友圈) |
| **D. 暂停 feature, 清理 backlog** | 适合准备协议 v3 升级 |

**我推荐 B**:在三审前后状态最稳,修两个 CRIT 即可解锁下阶段(scene_router / home_locate 已成为新稳定基线)。
