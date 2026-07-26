# LLM 通信内容改造方案(2026-07-25)

> 目标: 重新设计云端发给 LLM 的整块通信内容,涵盖场景上下文、退出路径、反馈通道、决策契约等。**非 JSON**,自然语言文本块 + 稳定段落结构,根据当前 `Scene × AppPage × 当前动作阶段` 动态拼装。
> 来源: 用户反馈 + roadmap 2026-07-25 §二/§三/§四 + 真机 8 帧样本量化(总 payload 5.1k~6.7k 字符,系统提示词占 4.8k)+ harness engineering 参考(Lil Weng 2026-07-04 / MobileAgent-V / V-Droid / Screen Agent)。

---

## 0. 问题诊断(为什么「内容不够」是 root cause,而不是「格式不对」)

| # | root cause | 现状证据 |
|---|---|---|
| 1 | **场景语义用 prompt 教,不是结构化字段** | `_SYSTEM_PROMPT` 写「scene=launcher.home 是 ColorOS 负一屏」是教学,LLM 概率遵守,真机五轮事故 |
| 2 | **「怎么出去」是一段长 prompt 文字** | `exit_hint` 当前是自然语言字符串,但**每个 Scene/AppPage 都有一行,塞 system prompt** 占据大量字符,LLM 还得分清哪个适用 |
| 3 | **screen 节点只有 `类型+文本`,缺位置/层级/角色** | `[3] button "搜索"` 没说「在顶部」,LLM 不知道这是顶部搜索框还是列表项按钮 → 真机错点事故 |
| 4 | **「上一条指令结果」是自然语言块,LLM 解析不稳** | 现在 `[feedback]` 块是「字段: 值」混合文本,信息密度低、格式脆弱 |
| 5 | **重复 LLM 调用费 token 不止,真正问题是 LLM 拿到信息做不了判断** | 「连按 back+home」循环 = LLM 不知道 back 后会到哪页、该 back 几次 |
| 6 | **action space 写死,LLM 自由发挥 tap 表达认知(核查标题)** | roadmap §4.2;需要 `expect` 类零副作用指令,但**目前 expect 之外还需要更多「LLM 想问的认知问题」通道** |

---

## 1. 设计原则(从借鉴项目提取)

| 原则 | 出处 | 在 JoyPhone 的落地 |
|---|---|---|
| **observe → ground → act → verify** | Screen Agent / Lil Weng | 整段 payload 拆成「观察→定位→行动→验证」四段,顺序固定 |
| **Tool contract 是模型判断的一部分** | Anthropic tool-use docs | 每个 op 的描述写「作用 + 副作用 + 何时用 + 失败会怎样」,而不是只写一句动词 |
| **场景 = 结构化字段,不写进 prompt** | MobileAgent-V / V-Droid | `scene` / `page` / `task_phase` / `app_role` 都是字段,不是 prompt 段落 |
| **失败反馈要让 LLM 知道「后果」而非「报错」** | OReilly harness | feedback 段不只 `ok/fail`,要写「后果是什么 + 你现在面对的现实是什么」 |
| **memory 是 curated,不是 raw transcript** | Lil Weng | 我们不重复推全 history,只发与下一步决策强相关的最近 N 条轨迹 |
| **token 是 reasoning 资源,不是无限资源** | Screen Agent | 每个 scene 给一个「该场景最小必要信息清单」,其余裁掉 |

---

## 2. 核心设计 —— Payload 四大段

把发给 LLM 的整块内容拆成 **四个稳定段落**,顺序固定、每段语义清晰。这不是 JSON,就是纯文本块,但**段名是约定**让 LLM 看到段名就知道这是什么信息。

```
┌────────────────────────────────────────────────────────┐
│ [OBSERVE]   屏幕现状(scene/page/节点树/布局摘要)         │
│ [GROUND]    你在哪里、要到哪去、还有多远、怎么出去       │
│ [ACT]       可用操作清单 + 你的最近动作                   │
│ [VERIFY]    上一条动作的结果 + 现在的反馈                 │
└────────────────────────────────────────────────────────┘
   上下两件事:
   - [SCENE-BRIEF] 当前场景专有补充(如 launcher.minus_one 警告)
   - [INSTRUCTION] 任务目标(短)
```

