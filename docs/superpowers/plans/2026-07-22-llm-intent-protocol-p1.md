# LLM 意图协议 P1:expect 断言 + 反馈通道实施计划

> **日期**: 2026-07-22
> **状态**: 设计已获用户批准(三层指令分类 / expect 语法 / feedback 一行粒度 / P2 复合指令后置)
> **来源**: 真机五轮事故——LLM 想「核查标题」但指令空间只有物理动作,只能用 tap 表达认知(误入群设置),或跳过核查幻觉 done
> **P2(不在本计划)**: wait_for / scroll_until 复合指令(缓解延迟,另立计划)

**Goal:** 指令空间按意图分三层(变更/观察/断言),新增断言类指令 `expect`(LLM 声明、云端机械判定、零副作用);LLM payload 新增一行 `feedback`(上一条指令的执行/拦截/判定结果),让 LLM 对后果不再失明。

**核心设计决策:**
- `expect` **只在云端求值,从不下发到设备**——协议 v2 与端侧零改动
- 判定用现成机制:`expect title` → detect_title + match_title;`expect pkg` → frame.pkg 比对;`expect "文本"` → 节点编码标签存在性(子串,LLM 便利性检查非守卫)
- feedback 存 TaskContext.llm_feedback,**一次性**:下次 decide 消费后即清空
- 沉默=成功:仅 ack 失败 / 策略拦截 / expect 判定 三类事件产生 feedback
- Policy 管道不动——expect 是 LLM 的合作通道,守卫仍是执法者(纵深防御)

**Tech Stack:** 仅 server/;pytest + pyright 门禁(改完 `uv run pytest tests/ -q` 全绿、`uv run pyright app/` 零错)。

---

### Task 1: expect 解析与求值(engine)

**Files:**
- Modify: `server/app/decision/engine.py`(parse_actions / _llm_decide / 新增 _evaluate_expect)
- Test: `server/tests/test_engine.py`

**语法**:
```
expect title "Android AI 开发组"   # 标题判定(detect_title + match_title)
expect pkg "com.ss.android.lark"   # 前台包名判定
expect "发送"                       # 文本存在性(任一节点编码标签包含即 PASS)
```

- [x] **Step 1: 失败测试**
  - `test_parse_expect_title/pkg/text`:三种语法解析为 `{"op":"expect","kind":"title|pkg|text","value":...}`(引号含空格正确解析,复用 tap 的引号处理)
  - `test_expect_title_pass_returns_feedback_pass`:FakeLLM 输出 `expect title "测试群"`,帧含 tv_title 节点 → Decision 只有 read_screen,`meta["feedback"]` 含 `PASS`
  - `test_expect_title_fail_reports_actual`:标题不符 → feedback 含 `FAIL` 与实际标题
  - `test_expect_text_substring` / `test_expect_pkg_mismatch`
  - `test_expect_ends_batch`:`expect` 同一批后续指令被截断(与 tap 同规则)

- [x] **Step 2: 实现**
  - `parse_actions` 新增 `expect` 动词:首参数为 kind(title/pkg),否则整体为 text;引号剥除
  - `_evaluate_expect(spec, d: DecideInput) -> str`:返回单行中文判定(`expect 判定 PASS:title=="X"` / `expect 判定 FAIL:title 实际是 "Y"` / `FAIL:当前 pkg=com.x`)
  - `_llm_decide` 循环遇 expect spec:立即 `return Decision(actions=[_read_screen_action()], source="llm", meta={"feedback": result})`

### Task 2: 拦截/失败反馈写入(策略管道 + handlers)

**Files:**
- Modify: `server/app/task/policies.py`(Verdict 增 `policy` 字段,run_pipeline 填充)
- Modify: `server/app/task/handlers.py`(拦截与 ack 失败时写 ctx.llm_feedback)
- Modify: `server/app/task/context.py`(TaskContext 增 `llm_feedback: str = ""`)
- Test: `server/tests/test_handlers.py` / `test_policies.py`

- [x] **Step 1: 失败测试**
  - `test_verdict_carries_policy_name`:run_pipeline 拦截时 verdict.policy == 策略名
  - `test_interception_writes_feedback`:SendGuard 拦截幻觉 done 后 `ctx.llm_feedback` 含「被策略 send_guard 拦截」
  - `test_ack_error_writes_feedback`:action.result ok=false error=anchor_not_found → `ctx.llm_feedback` 含 `anchor_not_found` 与 op
  - `test_ack_ok_no_feedback`:成功不产生反馈(沉默=成功)

- [x] **Step 2: 实现**
  - `Verdict` 增 `policy: str = ""`;`run_pipeline` 在 return 前 `v.policy = p.name`(continue 不必填)
  - `_on_perception` post 管道 intercept 且 `ctx.decided_actions` 非空:
    `ctx.llm_feedback = "上一条 {op} 被策略 {policy} 拦截"`(terminate 无需——任务已结束)
  - `_on_action_result`:`not ok and error` 时按 actionId 从 applied_steps 查 op,
    `ctx.llm_feedback = "上一条 {op} 执行失败:{error}"`

### Task 3: payload feedback 字段 + prompt 更新

**Files:**
- Modify: `server/app/decision/types.py`(DecideInput 增 `feedback: str = ""`)
- Modify: `server/app/decision/engine.py`(_llm_decide payload 增 "feedback" 键)+ `_SYSTEM_PROMPT`
- Modify: `server/app/task/handlers.py`(_on_perception 构建 DecideInput 时传入并清空 ctx.llm_feedback)
- Test: `server/tests/test_engine.py` / `test_handlers.py`

- [x] **Step 1: 失败测试**
  - `test_llm_payload_includes_feedback`:DecideInput(feedback="x") → 捕获 payload 含 `"feedback": "x"`
  - `test_feedback_consumed_once`:handlers 层 decide 后 ctx.llm_feedback 被清空,第二帧 payload 不再携带
  - `test_end_to_end_expect_feedback_loop`:handle_uplink 全链路——LLM 输出 expect title FAIL → 下一帧的 LLM-REQ payload feedback 含实际标题(用记录型 LLM 断言)

- [x] **Step 2: prompt 更新**
  - 指令表新增:`expect title "X" / expect pkg "com.x" / expect "文本"` —— 核查类指令,云端判定后通过 feedback 告知结果,**零副作用,需要核准时用它,禁止用 tap 表达核查**
  - 说明 feedback 字段:「你上一条指令的结果(失败原因/被拦截原因/expect 判定);没有此字段表示上一条成功」
  - 保留「严禁点击标题栏」与 TitleTapGuardPolicy(纵深防御)

### Task 4: 门禁 + 真机验证

- [x] `uv run pytest tests/ -q` 全绿;`uv run pyright app/` 零错误
- [ ] commit(单 commit,信息含「真机六轮」)
- [ ] 真机验证清单:
  - 进群后 LLM 用 `expect title` 核查(看 llm.log 是否出现)
  - 标题不符场景 feedback 是否引导 back
  - 幻觉 done 被拦截后,下一条 LLM 决策是否因 feedback 改为 tap 发送(而非慌乱点标题)
  - 全流程:进群 → input → tap "发送" → confirm → done

**备注(实现时易踩):**
- expect 的 read_screen 会触发新帧,新帧 decide 时 payload 才带上 feedback——时序靠 Task 3 的一次性消费保证
- `expect title` 在 detect_title 返回 None(无法识别标题)时判定为 `FAIL:当前页无法识别标题`,不算 PASS
- 端侧零改动:不要动 protocol/models.py 的 Op( expect 不下行)
