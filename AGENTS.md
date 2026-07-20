# AGENTS.md

## 合并硬门槛(三命令全绿)

```bash
cd server && uv run pytest tests/ -q      # 服务端测试(当前 204)
cd server && uv run pyright app/          # 类型检查(basic,零错误)
cd android && ./gradlew :app:testDebugUnitTest  # 端侧单测(当前 74)
```

## 架构分层(L0 内核 + L1 场景包 + L2 AppProfile)

```
server/app/
├── protocol/    # 协议 v2 模型 + parse_uplink(PROTOCOL_VERSION=2)
├── gateway/     # 连接层:connection.py(收发)+ router.py(分发),无业务状态
├── task/        # 任务层:context.py(TaskContext 唯一 per-task 状态,task.request 整体新建)
│                #          fsm.py(通用五态机 IDLE/RUNNING/AWAITING_CONFIRM/WAITING_EVENT/DONE/ABORT)
│                #          policies.py(策略管道:Verdict/Policy/run_pipeline)
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
- 日志禁止 f-string,统一 `logger.info("msg %s", arg)`
- decide() 返回 `Decision(actions, source, meta)`,永不返回 None
- cursor 仅在「动作来自 cache/skill 且端侧 ack ok」时推进
- 新场景 = 新 ScenarioPack(代码);同场景新 app = 新 AppProfile(数据)
- 端侧 WS_URL 来自 BuildConfig(build.gradle.kts),禁止硬编码
- 协议双端契约测试样本:shared/protocol/v2/*.json
