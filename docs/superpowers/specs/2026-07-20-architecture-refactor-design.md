# JoyPhone 全面架构重构设计（Spec）

> **日期**: 2026-07-20
> **状态**: 已获用户批准（brainstorming 流程）
> **前置依据**: `docs/CODE_REVIEW_REPORT.md`(v1.0) + `docs/kimi/CODE_REVIEW_FOLLOWUP.md`(v2.0)
> **指导原则**: 全面重构、选最优架构、不做妥协、**不要前向兼容**、不惧修改量
> **通用性原则**: 内核场景无关；场景特化通过 ScenarioPack（代码）+ AppProfile（数据）注入

---

## 1. 背景与问题陈述

三轮代码审查确认的根因（详见 kimi v2.0 报告）：

1. **gateway.py 710 行上帝文件**：连接管理、协议解析、per-task 状态（20+ 散变量）、决策调度、四道守卫补丁、确认逻辑全部混杂。
2. **状态机被架空**：Session/Scene 两套状态机无关联；POST_SEND_FORCE_DONE / POST_SEND_PATROL / INPUT_GUARD / 10s 观察窗四道守卫是 gateway 特判补丁，直接驱动状态流转，`_ALLOWED` 表无法描述系统真实行为。
3. **per-task 状态散列**：task.request 手工重置清单已两次被证明会漏（v1.0 漏 9 项、修复后仍漏 session.steps/guard/_state_history）。
4. **技能系统从未可用**：`{contact}`/`{query}` 模板无参数绑定层；cursor 推进语义混乱（任意 action.result.ok 都 +1）；verify_title FAIL 与 PASS 行为趋同。
5. **场景特化寄生内核**：FSM 状态（IN_CHAT/SENT/NEGOTIATING）、chat_title_helpers 关键词表、skills 全部只为「飞书发消息」服务，却写死在通用路径里，无法复用到其他场景/app。
6. **协议债**：atEnd 僵尸字段、seq 只加不消费、无版本号、heartbeat 空转。
7. **端侧债**：Executor.input 永远输入第一个 editable、节点回收不全、pendingConfirmCancelled 死标志、硬编码内网 IP。

## 2. 目标架构总览

分层管道架构，三层职责严格分离：

```
┌─────────────────────────────────────────────┐
│ L0 内核(场景无关,永不为新场景改代码)          │
│  连接/路由 · TaskContext · 通用 FSM · 策略管道 │
│  Decision 引擎(cache→skill→pkg_guard→LLM)    │
├─────────────────────────────────────────────┤
│ L1 场景包 ScenarioPack(每类任务一个,代码)      │
│  send_message(本期实装) / search / navigate…  │
├─────────────────────────────────────────────┤
│ L2 AppProfile(每个 app 一份,纯数据)           │
│  feishu / wechat / qq / dingtalk…            │
└─────────────────────────────────────────────┘
```

## 3. 服务端设计

### 3.1 模块结构（S1)

```
server/app/
├── protocol/          # 纯协议层(模型 + 版本号 + 解析)
├── gateway/           # 连接层:只做 accept/parse/dispatch,无业务状态
│   ├── connection.py      # WS 生命周期、发送封装
│   └── router.py          # uplink → handler 注册表分发
├── task/              # 任务层:一次任务的全部状态与行为
│   ├── context.py         # TaskContext(唯一 per-task 状态载体)
│   ├── fsm.py             # 任务状态机(迁移表 + 历史 + 超时守卫)
│   ├── handlers.py        # 各 uplink 类型的处理函数(操作 TaskContext)
│   └── policies.py        # 策略管道(见 3.3)
├── scenario/          # L1 场景包
│   ├── base.py            # ScenarioPack 协议 + 注册表 + matches 选择
│   ├── send_message.py    # 发消息场景(含 confirm/post_send/input_guard 策略)
│   └── profiles/          # L2 AppProfile 数据
│       ├── feishu.py
│       └── wechat.py
├── decision/          # 决策层
│   ├── engine.py          # DecisionEngine:cache→skill→guard→LLM
│   ├── skills.py          # SkillTemplate + BoundSkill(参数绑定)
│   ├── cache.py
│   ├── llm.py             # LLM/FakeLLM/RealLLM(删除重复 FakeLLM)
│   └── types.py           # Decision(actions, source, meta)
└── infra/             # metrics / comm_log / config(常量真正落地)
```

### 3.2 TaskContext —— 唯一 per-task 状态载体（S2)

