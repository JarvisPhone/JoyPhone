# AGENTS.md

## 合并硬门槛(三命令全绿)

```bash
cd server && uv run pytest tests/ -q      # 服务端测试(当前 395)
cd server && uv run pyright app/          # 类型检查(basic,零错误)
cd android && ./gradlew :app:testDebugUnitTest  # 端侧单测

## 架构分层(L0 内核 + L1 场景包 + L2 AppProfile)

```
server/app/
├── protocol/    # 协议 v2 模型 + parse_uplink(PROTOCOL_VERSION=2)
├── gateway/     # 连接层:connection.py(收发)+ router.py(分发),无业务状态
├── task/        # 任务层:context.py(TaskContext 唯一 per-task 状态,task.request 整体新建)
│                #          fsm.py(通用五态机 IDLE/RUNNING/AWAITING_CONFIRM/WAITING_EVENT/DONE/ABORT)
│                #          policies.py(策略管道:Verdict/Policy/run_pipeline,
│                #                      内核 LoopGuardPolicy 帧×决策签名停滞守卫)
│                #          handlers.py(各 uplink 类型处理)
├── scenario/    # L1 场景包:base.py(ScenarioPack 协议)+ send_message.py
│   └── profiles/  # L2 AppProfile 纯数据(feishu/wechat/misc 共 18 个别名)
├── decision/    # 决策层:engine.py(cache→skill→pkg_guard→LLM,返回 Decision 永不 None)
│                #            skills.py(SkillTemplate+BoundSkill 参数绑定,SkillCursor 步进)
│                #            cache.py / pkg_guard.py / llm.py / types.py / ui_inspect.py
└── infra/       # config.py(全部常量)/ logging.py(双轨日志)/ metrics.py
```

## 关键约定

- Python 一律用 uv:`uv add <pkg>` 加依赖,`uv run <cmd>` 执行
- 设备能力架构(设计中,未实装):见 `docs/superpowers/specs/2026-07-22-device-capability-architecture-design.md`;
  三条已拍板约定——①能力矩阵经握手首帧 `device.hello` 上报 ②动作空间由能力矩阵生成,
  无 SDK 设备 prompt 零变化 ③op 路由全在端侧,云端只感知能力不感知 Provider
- LLM payload 段名约定(2026-07-25 落地,见 `docs/roadmap/2026-07-25-llm-payload-redesign.md`):
  发给 LLM 的 user payload 由六段稳定结构组成:`[OBSERVE] [SCENE-BRIEF*] [GROUND] [PHASE] [ACT] [VERIFY]`,
  其中 `SCENE-BRIEF` 按 `Scene × AppPage`(或 `AppProfile.llm_brief`)按需出现。
  字段名稳定:`pkg` / `scene` / `page` / `layout` / `goal` / `target` / `exit_path` / `phase` /
  `current` / `next_gate` / `last_1_action` / `ack` / `screen_changed`。
  system prompt 缩到 `[ROLE] + [TOOLS] + [CONTRACT: done]`,约 1100 字符;
  旧超长 prompt(4770+ char,文案堆叠)按段拆分进 payload 对应位置。
  段名 / 字段名是稳定契约,改动先改 plan + plan-level review。
- 日志禁止 f-string,统一 `logger.info("msg %s", arg)`
- 日志双轨(2026-07-25 新增):应用进程走 `app.infra.logging.setup_logging()` 同时挂两路 handler
    * stdout:单行概要(`LEVEL | logger.name | message`),长消息自动截断 200 char,跑 dev 时人眼可读
    * `logs/server.jsonl`:每行一个 JSON 对象,含 `ts/level/logger/msg/src:行号`,事后 `jq` 查 bug
  comm 通信原始日志仍走文件独立 logger:`logs/comm.log`(WS 上下行原文 / 每行 `ts|UP/DOWN|type|内容`,不是 JSONL)+ `logs/llm.log`(LLM 请求/响应原文)。
  新增人读摘要文件 `logs/comm.log.summary`,一行一条,格式 `ts UP/DOWN <msg_type> <关键字段>`,grep + tail 两不耽误。
- decide() 返回 `Decision(actions, source, meta)`,永不返回 None
- 记忆回放(cache/skill)由 `Config.REPLAY_ENABLED` 总开关控制,LLM 链路未稳定前=False,每帧 LLM 决策
- cache 沉淀=多次验证+泛化:同 key 泛化轨迹连续成功 `SKILL_LEARN_THRESHOLD` 次才转正;
  只留 in-app+ack ok 步骤,剔除导航段,tap 只留语义锚点(match_text),坐标-only 不沉淀
- LoopGuard:同一(帧签名,决策签名)第 `LOOP_GUARD_TRIGGER` 次判定停滞→机械 back
  (≤`LOOP_GUARD_MAX_BACKS` 次)→仍循环 abort(stuck_loop);帧或决策任一变化即重置
- cursor 仅在「动作来自 cache/skill 且端侧 ack ok」时推进;cache 同一步连续 ack 失败
  达 `CACHE_STEP_MAX_FAILS` 整条作废+本场禁用
- 任务状态跨连接存活:TaskStore 按 device_id 共享(WS 只是传输层,断线重连不丢任务现场)
- 新场景 = 新 ScenarioPack(代码);同场景新 app = 新 AppProfile(数据)
- **Commit message 必用英文**(2026-07-27 立):`git commit -m "..."` / `git commit -m "$(cat <<'EOF' ... EOF)"` 字符串内部全英文。
  - type 限定:`feat` / `fix` / `refactor` / `test` / `docs` / `chore` / `perf` / `ci` / `build`
  - subject:imperative mood,≤ 72 char,首字母小写(类型词除外)
  - body:解释「why」而非「what」,wrap 72 char,详细到未来 reviewer 一眼能懂
  - footer:关联 `Refs: ...` / `Fixes: ...` / `BREAKING:`(仅在不向后兼容时)
  - 例:`feat(cancel): implement task.cancel uplink + Android abort button end-to-end`
  - **生效边界**:本约定自 commit `4fc4007` 起执行;之前 commit 不追溯重写
    (改历史会破坏 hash 链 + 远端 force push,traceability 优先,旧 commit 保留为历史快照)
- 执行定位只用语义锚点(match_text/match_rid/occurrence),坐标仅 tap_at 逃生舱;
  锚点 fail-closed,端侧执行瞬间在实时树上重定位
- 端侧 WS_URL 来自 BuildConfig(build.gradle.kts),禁止硬编码
- 协议双端契约测试样本:shared/protocol/v2/*.json
- WS 握手:连接 URL 须带 `?v=2`(PROTOCOL_VERSION),缺失或不符直接 close(code=4402)
- task.cancel 协议(2026-07-26 加,见 server/app/protocol/models.py:TaskCancel):
  - client → server 上行,用户主动取消运行中任务
  - server 仅在 fsm.state ∈ {RUNNING, AWAITING_CONFIRM, WAITING_EVENT} 时终止并发下行;
  - **其他状态(IDLE/DONE/ABORT) / store 上无该 task / taskId 与 store 上不一致 → silent noop,不发下行**
    - taskId mismatch 见 `server/app/task/guard.py`(设备断连重连后旧 taskId 上行)
    - silent noop(2026-07-27 修):端侧 onAbortRunningTask() 乐观更新 UI 至 Idle 并置 userIntent=Cancelled;
      云端下行 task.abort 到达端侧时由 `Repo.consumeUserIntent(Cancelled)` 吸收,
      UI 保持 Idle,**不再被覆盖为 Failed:user_cancel**(cancel race 修)
  - reason 字段透传,默认 `"user_cancel"`(与 LoopGuard 的 `stuck_loop` / SendGuard 的 `false_done` 区分)
- 端侧 TaskUserIntent 模型(2026-07-28 加)代替前轮 ad-hoc `pendingCancelledTaskIds` marker:
  - `None` / `SentGoal` / `Cancelled` 三态;UI 合成 = 下行 TaskState + 上行 userIntent
  - Cancelled 由 `Repo.consumeUserIntent(Cancelled)` 一次性消费(下行 task.end 到时吸收)
  - 服务端 helper:`task.guard.current_task_or_none(uplink, store)` —
    所有 taskId-bearing uplink(TaskCancel / ConfirmResponse 等)入口统一 staleness 防御
- 端侧 viewModel 拆分:`onAbortRunningTask`(上行 cancel)+ `onResetToIdle`(纯 UI 重置);
  旧 `onCancelTask` 双职能命名混淆已拆
- Action op 清单(2026-07-26 增 3 项,共 15):
  - `tap` / `tap_at` / `longpress` / `input` / `swipe` / `scroll_to`(top|bottom)
  - `back` / `home` / `press_enter`
  - `open_notifications` / `open_quick_settings`
  - `wait` / `read_screen` / `expect`(云端求值,不下发) / `done` / `abort`
  - `scroll_to` 端侧实装反复 swipe 直到屏稳定(上限 5 次);
    `open_*` 顶部下拉手势(几何与 quick_settings 区分:0.40h vs 0.70h)
- Metrics 任务级指标(2026-07-26):
  - `TaskMetrics` 字段:`loop_guard_triggered_count` / `action_ok_count` / `action_total_count` +
    派生 `action_success_rate()`(无数据时 None)
  - HTTP 端点 `GET /metrics/recent?limit=10`:扫 metrics.log 末端 64KB 聚合,无 auth(本地调试)
  - `loop_guard` 拦截处自动 `record_loop_guard_trigger`;`action_result` 来时自动 `record_action_result`
- cache 沉淀(2026-07-26 验证):`Config.REPLAY_ENABLED=False`(回放总开关)与 `cache.record_success`(沉淀)是两个独立机制,
  即使回放关闭,**沉淀照常跑**(测试 `tests/test_learn_cache.py::test_cache_record_success_independent_of_replay_enabled` 守护)
- 真机联调分工:**AI 不碰真机操作**;AI 负责 `adb install -r` + `adb shell monkey` 启动 app,用户手动授予无障碍权限 + 点击触发场景,用户口述现象,AI 看 `server/logs/*` 分析(`tail -F` 四件套 `uvicorn.log` / `comm.log` / `comm.log.summary` / `llm.log`,或 `jq` `server.jsonl`)

## 闭环优先级(2026-07-23 真机复盘后立)

1. **基础闭环先行**:LLM 链路在成功率未稳定前,**禁止**讨论 cache 沉淀 / skill 复用。cache 是优化,不是根基,基础不过 cache 上层没意义。
2. **LLM 必收结构化上下文**(规划中):Screen 序列化(`engine._encode_nodes`)+ pkg_guard `Scene` 状态机(`detect_scene`)结果一并塞进 prompt,
   让 LLM 看到 `[i] type "label"(clickable=true|false|editable=true|false)(scene=HOME|MINUS_ONE|...)` 等结构化字段;不要把 workspace bounds 写成文字描述让 LLM 自己推理。
3. **LoopGuard 兜底要扩**(规划中):在 `policies.py` 增加 `swipe left/right` 出口(若 frame 持续不变 + current scene 在 launcher / 负一屏,允许触发一次方向性 swipe),而不是死磕 `back/home`。
4. **clickable=false 显式标记**(规划中):`_encode_nodes` 输出 `type` 时,把不可点击纯文本与 `clickable=false` 装饰元素区分(例如新引入 `disabled` 标签);LLM 不该被"飞书 有2条通知"这种 clickable=false 通知磁贴误导为可点。

## MCP / A11Y 边界(2026-07-29 立,ADR 0001 落地)

LLM 看到的工具集分两段,两段走不同通道,边界刚性:

- **A11Y ops(硬编码进 [TOOLS] 段,system prompt)**:`tap` / `longpress` / `input` /
  `swipe` / `scroll_to` / `back` / `home` / `press_enter` / `open_notifications` /
  `open_quick_settings` / `expect` / `read` / `wait` / `done` / `abort`。这些 op
  LLM **直接产 Action 下行**(`Decision.actions=[Action(op="tap",...)]`),
  端侧由 AccessibilityService 兜底执行;**不走 MCP、不进 BM25 索引**。
- **SDK Provider tools(BM25 召回 + call_tool)**:`force_stop` / `install_silent` /
  `kill_background` / `reboot_device` / `lock_a11y` / `unlock_a11y` /
  `query_running_packages` / 厂商独有 capability(vivo / huawei / future ...)。
  LLM 通过 `search_tools(query)` BM25 召回 → `call_tool(name, args)` → McpRouter
  派发到具体 Provider → 走设备 daemon HTTP-RPC。

硬规则:

- `A11yProvider` **不存在**;Phase 1 注册表里有过,已删除。不要新加
  「A11Y Provider」「Universal Provider」之类抽象挡板;a11y 路径就是
  `Action 下行 + 端侧 AccessibilityService` 同一条链路。
- `server/app/mcp/providers/` 子目录只放厂商 SDK 适配,新 Provider 一律命名
  `mcp/providers/<vendor>/<vendor>.py` 并 `register` 到全局 registry。
- BM25 索引的 corpus = `registry.all_tools()` = SDK Provider tools 之并,
  **永远不包含 a11y ops**;LLM 在 [TOOLS] 段看到 a11y ops 与 BM25 召回
  SDK tools 互不重叠,语义清晰(避免「tap 既是 a11y 又被 SDK 召回」的歧义)。
- device.hello 上报的 `sdkVersion` 决定 capability 维度:**能力下放到设备**,
  op 路由全在端侧(2026-07-22 三约定);云端不感知 provider name,只
  BM25 召回 SDK tool,设备 daemon 按 SDK 实际能力执行或返回「不支持」。
- 决策出口分两大类型:`Decision(actions=[...], source="llm"|"cache"|"skill"|"pkg_guard"|"home_locate")` 走 Action 下行;
  SDK tool 调用由云端额外经 `McpRouter.route(...)` 异步执行,结果经 WS
  下行 feedback 回 LLM。**Action 和 MCP call 不混在同一帧决策里**;LLM 二选一输出。
