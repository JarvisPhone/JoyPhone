# 端侧节点合并 + 纯文本通信协议 设计文档

日期：2026-07-14
状态：待实现

## 背景与动机

现象 bug：让 agent 点"飞书"，却点到了负一屏的其它磁贴 / 点错控件。

根因（经 UIFormer 论文 arXiv:2512.13438 调研 + 真实飞书帧数据印证）：

1. **UI 表示占 agent 总 token 80-99%**。纯 JSON→文本仅省约 8%，不是关键。
2. **真正省 50%+ 且防点错的手段是"端侧合并语义等价的碎片节点"**。论文 Fig5 case（标签+控件拆开导致点错）正是本 bug 的形态。
3. 真实飞书消息页帧（`com.ss.android.lark`，31 节点）实测碎片
   - 6 个 `button ""`（idx 1/2/3/5/6/13）：clickable 但 text/desc 全空，LLM 无法区分 → 点错根因（右上角搜索/+号图标就是空 button）。
   - 父子文本重复（`[0]"Ra"` vs `[4]"Ra"`；`[16]text` vs `[17]button`）。
   - 整帧 SoM 编码 650 字符 / 31 行。

结论：**端侧合并碎片节点 + 上下行纯文本协议，一次到位。**

## 目标

- 消除空壳/重复节点造成的歧义（防点错）。
- 降低 UI 表示 token（预计这一帧 31 → ~23 节点，省约 26%）。
- 上下行改纯文本协议，抛弃 `match_text` 子串匹配（bug 高危点）。
- 保留多指令批处理能力，减少 LLM 往返。
- 通信原文持久落盘，便于排障。

## 非目标

- 不做纯视觉方案（论文证实 screenshot-only 更差）。
- 不过度扁平化（保留 scrollable 锚点与必要可点容器）。
- 不做与本目标无关的重构。

---

## 第 1 节：端侧节点合并规则（改造 `NodeFlattener`）

借 UIFormer 的 Filter / Merge / Pass-through，自底向上三条规则。

### 1.1 Filter（丢弃空壳节点，带兜底）

收录 clickable 节点时，按优先级摘 label：

```
text → desc → 子孙节点最近的非空 text/desc → viewIdResourceName 提取的语义
```

四者全空才丢弃。

- 新增纯函数 `viewIdToLabel(viewId: String?):String?`：取 `/` 后最后一段、去掉包名前缀、下划线转空格。
  - 例：`com.ss.android.lark/search_button` → `search`；`.../ic_add` → `ic add`。
- 例外：`editable` 输入框即使无文本也保留（它是操作目标），尽量摘 hint/placeholder。

效果：干掉 6 个 `button ""`；搜索/+号图标靠 viewId 保留为有语义节点。

### 1.2 Merge（父子语义等价合并）

- 同一 label 沿祖先链，只保留**最靠近叶子的 clickable 节点**（点击命中更准）。
- 父 clickable 且 label 来自子孙 → 子孙不再单独收录（被父吸收）；反之子 clickable 而父只是布局容器 → 保留子、丢父。

效果：干掉 `[0]"Ra"`（留 `[4]`）、`[16]text`（留 `[17]button`）。

### 1.3 Pass-through（透传）

- `scrollable` 容器（如 RecyclerView）不带子项文本时，仅作滚动锚点保留，不吸收子项 label；子项各自独立收录。

### 1.4 约束

- 合并后每个节点仍携带稳定 `endId`（indexPath）作引用键。
- 每个可交互节点必须带非空语义 label（带不到走 Filter 丢弃）。
- 不过度扁平化。
- 端侧 `NodeDto` / `UplinkPerception` 新增采集 `viewIdResourceName` 字段。

---

## 第 2 节：上行纯文本 SoM 协议（方案 C1）

### 2.1 现状问题

端侧把 `nodeTree` 序列化为 JSON 数组上行，云侧再转 SoM 文本喂 LLM。JSON 数组这层是纯中间开销。

### 2.2 新方案

上行 `perception` 消息（WS 信封仍是 JSON，但 `screen` 字段改纯文本块）：

```
type: perception
pkg: com.ss.android.lark
ts: 178...
screen: |
  [0] button "search"
  [1] button "Ra"
  [2] button "JoyPhone-2026黑马大赛"
  [3] button "消息"
```

每行格式：`[n] type "label"`，type ∈ input / button / text。

### 2.3 编号语义（方案 C1：映射在云侧）

- 编号 `[n]` 是**短稳定序号**（省 token），语义为"端侧稳定引用"而非数组下标。
- 端侧仍上报每个节点的 `endId` + `bounds`。
- **云侧**编码时给顺序号 `[n]` 并维护 `n → node(含 endId/bounds)` 映射。
- LLM 回 `tap n` → 云侧查映射取 node.bounds 中心 → 下发精确坐标点击。
- **彻底删除 `match_text` 分支**，只认 `[n]` 短号，杜绝子串误命中。

选 C1 理由：贴合现有"云侧决策 + 云侧坐标下发"链路（`_bounds_center` 已在云侧），改动集中在云侧，最小且防错强。

---

## 第 3 节：下行 action 文本指令语法（方案 B + 多指令批处理）

### 3.1 语法（一行一条，动词开头）