**为什么不是 JSON**:roadmap 已经拍板「非 JSON」,且 LLM 对自然语言段名 + 列表 + 缩进的解析更稳(JQ 都能 parse 但 LLM 容易数错嵌套括号)。我们要的是**清晰的章节 + 行内约定**。

---

## 3. 每段设计细节

### 3.1 `[OBSERVE]` —— 屏幕现状

```
[OBSERVE]
pkg: com.ss.android.lark
scene: app (page: app.inbox_list)        ← 一行解决 "你在哪",scene 树已实装
layout:
  top    : [搜索框] + [返回]
  middle : [会话列表]   (10 项)
  bottom : [tab: 消息 / 通讯录 / 工作台 / 我]
visible_nodes:                          ← 只列可交互 + 标题节点
  [0] input "搜索"                      ← 顶部
  [2] button "Android AI 开发组"       ← 列表项
  [4] button "张三"
  [7] tab "消息" (current)
  [8] tab "通讯录"
```

**关键改动**:
1. **`scene` + `page` 合一行**:`scene: app (page: app.inbox_list)`,LLM 一眼知道顶层 + app 内页型
2. **`layout:` 替代 `nav_map`**——给出「顶部 / 中部 / 底部各有什么角色」,人类直觉,LLM 直接映射
3. **`visible_nodes:` 替代 `[screen]` 节点清单**——只列可交互元素 + 标题,剔除纯装饰(原 prompt 里说「禁止 tap label/text」,那干脆不发)
4. **节点标签加位置前缀**:`[顶部]` / `[列表项]` / `[底部]`,LLM 不用数序号反推

### 3.2 `[GROUND]` —— 你在哪里 + 到哪去 + 还有多远 + 怎么出去

```
[GROUND]
target: 飞书 → 群 "Android AI 开发组" → 发消息
position: pkg=com.ss.android.lark, scene=app(page=inbox_list)
         ⇒ 已在目标 app, 还差 2~3 步: 找到群 → 进群 → 发送
depth: app 内 [back 0 次]
exit_path: 单 back 返回上一级(若在 app.chat 则回到 inbox_list);
          多次 back 仍困 → home 兜底;
          绝不要 back+home 交替振荡(会被 LoopGuard 拦截)
prev_subgoal: 无 / [上一步目标]
```

**关键改动**:
1. **`target:` 用自然语言一句话说清楚任务目标 + 子目标**——LLM 知道「我现在要做到哪一步」
2. **`position:` 紧凑表达当前位置 + 与目标的距离**——LLM 不会迷茫「我已经走了多远」
3. **`depth:` 量化 back 次数 / page 层级**——解决「该 back 几次」问题
4. **`exit_path:` 单一自然语言段**——取代 `exit_hint` 多行 prompt,LLM 看到一个完整方案,不用从多条提示中挑
5. **`prev_subgoal:` 让 LLM 知道「我上一帧的目标完成了没」**——避免重复决策

### 3.3 `[ACT]` —— 可用操作 + 最近动作

```
[ACT]
available:
  tap <n | "文本">       语义锚点点击,失败时按新屏幕决策(不要重复同一锚点)
  longpress <n>          长按 800ms,触发上下文菜单
  input <n> <文本>       在输入框输入;会自动替换现有内容
  swipe <up|down|left|right>    屏幕内滚动
  back                   返回上一级(在 app 内只按一次)
  home                   回桌面(只有 pkg != target_pkg 时才能用)
  press_enter            输完即搜索
  expect title "X"       核查当前页标题,不点击任何东西
  expect pkg "com.x"     核查前台应用
  expect "文本"          核查屏幕里是否有该文本
  read                   当前帧信息不足,重新读取
  wait <ms>              等动画
  done                   任务完成,需四条件全满足(见 §完成契约)
  abort <原因>            放弃并说明原因

last_3_actions:
  tap "通讯录"        → ok
  tap "Android AI 开发组" → ok
  tap "发送"            → failed: 节点不存在 (frame 已是 chat 页)
```

**关键改动**:
1. **op 列表是结构化的「动词 + 参数 + 副作用 + 失败策略」**——不是单纯定义,LLM 拿到完整契约
2. **只发最近 1 条**——`last_1_actions`(用户决策:先一条试,不够再加),用 Lil Weng 原则「curated memory,不是 raw history」
3. **每条带 ack 结果**——LLM 知道哪步成功了哪步失败,**反馈往前推一帧**

