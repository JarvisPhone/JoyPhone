# JoyPhone 技术深度剖析

本目录是对 JoyPhone（云-端协同 AI 手机智能体）各核心技术方向的深度剖析，
面向想快速建立系统级心智模型的开发者。与 `docs/superpowers/` 下按时间线组织的
plans / specs 不同，本目录按**技术方向**横向切分，聚焦"为什么这么设计"与
"关键实现细节"，是可长期维护的技术知识库。

## 项目一句话

云端（FastAPI / Python）当"大脑"负责决策，Android（Kotlin / 无障碍服务）当
"手眼"负责感知与执行，两端通过 WebSocket（协议 v2）实时协同，完成"给某人发消息"
这类跨 App 的手机自动化任务。

## 六层分层架构

```
protocol   —— 云端与端侧的消息契约（Action / Node / Perception / 上下行帧）
gateway    —— WS 握手鉴权、消息编解码、每设备连接生命周期
task       —— 任务内核：TaskContext / FSM / 策略管道 / 上行分派（与业务无关的安全底座）
scenario   —— 场景包：意图匹配 + 目标解析 + 技能模板 + 前后置策略 + App UI profile
decision   —— 决策引擎：cache → skill → pkg_guard → LLM 分级回退，恒产出动作
infra      —— 配置、LLM 客户端、日志等基础设施
```

数据流：端侧上行 `perception` 帧 → task 内核跑 PRE 策略 → decision 引擎产出动作 →
task 跑 POST 策略 → 下行 `action` → 端侧按语义锚点在实时树重定位并执行 →
上行 `action_result` → 云端对账推进 cursor / 补帧。

## 文档索引

| 文档 | 方向 | 核心问题 |
|------|------|----------|
| [01-decision-engine.md](01-decision-engine.md) | 决策引擎分级回退 | 每一帧如何恒定产出一个可执行动作？四级回退如何取舍？ |
| [02-task-kernel.md](02-task-kernel.md) | 任务内核 | FSM / 策略管道 / 因果对账闸门如何构成安全底座？ |
| [03-semantic-anchor.md](03-semantic-anchor.md) | 语义锚点执行 | 为什么不下发坐标？fail-closed 如何防误点错群？ |
| [04-scenario-pack.md](04-scenario-pack.md) | 场景包与 App 适配 | 如何用可插拔场景包承载业务，同时保留纯 LLM 兜底？ |
| [05-skill-cache.md](05-skill-cache.md) | 技能缓存泛化沉淀 | 成功轨迹如何泛化成可复用技能并安全回放？ |

## 贯穿全局的设计哲学

1. **fail-closed（安全失败）**：匹配不到宁可报错，绝不模糊猜测。语义锚点解析、
   消息输入框识别、发送前确认，处处优先"保守失败"而非"激进尝试"。
2. **归位判定在云端，端侧是哑执行器**：端侧只做原子动作（tap / input / swipe），
   不判断"是否成功"，一切归位由云端根据后续 perception 帧裁决。
3. **因果对账**：变更类动作（mutating）必须 ack 且抓到新帧后才允许下一步决策，
   杜绝"用旧帧做终态决策"（见 02 文档 F2 闸门）。
4. **分级回退恒产出**：`decide()` 永远返回非空动作，从确定性最高的 cache 逐级
   退到最灵活的 LLM，兼顾效率与鲁棒。