| 指令 | 含义 |
|---|---|
| `tap 5` | 点编号 5 节点 |
| `input 5 张三` | 编号 5 输入"张三"（文本取行尾整段，免转义） |
| `swipe up` / `down` / `left` / `right` | 滑动 |
| `back` | 返回键 |
| `home` | 回桌面 |
| `home_first` | 回桌面第一屏 |
| `next_page` | 桌面翻下一屏 |
| `wait 500` | 等 500ms |
| `read` | 重读屏幕 |
| `done` | 任务完成 |
| `abort 未找到应用飞书` | 放弃 + 原因（取行尾整段） |

### 3.2 解析规则（云侧 `parse_actions`）

- 按第一个空格切动词，其余按指令元数解析。
- 文本类参数（input 文本、abort 原因）一律放行尾取整行剩余，天然免转义。
- 无法解析的行 → 记 warn，兜底为 `read`（不乱点）。

### 3.3 多指令批处理

LLM 可输出多行，云侧逐行顺序执行，但需防"旧帧编号失效"：

- **盲操作**（不依赖当前帧编号）：`home` `home_first` `next_page` `back` `swipe` `wait` `read` `done` `abort` —— 可连续多条。
- **依赖编号**：`tap n` `input n ...` —— 执行会导致界面跳转。

**规则：一批 = N 条盲操作 + 最多 1 条 tap/input 收尾。** 遇到第一条 tap/input 执行后本批结束，重新抓帧决策。批里 tap/input 之后的行丢弃并 warn。

云侧逐条下发，每条拿 action.result 后发下一条；收尾 tap/input 后停止本批、触发下一轮 reportScreen。

### 3.4 系统提示词改写

`_SYSTEM_PROMPT` 里 JSON 格式说明整段替换为"输出单行文本指令"+ 上表；说明可多行、依赖编号的 tap/input 只放最后一条；删掉 match_text 相关描述。

---

## 第 4 节：引用键策略

已在第 2 节 C1 内定稿，此处汇总：

- 引用键 = 云侧维护的 `n → node(endId + bounds)` 映射。
- 编号 `[n]` 短、语义稳定；`tap n` 经映射还原为精确坐标点击。
- **删除 `_resolve_tap_node` 的 match_text 分支**，只认 `[n]`。

---

## 第 5 节：测试策略（TDD）+ 调试插桩清理

### 5.1 端侧单测（Kotlin `NodeFlattenerTest`）

- `viewIdToLabel`：带包名/下划线/无下划线/斜杠/null 各 case。
- Filter：clickable + 空 text/desc/子标签/viewId → 丢弃；有 viewId → 保留并标 label。
- Merge：父子同 label 只留最靠叶子的 clickable。
- Pass-through：scrollable 容器保留、不吸子项 label。
- 整帧回归：真实飞书 31 节点 → 合并后节点集，断言无空 label、无父子重复。

### 5.2 云侧单测（Python `test_decision.py` / `test_protocol.py`）

- SoM 编码：node 列表 → `[n] type "label"` 文本块；`n→node` 映射正确。
- `parse_actions(text)`：`tap 5` / `input 5 张三` / `swipe up` / `abort 原因` / 多行批处理 / 非法行兜底为 read。
- 批处理停止规则：`["home_first","wait 300","tap 5","tap 6"]` → 只执行到第一个 tap，第 4 行丢弃 + warn。
- `tap n` → 查映射 → bounds 中心坐标；越界 n 返回 None。
- 删除 match_text 后无回归。

### 5.3 集成/真机验证

编译装机 → 点测试按钮 → 手动进飞书 → 抓帧 → 验证 screen 无空 button、编号稳定、真实任务能点对搜索图标。

### 5.4 调试插桩清理清单（真机验证通过后统一移除）

- `PhoneAgentService.kt`：`DEBUG_ONESHOT_PREFIX`、`readOnlyMode`、`DEBUG_CAPTURE_DELAY_MS` 延迟抓帧分支、测试按钮相关。
- `decision.py`：`frame_dump.json` 转储、`encode_nodes_debug`、各 `[LLM-RAW-*]` 打印。
- 临时文件 `frame_dump.json`。

**真机验证通过前不 commit 到主线。**

---

## 第 6 节：通信原文持久日志（正式功能，非临时插桩）

区分：`frame_dump.json` 等属临时插桩（验证后删）；本节的通信原文落盘为**常驻能力**，实现后保留。

### 6.1 两个文件（各自轮转）

- **`server/logs/comm.log`**（端 ↔ 云原文）：每行 `ts | UP/DOWN | type | 内容`。
  - UP：perception（SoM 文本块）、action.result。
  - DOWN：action 指令行、task.start / done / abort。
- **`server/logs/llm.log`**（云 ↔ LLM 原文）：每行 `ts | LLM-REQ/LLM-RESP | 内容`。
  - REQ：完整 system prompt + user payload。
  - RESP：LLM 未清洗原文。

### 6.2 实现

- 两个独立 Python `logging.Logger` + `RotatingFileHandler`（如单文件 10MB × 5 备份），互不干扰主应用日志。
- 端侧上下行原文继续走 logcat（`Log.i`），不额外落端侧文件（端侧文件读取不便）。

---

## 实现顺序建议

1. 端侧：`NodeDto`/`UplinkPerception` 加 `viewIdResourceName` → `viewIdToLabel` + Filter/Merge/Pass-through（TDD）。
2. 云侧：SoM 文本编码 + `n→node` 映射；`parse_actions` 多指令解析（TDD）；删 match_text。
3. 云侧：改协议解析/下发；系统提示词改写。
4. 云侧：comm.log / llm.log 双文件日志。
5. 编译装机真机验证 → 清理临时插桩 → commit。