### 3.4 `[VERIFY]` —— 上一条动作的判定结果

```
[VERIFY]
last_action: tap "发送"
ack: ok=false
reason: 节点 "发送" 在当前帧不存在
screen_changed: false                ← 关键:屏幕没动
page: app.chat                       ← 当前仍在 chat 页
exit_hint: 单 back 返回 inbox_list
recommendation:
  - 不要重复 tap "发送"(节点已不存在)
  - 可选: longpress 上方消息气泡看是否有撤回菜单
  - 或: 重新输入内容(input 会整体替换)
```

**关键改动**:
1. **`ack: ok / ok=false / intercepted` 三态**——不是 string,是 stable token
2. **`screen_changed: true/false`**——LLM 知道动作到底有没有效,这是「LLM 失明」的关键修补
3. **`recommendation:` 是云端给的"软建议",不是硬规则**——LLM 可以采纳也可以不采纳(避免过度僵化)
4. **`exit_hint:` 只在屏未变化或页型异常时出现**——平时不发(信息冗余)

---

## 4. Scene-Brief 段(场景专有补充,按需插入)

不同的 `scene` 触发**不同的 scene-brief**,像插件一样按场景挂载。这是**最重要的设计**:

```
[SCENE-BRIEF: launcher.minus_one]
你看到的「XX 有 N 条通知」「XX 推荐」是 ColorOS 负一屏磁贴,
**不是应用图标**。禁止 tap 它们。
退出:swipe right → 回到 launcher.home。
```

```
[SCENE-BRIEF: app.chat]
当前在聊天会话页。**单 back 返回会话列表**,
不要按 home 退出 app。**严禁点击顶部标题栏**——那是群设置入口。
核查自己是不是在目标会话:expect title "Android AI 开发组"。
```

```
[SCENE-BRIEF: app.unknown]
app 内页型未识别。退路: 单 back;若 1 帧未变化则 home 兜底。
若你想点某个东西不确定: 用 expect "文本" 核查而不是盲点。
```

**关键**:
- 这些 brief **只在当前 scene 命中时插入**
- 每个 brief **最多 5 行**,专门讲这一场景最容易踩的坑
- 这是「专家经验注入」的位置,真机复盘时把新坑写进去就行
- 取代了原来散落在 system prompt 里的「【重要·负一屏识别】」「【重要·app 边界硬约束】」等大段文字

---

## 5. Task-Phase 字段(新增,自动判断)

把「任务推进到什么阶段」也变成结构化字段,LLM 不用自己推:

```
phase: search → enter_chat → input_text → send → done
current: search (step 1/5)
next_gate: 找到匹配 "Android AI 开发组" 的会话
```

**设计意图**:LLM 不该自己把任务拆成步骤,云端拆好发过来,LLM 只管「下一步」。

实现方式:`scenario` 包的 phase 状态机(`SendMessagePack` 已有的 scenario 层扩展),每个 phase 写明 `next_gate`(达成什么条件就推进)。

---

## 6. 退出路径体系(解决「进了二级页出不来」)

把现在散落的 `exit_hint` + system prompt 里「app 边界硬约束」+「退出路径迷失」全收拢成 **三段退出语义**:

```
[GROUND].exit_path  ← 当前场景的标准退出路径(一段自然语言,见 §3.2)
[SCENE-BRIEF]       ← 当前场景最容易踩的退出坑(见 §4)
[VERIFY].exit_hint  ← 失败时按需追加的退路建议(见 §3.4)
```

**关键**:三处信息**互补不重复**:
- `exit_path` —— 默认情况下 LLM 看到的退出路径
- `SCENE-BRIEF` —— 警告**反向操作**(「不要 back+home 振荡」「不要点标题栏」)
- `exit_hint` —— **失败后**追加(「刚才 tap 失败,屏没动,试试 back」)

LLM 拿到的是**一个完整的退出认知**:正常路径 + 反向警告 + 失败补救,而不是分散的字符串片段。

---

## 7. 完成契约(done 指令的语义)

把 `done` 的「四条件全满足」从 system prompt 抽出来,做成 LLM 可见的 [CONTRACT] 段:

```
[CONTRACT: done]
输出 done 必须四条件全部成立:
  1. pkg == target_pkg                          (在前台)
  2. 顶部标题 == 目标群名 (用 expect title 核查,不要肉眼判断)
  3. 最近一次动作是 tap 发送按钮 且 ack.ok=true
  4. 输入框已清空 (消息已发出,不是还在编辑)
任一不满足输出 expect 核查,不要输出 done。
```

LLM 现在**主动用 `expect` 核查**而不是「肉眼判断」——这是 roadmap §3.2 强调的「**禁止用 tap 表达核查**」的真正落地。

---

## 8. 反馈契约(替代 roadmap §3.4 的「结构化 feedback」)

把 `[feedback]` 自然语言块改为**段名约定**:

```
[VERIFY]
last_action: tap "发送"
ack: ok=false
reason: 节点 "发送" 在当前帧不存在
screen_changed: false
...
```

**不是 JSON**,但**字段名稳定**,LLM 可以精确读取。`recommendation:` 段不是硬规则,LLM 可选,但`screen_changed` 和 `ack` 是机器可读——Python 端能稳定生成。

---

## 9. 总览对比(现状 vs 新设计)

| 维度 | 现状 | 新设计 |
|---|---|---|
| 字段组织 | 平铺的 key: value + [screen] 块 | **四大段 + scene-brief 插件** |
| 场景上下文 | prompt 里 5+ 行文字规则 | **`scene: app (page: app.chat)` 一字段** + 场景专有 brief |
| 节点清单 | `[i] type "text"`,无位置,全发 | **`visible_nodes:` 加 `[顶部]/[列表项]/[底部]` 前缀**,只发可交互 |
| 退出路径 | `exit_hint` 单独字段 + prompt 6 行规则 | **三段互补语义**(exit_path / SCENE-BRIEF 反向警告 / VERIFY.exit_hint) |
| 反馈 | 自然语言 `[feedback]` 块 | **`[VERIFY]` 段,字段名稳定** + `recommendation` 软建议 |
| 历史 | 不发历史 | **`last_1_actions` 紧凑轨迹**(先 1 条,不够再加) |
| 任务阶段 | LLM 自己拆 | **`phase + current + next_gate` 云端拆好** |
| 完成契约 | prompt 4 行规则,LLM 概率遵守 | **`[CONTRACT: done]` 4 条 + expect 主动核查** |
| Token 体积 | system 4.8k + user 0.7k~2k | **system 大幅缩到 1k**(契约化),user 0.6k~1.5k(scene-brief 按需) |

---

## 10. 落地路径(分阶段,每阶段独立可验证)

### Phase 1:**重写 system prompt + payload 段落化**(P0,必须先做) ✅ 2026-07-26

- 拆 `_SYSTEM_PROMPT` 为: ✅
  - `[ROLE]` 短引言(<200 字符) ✅
  - `[TOOLS]` 操作契约(每 op 一段:**动词 + 参数 + 副作用 + 何时用 + 失败会怎样**) ✅
  - `[CONTRACT: done]` 完成契约 ✅
- 新增 `build_user_payload(d) -> str` 函数,把当前那段平铺 user_text 改成六段(§3.1–§3.6) ✅
- 不动 `parse_actions`(输出契约不动,改输入侧风险最小) ✅

实测:**system prompt 从 4770 字符缩到 ~1100 字符(commit 54ae067),user payload 段化但总字符控制在原量级**

### Phase 2:**新增 `SCENE-BRIEF` 插件系统**(P0,核心差异化) ✅ 2026-07-26

- 新增 `app/decision/scene_briefs.py`,存放每个 Scene/AppPage 的 brief 字典 ✅ (commit 01f0e0c)
- `build_user_payload` 在 OBSERVE 段后按当前 scene 注入对应 brief ✅ (commit ecabc7a)
- 编写第一版 brief 内容(飞书场景 + 通用场景各 3-5 行) ✅
- AppProfile.llm_brief 字段 + 飞书专属 brief ✅ (commit dccc700)

### Phase 3:**退出路径三段互补语义**(P0) ✅ 2026-07-26

