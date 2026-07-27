# 桌面找图标守卫（home_locate_guard，纯云端确定性）设计

日期：2026-07-27
状态：待实施

## 背景与动机

实测 log（task-83a32db5，目标「打开飞书发消息」）暴露一个比 title_tap_guard 更前置的
失败：**agent 在桌面阶段根本进不了飞书**。

时间线还原：
1. 目标 target_pkg=`com.ss.android.lark`。
2. 桌面首屏 25 个图标里**独缺「飞书」**（有 VibeVoice/王者荣耀/JoyPhoneAgent 等）。
3. LLM 看不到飞书 → 盲目乱点：`open_notifications` → tap `JoyPhoneAgent`（进控制中心）
   → tap `VibeVoice`（进别的 app）。
4. pkg_guard 反复救场（control_center→back / in_app→home / minus_one→swipe）兜圈。
5. `task.abort reason=pkg_guard_stuck:in_app` 中止。

**根因**：目标 app 图标不在桌面首屏，而系统**无包名直启能力**（用户已否决 open_app /
am start / QUERY_ALL_PACKAGES，见 2026-07-13 设计），只能靠在桌面 tap 图标启动。

**历史脉络**：
- 2026-07-13「真人式打开应用」设计：移除 open_app 直启，改端侧 `home_first_page`/`next_page`/
  `atEnd` 算子 + **LLM prompt 引导**找图标/翻页/放弃。
- 2026-07-16「场景状态机重构」：删除端侧 `homeFirstPage`/`nextPage`/`HomeDetector`/
  `ScreenFingerprint` 算子与复合 op，端侧回归哑执行器，`atEnd` 字段暂留恒 false。
- 实测证明「靠 LLM prompt 引导翻页」这条路没走通——LLM 在桌面照样乱点。

**本设计的收口**：把「找图标 / 翻页 / 放弃」从 LLM 手里彻底收回云端，做成**确定性守卫**，
端侧保持哑执行器不动。

## 目标

- 在桌面场景（HOME）用云端确定性逻辑找目标 app 图标：找到就 tap，没找到就自动翻页，
  翻到底仍未找到就 abort。LLM 完全不参与桌面找图标阶段。
- 端侧、协议**零改动**：复用现有 `swipe`（支持 direction 参数）、`tap`、场景机
  `detect_scene`、`AppProfile.aliases`。
- 根治「目标图标不在首屏 / 藏在其他屏」导致的桌面乱点与 pkg_guard_stuck 兜圈。

## 非目标

- 不引入任何包名直启（open_app / am start / deep_link）——用户已明确否决。
- 不做 app 抽屉 / 搜索启动（本设计只覆盖桌面左右翻页找图标）。
- 不动端侧算子（沿用 2026-07-16 哑执行器决策，不恢复 home_first_page/next_page）。
- 不做翻页手势真机参数最终校准（留待联调）。

## 整体架构与数据流

决策链现状（`engine.py:407 decide`）：`cache → skill → pkg_guard → LLM`。

本设计在 `pkg_guard_action` 之后、`_llm_decide` 之前插入新守卫 `home_locate_guard`：

```
decide():
  cache.lookup        -> 命中返回
  skill.next_step     -> 命中返回
  pkg_guard_action    -> 非 HOME 的错误场景收敛回 HOME
  home_locate_guard   -> 【新增】HOME 且未进目标 app 时,确定性找图标/翻页/abort
  _llm_decide         -> 进了目标 app 后才交给 LLM
```

数据流（单帧）：

```
端侧 reportScreen(nodeTree) ↑
云端 decide → home_locate_guard:
  detect_scene==HOME 且 pkg!=target_pkg ?
    ├─ 否 → 放行(return None),走后续 pkg_guard/LLM
    └─ 是 → 按 guard 状态机:
         · 找图标(aliases 匹配 nodeTree) 命中 → 下发 tap ↓
         · 未命中 → 按阶段下发 swipe(right 归位 / left 扫描) ↓
         · 扫描到底仍未找到 → 下发 abort(app_not_found) ↓
端侧执行 → 下一帧重抓 → 云端重判(逐帧收敛)
```

