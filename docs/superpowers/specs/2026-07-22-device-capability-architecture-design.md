# JoyPhone 设备能力架构设计(Spec)

> **日期**: 2026-07-22
> **状态**: 核心决策已获用户批准(见 §9 决策记录);Provider SPI 详细接口设计留待下一轮
> **前置依据**: `sdk/vivo_sdk.md`(vivo 企业开放 SDK v3.4,首个候选 Provider 的能力参照)
> **动机**: 后续会有多家厂商 SDK(vivo/OPPO/小米/…)及 AOSP 原生能力陆续接入;架构必须在「有 SDK」和「无 SDK」的设备上都成立,且接入新 SDK 不动核心

---

## 1. 背景与问题陈述

当前端侧架构只有一个感知/执行通道:AccessibilityService。它有两个结构性局限:

1. **能力天花板**:无输入注入之外的系统级能力——强杀应用、静默安装、锁定无障碍、常驻保活、原生通话/短信,a11y 全都做不到。
2. **部署脆弱性**:无障碍需用户手动开启(ColorOS/vivo 均会杀后台、掉授权),昨天 OPPO 真机已两次踩中。

vivo 企业 SDK(及后续各厂 SDK)能补上这些能力,但它是**可选的、因设备而异的**。如果架构把 SDK 当一等公民直接调用,OEM 细节会渗漏进每一层;如果当外挂补丁,每家接入都要改核心。

## 2. 核心概念

**抽象的单位不是「SDK」,而是「能力(Capability)」;SDK 只是能力的一种 Provider,无障碍是另一种。**

- **Capability**:一件可做的事,与实现无关。如 `APP_FORCE_STOP`、`SMS_SEND`。
- **Provider**:能力的提供者插件。同一能力可有多个 Provider,按可靠性排序选择。
- **CapabilityMatrix**:设备运行时探测出的能力全集,是该设备一切决策的前提。

**可靠性排序(铁律):原生 API > 厂商系统级 SDK > UI 自动化。** 同一件事多条路都能走时,永远不走 UI。

## 3. 角色定位:SDK 与无障碍

| | 无障碍(A11y) | 厂商 SDK |
|---|---|---|
| 角色 | **通用基座 Provider,永远在场、不可选** | **能力增强 Provider,可选插件** |
| 独有能力 | UI 感知(nodeTree)+ UI 执行(手势)——**SDK 没有输入注入,这两件事只有 a11y 能做** | a11y 做不到的系统级能力(强杀/静默安装/保活/锁无障碍/重启) |
| 何时用 | 所有 UI 感知与 UI 交互;一切能力的最终兜底 | ① a11y 做不到的事 ② a11y 做但不可靠的事(force-stop 保证冷启动) ③ 有原生 API 可绕过 UI 自动化的业务(打电话/发短信) |

注意:**截图多模态已被否决(见 DR-5),不属于本架构的感知通道。**

## 4. 架构总图

```
云端(对 Provider 无感知,只对 Capability 感知)
┌──────────────────────────────────────────────────┐
│ L0 内核:任务生命周期/seq 闸门/LoopGuard(不变)      │
│ L1 场景包:声明所需能力 requires/optional(新增)    │
│ L2 AppProfile:仅 UI 自动化通道需要(不变)          │
│ 决策层:动作空间 = f(该设备能力矩阵) ← 关键变化     │
└───────────────────↕ WS ──────────────────────────┘
端侧(一个 APK,运行时探测,动态装配)
│
│  ┌───────────── CapabilityRouter ─────────────┐
│  │ 能力矩阵 + Provider 链 + 失败降级            │
│  └──┬──────────────┬──────────────┬───────────┘
│     │ A11yProvider │ VivoProvider │ AospProvider│ ← Provider 插件(后续更多厂商)
│     │ (必备基座)    │ (证书存在才激活)│ (原生API兜底) │
│  ┌──┴───────────────────────────────────────┐
│  │ Executor:收到 op → 查能力 → 选 Provider 执行 │
│  └──────────────────────────────────────────┘
```

**为什么 Provider 探测放端侧**:证书有效性、SDK jar 是否存在、权限是否授予,只有设备本地知道,且会动态变化(证书过期、a11y 被杀)。端侧启动时各 Provider `probe()` 自检,Router 汇总成能力矩阵。

## 5. 通信设计

### 5.1 握手首帧:能力上报(协议唯一新增)

WS 连接建立后,端侧首条上行消息:

```json
{"type":"device.hello","deviceId":"...","caps":{
  "PERCEIVE_TREE":true, "ACT_UI":true,
  "APP_FORCE_STOP":true, "APP_INSTALL":true,
  "SMS_SEND":false, "SELF_KEEP_ALIVE":true, "...":"..."}}
```

云端将矩阵挂到该连接的 TaskContext,此后所有决策基于它。矩阵在连接存活期内视为不变;能力动态消失(如 a11y 被杀)通过 action 失败 `ok=false, error="capability_unavailable"` 体现。

### 5.2 能力驱动的动作空间(决策层最大变化)

LLM 动作空间不再写死,由能力矩阵生成:有 `APP_FORCE_STOP` 的设备 prompt 里才有 `force_stop`;`SMS_SEND` 同理。**无 SDK 设备的能力矩阵与今天等价,prompt 零变化、行为零变化**——这是兼容性验收标准。

### 5.3 op 路由全在端侧(DR-4)