- `exit_path` 字段由 `exit_hint.py` 升级生成 ✅ (单一 source 已就绪,Task 9 gate_for 完整化)
- `SCENE-BRIEF` 增加「反向警告」内容 ✅
- `VERIFY.exit_hint` 在 `screen_changed=false` 时追加 ✅ (commit 43a997a 部分)

### Phase 4:**task_phase 字段**(P1,与 ScenarioPack 联动) ✅ 2026-07-26

- `scenario/phase.py` 新增 TaskPhase 枚举 + PhaseState dataclass ✅ (commit c20bd34)
- `scenario/send_message.py` 增加 phase 状态机 + gate_for(phase, frame, ctx) ✅
- `build_user_payload` 把 `phase/current/next_gate` 注入 [PHASE] 段 ✅ (commit 395f55f)
- TaskContext.phase 字段 + handlers 写入 last_frame ✅

### Phase 5:**精简 screen → `visible_nodes` + 位置前缀**(P1,token 优化) ✅ 2026-07-26

- 把当前 `_encode_nodes` 拆: ✅ (commit f4bfaa1,4525bef)
  - `visible_nodes` (`encode_visible_nodes`): 只列 clickable/editable/有文本的标题节点 ✅
  - `layout` (`render_layout_summary`): 输出 `top=() mid=() bottom=()` 屏布局摘要 ✅
- 旧 `engine._nav_map` 函数删除,统一走 `payload.render_layout_summary` ✅ (commit dc5ae0f)

### Phase 6:**Feedback 契约化**(P1) ✅ 2026-07-26

- `_evaluate_expect` 输出的判定结果改为 `[VERIFY]` 段格式 ✅
- `feedback` 字段 `result` → `ack` 字段名对齐 verify 语义 ✅ (commit dc5783d)
- `screen_changed` 字段进 verify(初版 unknown,T11 真机升级) ✅

---

## 11. 关键决策点(用户拍板)

我把「核心设计选择」单列出来,需要你回答 5 个问题:

1. **段名约定 vs 完全自由格式** —— 段名 (`[OBSERVE]`/`[GROUND]`/`[ACT]`/`[VERIFY]`) 用方括号约定格式,LLM 看到就识别。还是用纯缩进/空行分?**(我推荐段名约定,Anthropic/Anthropic tool-use docs 都强调契约稳定性)**

2. **scene-brief 是 prompt 还是元数据?** —— 是塞进 user payload 作为自然语言段,还是在 `meta` 字段里给 LLM 自己读?**(我推荐前者,natural text 是 LLM 最稳的形式)**

3. **历史窗口** —— `last_1_actions` 先试一条(用户拍板),真机不够再加

4. **phase 字段放在 `[GROUND]` 还是独立 `[PHASE]`?** —— 影响信息密度,但不影响功能**(推荐独立,语义清晰)**

5. **Scene-Brief 优先级** —— 系统级 brief(所有 app 共用) vs app 级 brief(飞书专属)是否分层?**(推荐分层:通用 brief + 通过 AppProfile 注入了 app-specific 提示)**

---

## 12. 关键设计决策(2026-07-25 用户拍板)

| # | 决策 | 选择 | 备注 |
|---|---|---|---|
| 1 | 段名约定 vs 自由格式 | **段名约定**(方括号) | `[OBSERVE]/[GROUND]/[ACT]/[VERIFY]` 固定 |
| 2 | SCENE-BRIEF 放在哪里 | **user payload 自然语言段** | LLM 解析最稳 |
| 3 | 历史窗口大小 | **`last_1_actions` 先试一条** | 真机不够再加 |
| 4 | phase 字段位置 | **独立 `[PHASE]` 段** | 语义清晰 |
| 5 | SCENE-BRIEF 分层 | **通用 + AppProfile 注入 app 专属** | 飞书/微信 等各自注入自己 brief |

---

## 13. 验收方式

- [ ] system prompt 字符数 < 2000(从 4770)
- [ ] 真机 happy path(飞书发消息)LLM_DECIDE 行数不增(同等决策深度下)
- [ ] 真机二级页出不来场景下,LLM 主动用 `expect` 核查(grep `expect` in llm.log)
- [ ] 真机「back+home 振荡」场景被 LoopGuard 捕获前,LLM 已主动换路径(grep `back` 模式)
- [ ] 三个命令全绿(server 340 passed, pyright 0 errors, android tests)