原则（延续项目分层）：
- **端侧纯哑算子**：只执行 swipe/tap，不知道「在找图标」。
- **决策全云端确定性**：找图标/翻页/放弃不问 LLM。
- **逐帧收敛**：每步下发一个动作，端侧执行后重抓帧，云端重判状态机（与 pkg_guard 同模式）。
- **放弃复用现有链路**：abort → TaskAbort → UI 提示用户，不新增机制。

## 组件设计

### 1. 新模块 `server/app/decision/home_locate.py`

纯逻辑模块（可单测），核心函数：

```python
def home_locate_action(
    perception: Perception,
    target_pkg: str,
    aliases: list[str],   # 来自 AppProfile.aliases,如 ["飞书","feishu","lark"]
    guard: dict,          # 跨帧状态,复用 DecideInput.guard
) -> list[Action] | None:
    """桌面找图标守卫。返回动作列表;不该介入(非 HOME/已进 app/已找到)返回 None。"""
```

判定顺序：
1. 若 `detect_scene(perception) != HOME` 或 `perception.pkg == target_pkg` → `return None`（放行）。
2. **找图标**：`find_icon(perception.nodeTree, aliases)` 扫节点 text/desc，命中返回该节点。
   - 命中 → `return [tap(match_text=图标文案)]`，并清理 guard 的翻页状态。
3. **未命中** → 进翻页状态机（见下）。

### 2. 翻页状态机（guard dict 内,跨帧保持）

guard 里新增命名空间 `home_locate`，字段：
- `phase`: `"homing"`（归位中）| `"scanning"`（扫描中）。初次进入为 `"homing"`。
- `last_fingerprint`: 上一屏图标文案集合指纹（frozenset / 排序后 tuple）。
- `swipe_count`: 已翻屏数（安全上限兜底，防指纹/场景判据双失效时死翻）。

**归位阶段（phase=homing，你确认「做完整归位」）**：
- 下发 `swipe direction=right`（向右滑=看左边屏，逐屏回退）。
- **到头判据（负一屏）**：swipe right 后 `detect_scene` 变 `MINUS_ONE` → 说明越过首屏
  （首屏在负一屏右侧一格）→ 下发 `swipe direction=left` 退回首屏，切 `phase="scanning"`。

**扫描阶段（phase=scanning）**：
- 每帧先找图标（命中即 tap，同上）；未命中则下发 `swipe direction=left`（向左滑=看右边屏）。
- **到头判据（指纹）**：swipe left 后新屏图标文案集合与 `last_fingerprint` 完全相同
  → 已是最后一屏 → 下发 `abort`（reason=`app_not_found:<app_label>`）。
- 每次 swipe 后更新 `last_fingerprint`。

**方向 × 到头判据小结**（关键设计,来自用户补充）：
| 方向 | 用途 | 到头判据 |
|---|---|---|
| swipe right | 归位到首屏 | 场景变 `MINUS_ONE`（越过首屏） |
| swipe left | 逐屏扫描 | 图标文案集合指纹前后相同 |

理由：向右到头会滑进负一屏，用现成场景机判定比指纹稳；向左到头无特殊场景，只能靠指纹。

**安全上限**：`swipe_count` 超过阈值（如归位 8 屏 / 扫描 12 屏）强制 abort，防双判据失效死翻。

### 3. 图标文案指纹 `_screen_icon_fingerprint(nodeTree) -> frozenset[str]`

- 取所有节点非空 `text`/`desc`，strip 后收进集合。
- 用集合（无序、去重）而非整树深比：轻量稳定，避免动画/时间戳/坐标微差误判。
- 与 2026-07-13 端侧 `fingerprint` 思路一致,但改在**云端**用协议 nodeTree 计算（端侧不动）。

### 4. 图标匹配 `find_icon(nodeTree, aliases) -> Node | None`

