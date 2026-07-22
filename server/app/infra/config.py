class Config:
    MAX_STEPS_DEFAULT = 40
    CONFIRM_ID_PREFIX = "cfm"
    CONFIRM_ID_LENGTH = 8
    MAX_CONFIRM_COUNT = 1
    CONFIRM_TIMEOUT_MS = 5000
    PRE_SEND_REVERT_WINDOW_SEC = 10.0
    POST_SEND_PATROL_THRESHOLD = 2
    WRONG_CHAT_INPUT_THRESHOLD = 2
    AWAITING_CONFIRM_TIMEOUT_SEC = 30
    # ---- 技能沉淀/回放门槛 ----
    # 同一泛化轨迹连续成功次数,达到才从候选转正为可回放 entry
    SKILL_LEARN_THRESHOLD = 3
    # cache 回放同一步连续 ack 失败上限,达到整条作废并本场禁用
    CACHE_STEP_MAX_FAILS = 2
    # skill 连续无节点匹配的帧数上限,达到本场禁用(防 SKILL_NO_MATCH 刷屏)
    SKILL_MAX_MISSES = 3
    # LLM 幻觉 done(未真实发送)连续拦截上限,达到强 abort
    SEND_GUARD_MAX = 3
    # ---- 停滞/循环守卫(内核,帧签名×决策签名重复检测)----
    # 同一(帧,决策)出现次数达到此值判定停滞(容忍 1 次点空重试,第 3 次必是循环)
    LOOP_GUARD_TRIGGER = 3
    # 机械 back 脱困上限,仍循环直接 abort(stuck_loop) 留现场查原因
    LOOP_GUARD_MAX_BACKS = 2
    # ---- 记忆回放总开关 ----
    # LLM 链路未稳定前关闭 cache/skill 回放,每帧由 LLM 决策(代码保留,稳定后再开)
    REPLAY_ENABLED = False
