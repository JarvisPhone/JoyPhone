# AGENTS.md

## 合并硬门槛(三命令全绿)

```bash
cd server && uv run pytest tests/ -q      # 服务端测试(当前 252)
cd server && uv run pyright app/          # 类型检查(basic,零错误)
cd android && ./gradlew :app:testDebugUnitTest  # 端侧单测(当前 78)
```

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
└── infra/       # config.py(全部常量)/ metrics.py
```

## 关键约定

- Python 一律用 uv:`uv add <pkg>` 加依赖,`uv run <cmd>` 执行
- 设备能力架构(设计中,未实装):见 `docs/superpowers/specs/2026-07-22-device-capability-architecture-design.md`;
  三条已拍板约定——①能力矩阵经握手首帧 `device.hello` 上报 ②动作空间由能力矩阵生成,
  无 SDK 设备 prompt 零变化 ③op 路由全在端侧,云端只感知能力不感知 Provider
- 日志禁止 f-string,统一 `logger.info("msg %s", arg)`
- decide() 返回 `Decision(actions, source, meta)`,永不返回 None
- 记忆回放(cache/skill)由 `Config.REPLAY_ENABLED` 总开关控制,LLM 链路未稳定前=False,每帧 LLM 决策
- cache 沉淀=多次验证+泛化:同 key 泛化轨迹连续成功 `SKILL_LEARN_THRESHOLD` 次才转正;
  只留 in-app+ack ok 步骤,剔除导航段,tap 只留语义锚点(match_text),坐标-only 不沉淀
- LoopGuard:同一(帧签名,决策签名)第 `LOOP_GUARD_TRIGGER` 次判定停滞→机械 back
  (≤`LOOP_GUARD_MAX_BACKS` 次)→仍循环 abort(stuck_loop);帧或决策任一变化即重置
- cursor 仅在「动作来自 cache/skill 且端侧 ack ok」时推进;cache 同一步连续 ack 失败
  达 `CACHE_STEP_MAX_FAILS` 整条作废+本场禁用
- 新场景 = 新 ScenarioPack(代码);同场景新 app = 新 AppProfile(数据)
- 端侧 WS_URL 来自 BuildConfig(build.gradle.kts),禁止硬编码
- 协议双端契约测试样本:shared/protocol/v2/*.json
- WS 握手:连接 URL 须带 `?v=2`(PROTOCOL_VERSION),缺失或不符直接 close(code=4402)
