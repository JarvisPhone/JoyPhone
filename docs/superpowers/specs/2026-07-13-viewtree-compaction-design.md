# View Tree 感知裁剪与紧凑编码设计

日期：2026-07-13
分支：feat/app-driven-goal
状态：已批准，待实施

## 背景与动机

真机联调时触发 TEST_GOAL，agent 在飞书误跳到微博页面，端侧 `NodeFlattener.flatten`
一次性产出 **2973 个节点**，云端 `decision.py` 把全量节点 `model_dump` 成 JSON 塞进 LLM
prompt，直接触发 `openai.BadRequestError: 400 - context window exceeds limit (2013)`，
WS 循环崩溃断连。

根因两层：

1. **过滤条件太宽**：当前 flatten 规则是「可见 且 (可点击 或 有文本)」。微博信息流里每条微博的
   正文/昵称/时间/转发数/评论数全是「有文本」节点，全被收进来，一屏上千节点，全是决策噪声。
   而找图标 / 点 tab / 填输入框只需要「可操作的结构元素」，不需要「内容文本」。
2. **格式费 token**：每节点 `model_dump` 成 JSON（键名 `id`/`text`/`desc`/`className`/`bounds`/
   `clickable`/`editable` 逐节点重复），其中 `bounds`（4 个坐标整数）纯 token 浪费——真机实测确认
   端侧 `Executor.tap` 只用 `match_text` 重新查节点算坐标（`findByText`），**根本不消费 LLM
   传回的 id/bounds**。JSON 带 bounds 约 40–60 token/节点，编号文本约 5–15 token/节点。

## 业界调研结论（支撑决策）

- **单层强过滤**（DroidBot-GPT arXiv:2304.07061 / AutoDroid 主流做法）：只保留可交互节点
  （clickable/scrollable/editable/checkable + 有 text 或 contentDescription），纯内容 TextView 丢弃。
- **编号文本列表**替代 JSON：`[3] button "发布"`（agent-browser AX 快照格式），几乎无人回传 bounds，
  端侧靠 text/resource-id 重新定位。
- **分层递进（coarse-to-fine）业界罕见**：Android 单屏可交互元素本就只几十个，单层强过滤即可放进上下文，
  多轮 expand 徒增 LLM 往返延迟与出错面。**故放弃分层，采用单层强过滤。**

## 目标

- 端侧感知从「无差别收集所有可见文本」改为「只收可操作结构元素 + 子树向上合并保护图标/可点父容器」。
- 传给 LLM 的表示从 JSON 全字段改为紧凑编号文本行，去 bounds/className，text 截断。
- 巨型页面（2973 节点）降到几十个节点，token 从数万降到 <1000，彻底消除上下文溢出。
- 端侧执行不变：仍靠 text/desc 重定位（LLM 只回 match_text）。

## 非目标

- 不做分层递进感知（业界罕见，YAGNI）。
- 不引入多模态截图 / Set-of-Marks（token 成本大、依赖多模态模型）。
- 不改 tap/input 的端侧定位机制（继续 findByText / findEditable）。

## 整体架构与数据流

```
端侧 rootInActiveWindow
  → NodeFlattener.flatten（强过滤 + 子树向上合并）→ List<NodeDto>（几十个可操作节点）
  → UplinkPerception ↑（node_tree 仍为结构化 NodeDto，端云协议不变）
云端 gateway 收 Perception
  → decision.decide：把 nodeTree 编码为紧凑编号文本行喂给 LLM（去坐标/className，text 截断）
  → LLM 返回 {op, params:{match_text|id|text}}
端侧执行：tap 用 match_text 重定位；input 用 text
```

**关键分工**：端侧负责「过滤节点数量」（少传垃圾节点），云侧负责「紧凑编码格式」（省 token）。
两者正交，各自可单测。协议 NodeDto 结构保持不变（向后兼容），是节点数量变少、云侧编码变紧凑。

## 组件设计

### 1. 端侧强过滤（NodeFlattener.walk）

过滤规则从 `visible && (clickable || 有text)` 改为：

**保留节点当且仅当** 可见 且满足任一：
- 可交互：`isClickable || isEditable || isScrollable || isCheckable`
- 或 携带可定位语义：有非空 `contentDescription`（图标常靠 desc）

**子树向上合并（保护图标 / 可点父容器）**：
- 很多桌面图标 / 按钮自身 `clickable=false`，真正可点的是父容器；文本又常在更深的叶子。
- 规则：向下递归时，若当前节点可交互（clickable/editable），把其**子树中最近的非空 text/desc**
  合并上来作为该可点节点的 `text`（若自身 text 为空）。合并后**不再单独收录那些纯文本叶子**，
  避免「可点父 + 一堆文本叶」重复。
- 纯内容文本节点（无可交互祖先直接关联、纯信息流正文）不收录。

### 2. text 截断

- 单节点 `text` / `desc` 超过 `MAX_TEXT_LEN`（20 字）截断加省略号，避免长正文吃 token。
- 截断在端侧 flatten 时做（NodeDto 已是裁剪后表示）。

### 3. 云侧紧凑编码（decision.py）

新增 `_encode_nodes(nodes) -> str`，把 `perception.nodeTree` 编码为编号文本行：

```
[0] tab "首页"
[3] icon "微博"
[5] input "搜索"
[8] button "发布"
```

- 序号 = 节点在 nodeTree 中的下标（LLM 可回 `{"id": "3"}` 或`{"match_text": "微博"}`）。
- 类型标签由 className/clickable/editable 推断：editable→input，clickable→button/icon/tab，其余→text。
- 去掉 bounds、className、原始 id 串；只留 序号 + 类型 + 文本（text 优先，无则 desc）。
- payload 从 `{"goal","nodes":[JSON...],"history"}` 改为 `{"goal","screen":"<编号文本>","history"}`。
- 更新 `_SYSTEM_PROMPT`：说明 screen编号元素列表，tap 可用 match_text 或行号 id。

### 4. 兜底上限（防御纵深）

即便强过滤后，极端页面仍可能偏多。保留一个数量上限 `MAX_LLM_NODES`（如 80）作为最后防线：
超出则截断（可交互节点优先保留）。这是 defense-in-depth，正常情况下强过滤已使其不触发。

## 错误处理

- flatten 合并时空 text 且空 desc 的可交互节点仍保留（用类型标签占位，如 `[7] button ""`），
  LLM 可用行号 id 点击。
- 云侧编码空 nodeTree → `screen` 为空串，prompt 已有「信息不足→read_screen」兜底。

## 测试策略

**端侧（NodeFlattenerTest）**：
- 纯文本叶子（无可交互祖先）被丢弃。
- clickable=false 的图标父容器 + 深层 desc 叶子 → 合并为一个带 desc 的可点节点。
- editable / scrollable / checkable 节点保留。
- 长 text 截断到 MAX_TEXT_LEN。

**云侧（test_decision.py）**：
- `_encode_nodes` 输出编号文本行格式正确（类型标签 + 文本）。
- 巨型 nodeTree（3000 节点）经强过滤+上限后，编码结果节点数 ≤ MAX_LLM_NODES。
- 可交互节点在上限裁剪时优先保留（不被纯文本挤掉）。
- payload 用 `screen` 字段而非 `nodes`。

## 实施顺序

1. 云侧紧凑编码 `_encode_nodes` + payload 改 `screen` + prompt 更新 + 上限兜底（TDD）。
2. 端侧强过滤 + 子树向上合并 + text 截断（TDD）。
3. 真机联调复测微博/飞书页面节点数与 token，验证不再溢出。