```python
class TaskContext:
    task_id: str
    goal: str
    fsm: TaskFSM              # 通用状态机实例,含迁移历史与超时守卫
    steps: int                # 预算计数
    cursor: SkillCursor       # 技能/缓存步进(见 3.5)
    history: list[dict]       # action.result 历史
    applied_steps: list[dict]
    target: TaskTarget        # target_pkg + target_chat(场景包解析产物)
    bindings: dict[str, str]  # 技能参数绑定(如 {"contact": "张三"})
    bound_skill: BoundSkill | None
    confirm: ConfirmState     # pending_action/confirm_id/sent_ts/reverted/count
    post_send: PostSendState  # sent_acked/patrol_count
    guard: GuardState         # pkg_guard 收敛状态
    negotiation: list[dict]
```

**铁律**: `task.request` 到达 → 整体新建 TaskContext 替换旧实例;DONE/ABORT → 置 None。gateway 只持有 `current_task: TaskContext | None`。不存在任何「重置清单」。

### 3.3 策略管道（S3)

```python
class Policy(Protocol):
    name: str
    def inspect(self, frame: Perception, ctx: TaskContext) -> Verdict: ...

# Verdict = Continue | Terminate(reason, status) | Intercept(actions)

# 内核 PRE 策略(decide 之前,全场景生效)
KERNEL_PRE = [BudgetPolicy()]
# 内核 POST 策略(decide 之后下发之前,全场景生效)
KERNEL_POST = []

# send_message 场景包注入
SEND_MESSAGE_PRE = [
    PreSendRevertPolicy(),      # AWAITING_CONFIRM 10s 观察窗 → abort
    PostSendForceDonePolicy(),  # 已发送+标题匹配 → 强制 done
    PostSendPatrolPolicy(),     # 发送后巡逻 ≥2 帧 → abort
]
SEND_MESSAGE_POST = [
    ConfirmInterceptPolicy(),   # tap 发送按钮 → 拦截改发 task.confirm
    WrongChatInputPolicy(),     # 错群 input → 拦截改 back / 累计 ≥2 → abort
]
```

- 每个策略是纯函数式单元，独立单测；
- 所有状态迁移统一走 `ctx.fsm.transition(reason=policy.name)`，迁移原因强制记录，状态流转全程可追溯；
- FSM 内置 AWAITING_CONFIRM 超时，由管道中 `ConfirmTimeoutPolicy` 真正接线（现 `check_awaiting_confirm_timeout` 零调用问题从结构上消灭）。

### 3.4 通用 FSM

内核只保留 5+1 个通用状态：

```
IDLE → RUNNING → AWAITING_CONFIRM → RUNNING(驳回) / DONE / ABORT
RUNNING → WAITING_EVENT → RUNNING / DONE / ABORT   (等待回复型场景)
RUNNING → DONE / ABORT
```

现 IN_CHAT/SENT/WAITING_REPLY/NEGOTIATING 降级为 send_message 场景内的**子状态标签**（挂在 TaskContext 上供策略判断，不进内核 FSM）。协商机器人成为 WAITING_EVENT 状态下由场景包注册的事件处理器。

### 3.5 决策层（D1/D2/D3)

**SkillTemplate + BoundSkill（参数绑定层）**:

```python
@dataclass
class SkillTemplate:            # 场景包提供的静态定义
    name: str
    params: list[str]           # 声明需要的绑定,如 ["contact"]
    steps: list[SkillStep]      # 含 {contact} 占位符

class BoundSkill:
    @classmethod
    def bind(cls, tpl: SkillTemplate, bindings: dict[str, str]) -> "BoundSkill | None":
        # 缺绑定 → None(技能本轮不可用,回落 LLM)
        # 绑定时一次性替换全部占位符,steps 变为具体值
```

- 绑定发生在技能选中时（task.request 装配阶段），非每帧；
- `next_step()` 只消费已实例化的具体步骤。

**SkillCursor（cursor 语义根治）**:

```python
class SkillCursor:
    index: int
    state: PENDING | ISSUED | VERIFIED | FAILED

# 推进规则:仅当「本帧动作 source ∈ {cache, skill} 且端侧 ack ok」→ index+1
# verify_title PASS → 无副作用 read_screen 占位,ack 后推进
# verify_title FAIL → state=FAILED,技能本轮作废,同帧回落 LLM,index 不动
```

**Decision 类型与引擎**:

```python
@dataclass
class Decision:
    actions: list[Action]        # 永不空,无决策时为 [read_screen]
    source: Literal["cache", "skill", "pkg_guard", "llm"]
    meta: dict = field(default_factory=dict)

# decide() 永不返回 None;引擎内部:
# 1. cache.lookup(goal, pkg, cursor)        → source=cache
# 2. bound_skill.next_step(frame, cursor)   → source=skill(verify_title 在此评估)
# 3. pkg_guard(frame, target_pkg, guard)    → source=pkg_guard
# 4. llm.complete(...)                      → source=llm
```

私有成员访问（`engine._cache`/`engine._select_skill`）全部消失，handler 只消费 Decision。

### 3.6 场景包接口（S4)

```python
class ScenarioPack(Protocol):
    name: str
    def matches(self, goal: str) -> float             # 意图匹配得分,0=不命中
    def resolve_target(self, goal: str) -> TaskTarget # app pkg + 目标对象 + bindings
    def skills(self) -> list[SkillTemplate]
    def pre_policies(self) -> list[Policy]
    def post_policies(self) -> list[Policy]
    def ui_profile(self, pkg: str) -> AppProfile      # L2 识别特征

class AppProfile(BaseModel):   # 纯数据
    pkg: str
    aliases: list[str]                # app_goal_resolver 别名表归位于此
    title_rid_keywords: list[str]     # 现 chat_title_helpers 硬编码归位
    send_button_keywords: list[str]
    search_hints: list[str]
    message_input_hints: list[str]
```

- `task.request` 到达：遍历注册的场景包取 `matches()` 最高分装配 TaskContext；无命中 → 纯 LLM 通用模式（预算/pkg_guard 等内核安全策略仍在）；
- **适配成本分级**: ① 同场景新 app = 只加 AppProfile 数据（配 sample.capture 探针→标注→生成 Profile 工作流）;② 新场景 = 新 ScenarioPack;③ 未知场景 = 内核 LLM 兜底，不硬失败。

## 4. 协议 v2（双端同步切换，不兼容旧端）

- 删除 `atEnd` 字段（双端）、未使用的 `request_confirm` op;
- 新增 `protocol_version: 2` 握手校验，版本不符拒连;
- seq 真正落地：端侧 perception/action.result 共用递增序号；云端丢弃 `seq <= last_consumed` 的过期 perception 并记日志;
- heartbeat 改为轻量 `heartbeat.ack`，不再回 read_screen 空转。

## 5. 端侧（Android）

- **ConfirmManager**: 统一持有 pendingConfirm/超时 Runnable/取消逻辑,`onTaskEnd` 强制清理(消灭 pendingConfirmCancelled 死标志类问题);
- **Executor**: `input` 按 x/y 坐标定位 editable(与 tap 一致);`findByText`/`findEditable` 节点全量 recycle;`dispatchGesture` 走 callback 拿真实执行结果回传 ok;
- **配置**: WS_URL 移入 BuildConfig(build.gradle.kts per-flavor),内网 IP 从源码移除。

## 6. 测试与 CI

- **契约测试**: 双端共享 golden JSON 样本(协议 v2 每种消息),Python/Kotlin 各自反序列化断言;
- **策略单测**: 每个 Policy 独立测试;**FSM 穷举测试**: 全部合法/非法迁移;
- **场景包回归**: send_message 用现有回放夹具 `feishu_happy_path.json` 端到端回归;
- **行为锁定**: verify PASS/FAIL 的 cursor 语义、TaskContext 整体重建(同连接第二任务零污染)、seq 乱序丢弃;
- **CI 硬门槛**: pytest 全绿 + gradle test 全绿 + pyright basic 零新增错误。

## 7. 迁移步骤（大爆炸式，一次性切换）

1. 协议 v2 + 双端同步切换;
2. 服务端按 3.1 结构重建,旧 gateway.py 废弃;
3. send_message 场景包 + feishu/wechat AppProfile 迁移;
4. 端侧 ConfirmManager/Executor/BuildConfig;
5. 测试体系补齐,回放夹具回归通过即切换完成。

## 8. 工作量预估

| 部分 | 预估 |
|------|------|
| 服务端(结构+场景包+决策层) | 5-7 天 |
| 端侧 | 1-2 天 |
| 测试/CI | 2 天 |

## 9. 明确不做（YAGNI）

- 不实现 send_message 以外的场景包（只留接口和注册机制）;
- 不实现 Session 持久化/多实例部署（单机单连接仍是当前部署形态）;
- 不引入状态机框架/消息队列/Actor 模型等外部依赖;
- AppProfile 不做自动学习，人工/LLM 标注即可。