云端下发 `Action(op="force_stop", params={pkg})`,端侧 Executor 查 Router 选 Provider 执行;无 Provider 则回 `ok=false, error="capability_unavailable"`,云端决策层据此换路径(降级 UI 自动化或放弃)。**云端永远不需要知道 op 由谁执行,OEM 细节止于端侧。**

### 5.4 协议兼容性

`Action(op, params)` 本为开放枚举,新增 op 不需协议版本号变更;双端对未知 op 的处理(端侧:回 capability_unavailable;云侧:不生成)已足够。`device.hello` 是 v2 内新增消息类型,`PROTOCOL_VERSION` 保持 2。

## 6. 各层职责

| 层 | 职责 | 不知道什么 |
|---|---|---|
| 云端 L0 内核 | 任务状态机、因果闸门、停滞守卫 | 任何设备细节 |
| 云端 L1 场景包 | 目标语义、策略、**声明能力需求** | 能力由谁提供 |
| 云端决策层 | 按能力矩阵生成动作空间、按可靠性排序选通道 | Provider 是谁 |
| 端侧 CapabilityRouter | 能力矩阵、Provider 选择、失败降级 | 任务语义 |
| 端侧 Provider | 单一能力的执行 + 自检(`probe/capabilities/execute`) | 其他 Provider 的存在 |
| A11y | UI 感知 + UI 执行(必备) | — |
| 各厂 SDK | 系统级/原生能力(可选) | — |

**场景能力声明规则(建议默认,实现轮确认)**:场景包声明 `requires`(缺失则 task 开始时拒绝,`reason="capability_unavailable"`)与 `optional`(缺失则降级运行)。例:「打电话」场景 `requires=[CALL_MAKE]` 在无 SDK 设备上直接拒单,而不是硬上 UI 自动化。

## 7. SDK 有/无行为矩阵

| 场景 | 无 SDK(今天) | 有 SDK |
|---|---|---|
| 启动部署 | 手动开无障碍,可能被杀 | 自举:锁定无障碍 + 保活,零接触 |
| 任务前置 | 直接 launch(app 状态不可控) | force-stop 后 launch(确定冷启动) |
| 感知 | nodeTree | nodeTree(截图已否决,见 DR-5) |
| UI 执行 | a11y 手势(两者相同) | a11y 手势 |
| 发消息场景 | UI 自动化 | UI 自动化(输入框无 API,不变) |
| 打电话场景 | 拒单或 UI 自动化 | 直接 CALL API |
| 卡死恢复 | back → abort | back → abort(同) |

同一套 APK、同一个云端,差异全部收敛在端侧 Provider 探测结果里。

## 8. 能力清单初版(枚举,实现轮可增减)

| 能力 | 首选 Provider | 兜底 | 优先级 |
|---|---|---|---|
| PERCEIVE_TREE / ACT_UI | A11y(必备) | — | 基座 |
| APP_LAUNCH | AOSP Intent(通用) | — | 基座 |
| SELF_A11Y_LOCK / SELF_KEEP_ALIVE | vivo SDK | 手动/前台服务 | **P0 自举+保活** |
| APP_FORCE_STOP / APP_CLEAR_DATA | vivo SDK | 无(报不可用) | **P1 冷启动确定性** |
| APP_INSTALL / SELF_UPDATE | vivo 静默安装 | AOSP PackageInstaller(需用户确认) | P2 OTA |
| SMS_SEND / CALL_MAKE | vivo SDK | AOSP SmsManager/Telecom(需角色) | P3 API 直调场景 |
| DEVICE_REBOOT / KEY_CONTROL / NETWORK_CONFIG | vivo SDK | 无 | P4 kiosk/管控 |
| ~~PERCEIVE_SCREENSHOT~~ | ~~reserved,不实装(DR-5)~~ | — | 否决 |

## 9. 决策记录(DR)

| # | 决策 | 理由 | 状态 |
|---|---|---|---|
| DR-1 | 抽象单位是能力不是 SDK;Provider 插件化,各厂 SDK 以 Adapter 接入 | 多厂商接入不动核心;SDK 有无皆可行 | 用户提出并确认 |
| DR-2 | 能力矩阵经握手首帧 `device.hello` 上报,挂连接级上下文 | 决策前提必须云端可知;探测只能在端侧 | 已批准 |
| DR-3 | 动作空间由能力矩阵动态生成;无 SDK 设备 prompt 零变化 | 兼容性验收标准;防止 LLM 生成设备执行不了的 op | 已批准 |
| DR-4 | op 路由全放端侧,云端只感知能力不感知 Provider | 防止 OEM 细节渗漏进云端每一层 | 已批准 |
| DR-5 | **截图多模态不做** | LLM 识图能力尚不足、成本高、对整体能力实现无帮助;能力枚举保留 reserved 占位,环境变化后可重议 | 用户否决 |
| DR-6 | Provider SPI 详细接口设计下一轮单独做 | 本轮先固化整体架构 | 已批准 |

## 10. 下一轮待办(实施轮输入)

1. **Provider SPI 详设**:`probe() / capabilities() / execute(op, params): Result` 的签名、错误模型、降级链语义
2. **协议消息定义**:`device.hello` 模型 + 共享契约测试样本(`shared/protocol/v2/*.json`)
3. **Android 模块结构**:Provider 插件的包结构、反射探测(避免对 vivo jar 硬依赖)、Executor 改造
4. **云端改造点清单**:TaskContext 挂矩阵、DecideInput 带矩阵、prompt 动作空间生成、场景包 requires/optional 声明
5. **首个 Provider**:VivoProvider 范围 = P0(自举+保活)+ P1(force-stop),真机验收
