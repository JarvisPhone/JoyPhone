# 03 · 语义锚点执行（fail-closed）

> 源码（端侧）：`android/.../accessibility/{AnchorResolver,Executor}.kt`
> 源码（云端）：`server/app/scenario/ui.py` 的 `resolve_anchor_node`

这是整个系统安全性最关键的一环，直接源于 **2026-07-22 的"点错群"事故**。

## 问题：坐标会过期

早期实现里，云端下发 tap 时携带绝对坐标 `(x, y)`。但从"云端拿到某一帧"到
"端侧真正执行这一 tap"之间存在延迟，界面可能已经滚动/刷新，导致坐标指向的
早已不是原本那个节点——最严重的一次点进了错误的群，险些把消息发错人。

**根因：坐标是"某一帧的快照"，帧一过期就点歪。**

## 解法：只下发语义锚点，端侧实时重定位

云端**不再下发坐标**，改为下发**语义锚点**（`Anchor`）：

```kotlin
data class Anchor(val text: String?, val rid: String?, val occurrence: Int?)
```

- `text`：节点文本（业务语义最强，列表行通常唯一）
- `rid`：resource-id 尾段
- `occurrence`：同名多命中时的序号

端侧执行 tap/input的**那一瞬间**，用 `service.rootInActiveWindow` 拉取
**当前实时树**，按锚点重新定位节点，用"当下的" bounds 计算点击中心。这样即使
界面变了，也是在"现在真实看到的树"上找目标，而不是照着过期坐标戳。

## fail-closed：宁可报错，绝不猜

`AnchorResolver.resolve` 返回三态之一：

```kotlin
sealed interface ResolveResult {
    data class Found(val node)     // 唯一命中 → 执行
    data object NotFound           // 没找到  → 报 anchor_not_found
    data class Ambiguous(count)    // 多命中且无法收窄 → 报 anchor_ambiguous
}
```

**核心原则：只有唯一命中才动手，NotFound / Ambiguous 一律 fail-closed 报错**，
把错误码（`anchor_not_found` / `anchor_ambiguous` / `anchor_missing` ...）随
`action_result` 回传云端，由云端决定回落 LLM 或终止。

**明确禁用子串匹配**——子串会误中同名磁贴/群名（"张三" 命中 "张三丰"），这正是
事故温床。要么精确相等，要么不匹配。

## 解析阶梯（云端与端侧同一语义）

`AnchorResolver.resolve` 与云端 `resolve_anchor_node` 实现**完全一致的阶梯**，
保证两端对"同一锚点指向哪个节点"的理解不会分歧：

```
1. text 精确相等                （最具业务语义）
2. desc 精确相等                （text 落空时）
3. rid 尾段精确相等             （仅文本层全空时兜底）
   —— 为什么 rid 垫底？列表行常复用同一容器 rid，rid 先行会把唯一的
      文本行淹没在 N 个同 rid 兄弟里，反而制造歧义
4. 文本层多命中且有 rid → 用 rid 在候选内收窄
5. 仍多命中 → 按 occurrence 选取；无 occurrence → Ambiguous
```

`editableOnly=true`（input 专用）时只在 editable 节点里解析，避免把正文写进
非输入框。

## Executor：哑执行器 + 节点回收纪律

`Executor.kt` 把动作分为：

| op | 说明 |
|----|------|
| `tap` | 锚点重定位 → 取 bounds 中心 → 派发点击手势 |
| `tap_at` | **逃生舱**：原始坐标点击，仅用于画布/地图等无语义节点场景，正常任务不生成 |
| `input` | 锚点解析出目标 editable 的 id 路径 → 在活树按路径找到节点 → `ACTION_SET_TEXT` |
| `swipe` / `back` / `home` | 手势 / 全局动作 |
| `read_screen` / `wait` | 空操作，恒 ok（真正结果由后续帧体现） |

两个工程细节值得注意：

1. **节点回收纪律**：`AccessibilityNodeInfo` 需显式 `recycle()` 防泄漏。
   代码用清晰的所有权约定（"命中节点所有权转移给调用方"）+ `try/finally`
   保证遍历中未命中节点即时回收、root 由拿取方回收，还特意处理了
   "editable 就是 root 本身（id=0）" 的 double-recycle 陷阱。

2. **手势 fire-and-forget**：`dispatchGestureFireAndForget` **不等待**
   `GestureResultCallback`。因为实测部分 ROM 上回调延迟 1.7~6s，若在 WS reader
   线程上等待会把后续动作全堵在队列里（**2026-07-21 back 延迟 6s 导致误判
   abort 的事故根因**）。返回值只代表"框架已受理"，动作真实结果交给云端凭后续
   perception 帧判定——**归位判定在云端**。

## 云端如何复用锚点

`resolve_anchor_node` 让云端策略（`ConfirmInterceptPolicy` / `WrongChatInputPolicy`
等，见 04）能把 LLM 决策出的 action **还原成语义节点**，从而判断"这个 tap 是不是
点在发送按钮上""这个 input 是不是往正文框输"，而**不依赖会过期的坐标**。两端共用
一套解析语义，是这套设计能自洽的前提。

## 设计取舍小结

| 取舍 | 选择 | 理由 |
|------|------|------|
| 下发坐标 vs 下发语义锚点 | 语义锚点 | 坐标过期点歪（错群事故） |
| 子串匹配 vs 精确匹配 | 精确匹配 | 子串误中同名项 |
| rid 优先 vs 文本优先 | 文本优先，rid 垫底 | rid 复用会淹没唯一文本行 |
| 等手势回调 vs fire-and-forget | fire-and-forget | 回调延迟堵队列（误判 abort 事故） |
| 端侧判定归位 vs 云端判定 | 云端判定 | 端侧只做哑执行，职责单一 |

## 延伸阅读

- 锚点从哪来（LLM 决策时抽取）→ [01-decision-engine.md](01-decision-engine.md)
- 云端策略如何用锚点做确认/守卫 → [04-scenario-pack.md](04-scenario-pack.md)