- 遍历节点，若节点 `text` 或 `desc`（strip 后）等于或包含任一 alias → 命中返回。
- 命中优先级：完全相等 > 包含。多个命中取第一个。
- 下发 tap 用命中节点的可见文案作 `match_text`（与现有 tap anchor 机制一致，端侧
  AnchorResolver 再解析坐标）。

### 5. engine.decide 接线（`engine.py:419` 后）

```python
guarded = pkg_guard_action(d.frame, d.target_pkg, d.guard, self._escape_llm)
if guarded is not None:
    return Decision(actions=guarded, source="pkg_guard")

# 新增:桌面找图标守卫
profile = _ui_profile_for_pkg(d.target_pkg)
aliases = profile.aliases if profile else []
located = home_locate_action(d.frame, d.target_pkg, aliases, d.guard)
if located is not None:
    return Decision(actions=located, source="home_locate")

return self._llm_decide(d)
```

- `aliases` 为空（未注册 profile）时，`home_locate_action` 内部找不到图标就只能翻页扫描
  到底 abort——退化为「翻遍所有屏都没有」，可接受（本就无从匹配）。

## 错误处理

- **图标文案变体**（如图标只有 icon 无文字、或文案是「Lark」大小写差异）：aliases 已含
  中英文变体；匹配用 strip + 大小写归一 + 包含兜底。仍匹配不到则翻页到底 abort，reason
  明确告知用户「未找到应用」,不静默卡死。
- **负一屏判据失效**（某些 launcher 无负一屏）：`swipe_count` 安全上限兜底，归位阶段翻满
  上限仍未见 MINUS_ONE 则直接切 scanning（从当前屏扫）。
- **指纹抖动**（桌面有动态 widget 导致文案帧间微变）：指纹只取图标类文案集合，且要求
  **完全相同**才判到头；偶发不等只会多翻一屏，由 swipe_count 上限兜底。
- **abort reason** 走现有 TaskAbort → 端侧 UI 链路，复用不新增。

## 测试策略（TDD 纯逻辑先行）

云端纯函数单测（`server/tests/`）：
1. `_screen_icon_fingerprint`：相同图标集不同顺序 → 指纹相等；增删一个图标 → 不等。
2. `find_icon`：nodeTree 含「飞书」→ 命中；不含 → None；大小写/包含变体命中。
3. `home_locate_action` 状态机（构造 Perception 帧驱动）：
   - HOME且命中图标 → 返回 tap。
   - HOME 未命中 + phase=homing → 返回 swipe right；场景变 MINUS_ONE → swipe left 切 scanning。
   - scanning 未命中 → swipe left；指纹前后相同 → abort(app_not_found)。
   - 非 HOME / 已进 target_pkg → 返回 None（放行）。
   - swipe_count 超上限 → 强制 abort。
4. engine.decide 接线：pkg_guard 放行后进 home_locate；进 app 后交 LLM。

**先写失败复现测试**（systematic-debugging Phase 4）：用实测帧（visible_nodes 无飞书的
桌面首屏）构造 Perception，断言旧行为会走 LLM（乱点），新守卫会返回 swipe。

真机联调（不写单测）：swipe direction 手势真机生效、负一屏识别、指纹稳定等待时间。

## 分 commit 计划

1. `test(server): home_locate 纯函数失败复现测试(指纹/find_icon/状态机)`
2. `feat(server): home_locate_guard 桌面找图标守卫(纯云端确定性)`
3. `feat(server): engine.decide 接线 home_locate(pkg_guard 后 / LLM 前)`
4. （联调后）`fix: 真机翻页手势 / 负一屏判据 / 指纹等待参数校准`

## 风险与待联调项

- swipe direction=right/left 手势真机是否精确翻一屏、负一屏能否稳定 MINUS_ONE、指纹等待
  时间——均需真机联调。
- 改 engine/decision 后需重启 uvicorn。
- 真实 LLM decide 较慢，但本守卫在桌面阶段**不调 LLM**，桌面找图标应显著提速。
- aliases 未覆盖的 app 会退化为「翻遍到底 abort」，后续可扩充 profile 或加图标 rid 匹配。