import json
import logging
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, WebSocket
from starlette.websockets import WebSocketDisconnect

from app.app_goal_resolver import extract_target, resolve_target_pkg
from app.chat_title_helpers import (
    detect_chat_title,
    is_message_input,
    is_send_button,
    match_chat_title,
)
from app.comm_log import log_up, log_down
from app.decision import DecisionEngine
from app.llm import FakeLLM, build_llm
from app.metrics import get_metrics_collector
from app.protocol import (
    Action,
    ConfirmResponse,
    SampleCapture,
    TaskAbort,
    TaskConfirm,
    TaskDone,
    TaskStart,
    parse_uplink,
)
from app.skill_cache import SkillCache
from app.skills import SkillLibrary

logger = logging.getLogger("phoneagent.gateway")
if not logger.handlers:
    _fmt = logging.Formatter("%(asctime)s [phoneagent] %(message)s")
    _h = logging.StreamHandler()
    _h.setFormatter(_fmt)
    logger.addHandler(_h)
    _log_dir = Path(__file__).resolve().parents[1] / "logs"
    _log_dir.mkdir(exist_ok=True)
    _fh = logging.FileHandler(_log_dir / "gateway.log", encoding="utf-8")
    _fh.setFormatter(_fmt)
    logger.addHandler(_fh)
    logger.setLevel(logging.INFO)
    logger.propagate = False

_FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "feishu_happy_path.json"


# ==== Gateway 配置常量 ====
class GatewayConfig:
    """Gateway 相关配置常量，统一管理魔法数字。"""
    DEFAULT_GOAL = "等待用户下发任务目标"
    CONFIRM_ID_PREFIX = "cfm"
    CONFIRM_ID_LENGTH = 8
    MAX_CONFIRM_COUNT = 1
    MAX_STEPS_DEFAULT = 40
    CONFIRM_TIMEOUT_MS = 5000
    PRE_SEND_REVERT_WINDOW_SEC = 10.0
    POST_SEND_PATROL_THRESHOLD = 2
    DEBOUNCE_MS = 400
    WRONG_CHAT_INPUT_THRESHOLD = 2


_DEFAULT_GOAL = GatewayConfig.DEFAULT_GOAL


_SAMPLES_DIR = Path(__file__).resolve().parents[1] / "data" / "samples"


def _persist_sample(sample: "SampleCapture", base_dir: Path | None = None) -> Path:
    """把一帧采样落盘为 <label>-<ts>.json,返回落盘路径。"""
    target_dir = base_dir if base_dir is not None else _SAMPLES_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{sample.label}-{sample.ts}.json"
    path.write_text(sample.model_dump_json(indent=2), encoding="utf-8")
    return path


def _load_fixture_steps() -> list[dict]:
    if not _FIXTURE.exists():
        return []
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _build_engine() -> DecisionEngine:
    fake = os.getenv("PHONEAGENT_FAKE_LLM")
    llm = FakeLLM(json.loads(fake)) if fake else build_llm()
    cache = SkillCache(Path(os.getenv("SKILL_CACHE_PATH", "data/skill_cache.json")))
    return DecisionEngine(llm=llm, skills=SkillLibrary(), cache=cache)


def create_app() -> FastAPI:
    app = FastAPI()
    max_steps = int(os.getenv("PHONEAGENT_MAX_STEPS", "40"))
    metrics = get_metrics_collector()

    @app.websocket("/ws/{device_id}")
    async def ws_gateway(websocket: WebSocket, device_id: str) -> None:
        await websocket.accept()
        logger.info("WS connected device=%s", device_id)
        from app.session import Session, State
        from app.negotiation import NegotiationBot

        engine = _build_engine()
        llm = build_llm()
        negotiation_bot = NegotiationBot(llm=llm)

        session = Session(
            task_id=f"task-{uuid.uuid4().hex[:8]}",
            goal=_DEFAULT_GOAL,
            target=device_id,
            max_steps=max_steps,
        )
        metrics.start_task(session.task_id, session.goal, device_id)

        cursor = 0
        history: list[dict] = []
        applied_steps: list[dict] = []
        last_pkg = ""
        negotiation_history: list[dict] = []
        skill_name: str | None = None

        # 【BUG FIX·Bug 1】"错群 input" 计数器。LLM 在错误会话标题下持续 input 正文,
        # 触发 [INPUT_GUARD] 多次仍不死心 → 给阈值强制 abort。
        wrong_chat_input_count: int = 0

        # Toast 确认相关状态
        target_chat_name: str | None = extract_target(session.goal)
        target_app_pkg: str | None = resolve_target_pkg(session.goal)
        pending_send_action: Action | None = None  # 被拦截的 input action
        pending_send_button_node: Node | None = None  # 当前屏的「发送」按钮节点
        pending_confirm_id: str | None = None
        pending_message_text: str = ""
        confirm_count = 0  # 全程只确认一次,避免循环

        # 【BUG FIX·Bug 2 硬性守卫】:CONFIRM 拦截成功、tap 真正下发到端侧后,
        # 端侧回 action.result.ok=true。此时应记录"消息已发出",并等待下一帧 perception
        # 验证输入框已清空——满足后强制下发 done(无视 LLM 是否输出),防止 LLM 在
        # 已发送的情况下继续 tap 群设置页/input 群名做无效探索。
        sent_at_step: int | None = None  # cursor 到达此值表示消息已发出
        sent_acked: bool = False         # 端侧已 ack 发送成功
        post_send_patrol_count: int = 0  # 发送后 LLM 仍继续操作的探测帧计数

        # [BUG FIX] 发送前 10s 观察窗:在 task.confirm 拦截期间(等待用户 approve),
        # 若用户触发「back / home」(表现为 uplink.pkg 从目标 app 切换到 launcher/systemui),
        # 视作用户撤回意图,主动 abort 待发的发送动作,不再下发 tap。
        # 设计要点:
        # - confirm_sent_ts 记录 task.confirm 下发的时刻(单调时钟,秒,来自 time.time())。
        # - last_pkg_before_confirm 记录拦截瞬时的 pkg,作为后续 pkg 切换的对照基线。
        # - 当 perception 上行时,若 state == AWAITING_CONFIRM 且距 confirm_sent_ts
        #   ≤ 10s 内 + pkg 切换到 launcher/systemui,立即下发 task.abort(reason=
        #   "pre_send_user_reverted"),并把 pending_send_action 清空、阻止
        #   后续 approve 路径下发真实 tap。
        confirm_sent_ts: float | None = None
        last_pkg_before_confirm: str = ""
        # 用户在观察窗内是否已经「反悔」。一旦置 True,即便后续 approve 上行
        # 我们也拒绝下发 tap,只发 abort 兜底。
        pre_send_reverted: bool = False

        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                logger.info("WS disconnected device=%s", device_id)
                break

            try:
                uplink = parse_uplink(raw)
                log_up(uplink.type, raw)
            except ValueError:
                _abort = TaskAbort(taskId=session.task_id, reason="invalid_uplink").to_json()
                log_down("task.abort", _abort)
                await websocket.send_text(_abort)
                metrics.finish_task(session.task_id, "aborted", "invalid_uplink")
                break

            if uplink.type == "action.result":
                history.append({"actionId": uplink.actionId, "ok": uplink.ok, "atEnd": uplink.atEnd})
                if uplink.ok:
                    cursor += 1
                    metrics.record_step(session.task_id)
                continue

            if uplink.type == "sample.capture":
                try:
                    saved = _persist_sample(uplink)
                    logger.info("sample.capture label=%s nodes=%d saved=%s",
                                uplink.label, len(uplink.nodeTree), saved.name)
                except OSError as exc:
                    logger.error("sample.capture persist failed label=%s err=%s",
                                 uplink.label, exc)
                continue

            if uplink.type == "heartbeat":
                _hb = Action(actionId=str(uuid.uuid4()), op="read_screen", params={}).to_json()
                log_down("action", _hb)
                await websocket.send_text(_hb)
                continue

            if uplink.type == "task.request":
                session.goal = uplink.goal
                session.state = State.NAVIGATING
                session.active = True
                # [P1-1 FIX] 重置所有 per-task 状态，避免同连接第二个任务继承污染
                cursor = 0
                history = []
                applied_steps = []
                last_pkg = ""
                negotiation_history = []
                skill_name = None
                wrong_chat_input_count = 0
                sent_at_step = None
                sent_acked = False
                post_send_patrol_count = 0
                target_chat_name = extract_target(session.goal)
                target_app_pkg = resolve_target_pkg(session.goal)
                pending_send_action = None
                pending_send_button_node = None
                pending_confirm_id = None
                pending_message_text = ""
                confirm_count = 0
                # [BUG FIX] 同步清零 10s 反向操作观察窗状态,避免上次任务残留污染。
                confirm_sent_ts = None
                last_pkg_before_confirm = ""
                pre_send_reverted = False
                logger.info("task.request goal=%s target_chat=%s pkg=%s", uplink.goal, target_chat_name, target_app_pkg)
                _ts_msg = TaskStart(taskId=session.task_id, goal=session.goal, target=device_id).to_json()
                log_down("task.start", _ts_msg)
                await websocket.send_text(_ts_msg)
                continue

            if uplink.type == "task.confirm_response":
                if session.state != State.AWAITING_CONFIRM:
                    logger.warning(
                        "confirm_response in wrong state=%s (ignoring)",
                        session.state.value,
                    )
                    continue
                if uplink.confirmId != pending_confirm_id:
                    logger.warning(
                        "confirm_response id mismatch: got=%s expected=%s",
                        uplink.confirmId, pending_confirm_id,
                    )
                    continue
                logger.info(
                    "task.confirm_response approved=%s reason=%s",
                    uplink.approved, uplink.reason,
                )
                pending_confirm_id = None
                if uplink.approved:
                    # 用户确认(Toast 5 秒到点 / App 主动)
                    # [BUG FIX] 若在 10s 观察窗内已检测到反向操作,即便 approve
                    # 已上行也拒绝下发 tap,改发 task.abort 兜底。
                    if pre_send_reverted:
                        logger.warning(
                            "[APPROVE_BUT_REVERTED] approved arrived but pre_send_reverted=True, refuse tap",
                        )
                        pending_confirm_id = None
                        pending_send_action = None
                        pending_send_button_node = None
                        session.transition(State.ABORT)
                        _ab = TaskAbort(
                            taskId=session.task_id,
                            reason="approve_but_pre_send_reverted",
                        ).to_json()
                        log_down("task.abort", _ab)
                        await websocket.send_text(_ab)
                        metrics.finish_task(
                            session.task_id, "aborted", "approve_but_pre_send_reverted"
                        )
                        break
                    session.transition(State.SENT)
                    if pending_send_action is not None:
                        # 文案在拦截前已通过 input 放行进框,这里只需下发被拦截的
                        # 「tap 发送按钮」动作把消息发出去。
                        send_act = Action(
                            actionId=str(uuid.uuid4()),
                            op="tap",
                            params={**pending_send_action.params},
                        )
                        _sa = send_act.to_json()
                        log_down("action", _sa)
                        await websocket.send_text(_sa)
                        applied_steps.append({"op": "tap", "params": send_act.params})
                        # 【BUG FIX·Bug 2】 真实发到端侧,标记"消息已下发"。
                        # 主循环下次的 perception 帧会据此守卫:若 LLM 输出非 done,
                        # 强制终止任务,防止 LLM 把"已发送"误判为"未完成"反复探索。
                        sent_acked = True
                        sent_at_step = cursor  # 当前 cursor 标识这一步
                        pending_send_action = None
                        pending_send_button_node = None
                    else:
                        logger.error("approved but no pending action → abort")
                        _ab = TaskAbort(taskId=session.task_id, reason="no_pending_after_approve").to_json()
                        log_down("task.abort", _ab)
                        await websocket.send_text(_ab)
                        metrics.finish_task(session.task_id, "aborted", "no_pending_after_approve")
                        break
                else:
                    # 取消:把 input 撤回不发,转入 IN_CHAT 让 LLM 重新决策(可改文案/重试)。
                    # SENT<-IN_CHAT 不在 _ALLOWED,改用更宽松的处理:不转换状态但清掉 pending,
                    # 让下一帧上行时由正常决策路径继续。
                    pending_send_action = None
                    pending_send_button_node = None
                    session.transition(State.IN_CHAT)
                    logger.info("[CONFIRM_REJECTED] reason=%s → back to IN_CHAT for re-decide", uplink.reason)
                    continue
                continue

            if uplink.type == "event.newMessage":
                sender = getattr(uplink, "sender", "unknown")
                text = getattr(uplink, "text", "")
                logger.info("event.newMessage from=%s text=%s", sender, text)

                negotiation_history.append({"role": "user", "content": text})

                try:
                    result = negotiation_bot.respond(
                        goal=session.goal,
                        incoming=text,
                        history=negotiation_history[:-1],
                    )
                    action = result.get("action", "continue")
                    reply = result.get("reply", "")

                    if action == "done":
                        session.transition(State.DONE)
                        _done = TaskDone(
                            taskId=session.task_id, result="ok", summary="negotiation completed"
                        ).to_json()
                        log_down("task.done", _done)
                        await websocket.send_text(_done)
                        metrics.finish_task(session.task_id, "completed")
                        break

                    if action == "escalate":
                        session.transition(State.ABORT)
                        _ab = TaskAbort(taskId=session.task_id, reason="escalated_to_human").to_json()
                        log_down("task.abort", _ab)
                        await websocket.send_text(_ab)
                        metrics.finish_task(session.task_id, "escalated")
                        break

                    if reply:
                        negotiation_history.append({"role": "agent", "content": reply})

                    session.transition(State.NEGOTIATING)

                except Exception as e:
                    logger.error("Negotiation error: %s", e)
                    session.transition(State.ABORT)
                    _ab = TaskAbort(taskId=session.task_id, reason="negotiation_error: %s" % e).to_json()
                    log_down("task.abort", _ab)
                    await websocket.send_text(_ab)
                    metrics.finish_task(session.task_id, "error", str(e))
                    break
                continue

            if uplink.type != "perception":
                continue

            # 【空闲闸门】未收到 task.request(或任务已结束)时,忽略一切 perception 帧,
            # 不决策、不下发任何 action。杜绝端侧持续推帧导致的空转轮询。
            if not session.active:
                continue

            if session.budget_exhausted():
                session.transition(State.ABORT)
                _be = TaskAbort(taskId=session.task_id, reason="budget_exhausted").to_json()
                log_down("task.abort", _be)
                await websocket.send_text(_be)
                metrics.finish_task(session.task_id, "aborted", "budget_exhausted")
                break

            last_pkg = uplink.pkg or last_pkg

            # 【BUG FIX·Bug 2 硬性兜底】消息已发出后,LLM 可能误判"还在处理",
            # 继续 tap 群设置页/input 群名做无效探索 → 进入「永不终止」死循环。
            # 这里用两道防线:
            # 1) 若上一帧 sent_acked=True + 当前仍在目标 app + 标题匹配目标群
            #    → 强制下发 done(task.completed),无视 LLM 输出。
            # 2) 若 LLM 在发送成功后又做出 ≥ 2 次非 done 操作
            #    → 直接 task.abort(防止继续耗 budget)。
            if sent_acked and target_app_pkg and uplink.pkg == target_app_pkg and target_chat_name:
                current_title = detect_chat_title(uplink.nodeTree)
                if current_title and match_chat_title(target_chat_name, current_title):
                    # 信号已强:消息已发、当前仍在目标会话内、标题匹配 → 强制 done。
                    logger.info(
                        "[POST_SEND_FORCE_DONE] sent_acked=True pkg=%s title=%s match",
                        uplink.pkg, current_title,
                    )
                    session.transition(State.DONE)
                    session.active = False
                    if applied_steps:
                        engine._cache.learn(session.goal, last_pkg, applied_steps)
                    _done = TaskDone(
                        taskId=session.task_id, result="ok",
                        summary="post-send auto-done (LLM did not output done)",
                    ).to_json()
                    log_down("task.done", _done)
                    await websocket.send_text(_done)
                    metrics.finish_task(session.task_id, "completed")
                    break

            # 防线 2:消息已发但 LLM 还在继续做事 → 累计巡逻计数,≥ 2 次强 abort。
            # 注意 must come BEFORE skills cache 命中检查,否则会被静默吃掉。
            if sent_acked:
                post_send_patrol_count += 1
                if post_send_patrol_count >= 2:
                    logger.warning(
                        "[POST_SEND_PATROL_ABORT] sent_acked=True but LLM continued %d frames",
                        post_send_patrol_count,
                    )
                    session.transition(State.ABORT)
                    _ab = TaskAbort(
                        taskId=session.task_id,
                        reason="post_send_patrol:llm_continued_after_send",
                    ).to_json()
                    log_down("task.abort", _ab)
                    await websocket.send_text(_ab)
                    metrics.finish_task(
                        session.task_id, "aborted", "post_send_patrol"
                    )
                    break
            logger.info(
                "perception pkg=%s nodes=%d cursor=%d state=%s",
                uplink.pkg, len(uplink.nodeTree), cursor, session.state.value,
            )

            # [BUG FIX] 【AWAITING_CONFIRM 期间·10s 反向操作观察窗】
            # 用户按 back/home 导致 uplink.pkg 从目标 app 切到 launcher/systemui 时,
            # 在 confirm_sent_ts 之后 10s 窗口内 → 视作主动撤回,
            # 清掉 pending_send_action 并把 pre_send_reverted 置 True,
            # 后续 approve 路径将拒绝真正下发 tap。窗口外仍走原"app_left_during_confirm"。
            if session.state == State.AWAITING_CONFIRM and confirm_sent_ts is not None and target_app_pkg:
                import time as _t
                within_window = (_t.monotonic() - confirm_sent_ts) <= 10.0
                pkg_left_app = (uplink.pkg or "") and uplink.pkg != target_app_pkg
                pkg_is_launder_view = any(
                    k in (uplink.pkg or "").lower()
                    for k in ("launcher", "systemui", "inputmethod")
                )
                if within_window and pkg_left_app and pkg_is_launder_view:
                    elapsed = _t.monotonic() - confirm_sent_ts
                    logger.warning(
                        "[PRE_SEND_USER_REVERTED] window=%.2fs pkg=%s -> target_pkg=%s, abort",
                        elapsed, uplink.pkg, target_app_pkg,
                    )
                    pre_send_reverted = True
                    pending_confirm_id = None
                    pending_send_action = None
                    pending_send_button_node = None
                    session.transition(State.ABORT)
                    _ab = TaskAbort(
                        taskId=session.task_id,
                        reason=(
                            f"pre_send_user_reverted:"
                            f"pkg_left_within_10s:elapsed={elapsed:.2f}s"
                        ),
                    ).to_json()
                    log_down("task.abort", _ab)
                    await websocket.send_text(_ab)
                    metrics.finish_task(
                        session.task_id, "aborted", "pre_send_user_reverted"
                    )
                    break
                # 窗口外但已切走,沿用旧逻辑(11+ 秒仍切走则按原路径处理)
                if not within_window and pkg_left_app:
                    logger.info(
                        "[CONFIRM_CANCELLED] pkg=%s != target=%s during AWAITING_CONFIRM -> auto reject",
                        uplink.pkg, target_app_pkg,
                    )
                    pending_confirm_id = None
                    session.transition(State.ABORT)
                    pending_send_action = None
                    pending_send_button_node = None
                    _ab = TaskAbort(taskId=session.task_id, reason="confirm_rejected:app_left_during_confirm").to_json()
                    log_down("task.abort", _ab)
                    await websocket.send_text(_ab)
                    metrics.finish_task(session.task_id, "aborted", "confirm_rejected:app_left_during_confirm")
                    break
                continue

            skill_name = engine._select_skill(session.goal, uplink.pkg) if skill_name is None else None

            target_pkg = resolve_target_pkg(session.goal) or ""
            actions = engine.decide(
                goal=session.goal,
                perception=uplink,
                skill_name=skill_name,
                cursor=cursor,
                history=history,
                target_pkg=target_pkg,
                guard=session.guard,
            )

            # [P0 FIX] 防御式处理 decide() 返回 None 的情况
            # 技能校验失败时可能返回 None，此时回退到 read_screen
            if actions is None:
                logger.warning("decide() returned None, falling back to read_screen")
                actions = [Action(actionId=str(uuid.uuid4()), op="read_screen", params={})]

            # 每做一次决策计为一步，而非仅在 action.result.ok 时计数。
            # 这样 wait/home/read_screen 等无副作用动作也消耗 budget，
            # 防止 LLM 持续返回 wait 导致任务永不终止。
            session.record_step()

            if skill_name:
                metrics.record_skill_hit(session.task_id)
            else:
                metrics.record_llm_call(session.task_id)

            terminate = False
            for action in actions:
                logger.info("decided op=%s params=%s", action.op, action.params)

                if action.op == "done":
                    session.transition(State.DONE)
                    session.active = False
                    if applied_steps:
                        engine._cache.learn(session.goal, last_pkg, applied_steps)
                    _done = TaskDone(
                        taskId=session.task_id, result="ok", summary="task completed"
                    ).to_json()
                    log_down("task.done", _done)
                    await websocket.send_text(_done)
                    metrics.finish_task(session.task_id, "completed")
                    terminate = True
                    break

                if action.op == "abort":
                    session.transition(State.ABORT)
                    session.active = False
                    _ab = TaskAbort(taskId=session.task_id, reason="llm_abort").to_json()
                    log_down("task.abort", _ab)
                    await websocket.send_text(_ab)
                    metrics.finish_task(session.task_id, "aborted", "llm_abort")
                    terminate = True
                    break

                # 【发送前确认】文案通过 input 正常放行进框;当 LLM 决策「tap 发送按钮」
                # 时才拦截:先不发给 App,改发 task.confirm 让用户确认。收到 approve 后
                # 再由 gateway 把这条 tap 发下去,把消息真正发出。
                if (
                    action.op == "tap"
                    and confirm_count == 0
                    and target_app_pkg
                    and uplink.pkg == target_app_pkg
                    and target_chat_name
                ):
                    current_title = detect_chat_title(uplink.nodeTree)
                    if (
                        current_title
                        and match_chat_title(target_chat_name, current_title)
                        and _tap_hits_send_button(action, uplink.nodeTree)
                    ):
                        confirm_id = f"cfm-{uuid.uuid4().hex[:8]}"
                        pending_confirm_id = confirm_id
                        pending_send_action = action
                        pending_send_button_node = None
                        pending_message_text = _extract_last_input_text(applied_steps)
                        _confirm = TaskConfirm(
                            taskId=session.task_id,
                            confirmId=confirm_id,
                            target=current_title,
                            message=pending_message_text,
                            timeoutMs=5000,
                        )
                        log_down("task.confirm", _confirm.to_json())
                        await websocket.send_text(_confirm.to_json())
                        session.transition(State.AWAITING_CONFIRM)
                        confirm_count += 1
                        # [BUG FIX] 启动 10s 反向操作观察窗:从此刻起 10 秒内
                        # 若发现 uplink.pkg 切换到 launcher/systemui(用户按 back 或 home)
                        # 则主动 abort,阻止后续真正下发 tap。
                        import time as _t
                        confirm_sent_ts = _t.monotonic()
                        last_pkg_before_confirm = uplink.pkg
                        pre_send_reverted = False
                        logger.info(
                            "[CONFIRM_SENT] target=%s current=%s msg=%r (send tap intercepted)",
                            target_chat_name, current_title, pending_message_text,
                        )
                        break

                # 【错群 input 正文守卫】LLM 决策「往聊天正文输入框输入正文」时,
                # 若当前会话页顶部标题与 target_chat 不匹配(进错群),拦截该 input
                # 不下发,改下发一个 back 回上一级列表,并记 [INPUT_GUARD] 日志。
                # 搜索框的 input(输群名搜索,is_message_input=False)不进此分支,正常放行。
                if (
                    action.op == "input"
                    and target_app_pkg
                    and uplink.pkg == target_app_pkg
                    and target_chat_name
                ):
                    input_node = _input_target_node(action, uplink.nodeTree)
                    if input_node is not None and is_message_input(input_node):
                        current_title = detect_chat_title(uplink.nodeTree)
                        if not (
                            current_title
                            and match_chat_title(target_chat_name, current_title)
                        ):
                            logger.warning(
                                "[INPUT_GUARD] target=%s current=%s text=%r "
                                "(message input in wrong chat intercepted, forcing back)",
                                target_chat_name, current_title,
                                action.params.get("text", ""),
                            )
                            wrong_chat_input_count += 1
                            # 阈值 2:同一目标下,LLM 两次都在错群输正文 → 强 abort,
                            # 防止 LLM 进入「tap 不匹配项 → back → 下一项 → input」
                            # 的循环死锁(Bug 1 主因)。
                            if wrong_chat_input_count >= 2:
                                logger.error(
                                    "[INPUT_GUARD_ABORT] wrong_chat_input_count=%d, force abort",
                                    wrong_chat_input_count,
                                )
                                session.transition(State.ABORT)
                                _ab = TaskAbort(
                                    taskId=session.task_id,
                                    reason=f"wrong_chat_repeated:{wrong_chat_input_count}",
                                ).to_json()
                                log_down("task.abort", _ab)
                                await websocket.send_text(_ab)
                                metrics.finish_task(
                                    session.task_id, "aborted",
                                    f"wrong_chat_repeated:{wrong_chat_input_count}",
                                )
                                terminate = True
                                break
                            _back = Action(
                                actionId=str(uuid.uuid4()), op="back", params={}
                            ).to_json()
                            log_down("action", _back)
                            await websocket.send_text(_back)
                            break

                if action.op in ("tap", "input"):
                    if session.state == State.NAVIGATING:
                        session.transition(State.IN_CHAT)

                applied_steps.append({"op": action.op, "params": action.params})
                _act = action.to_json()
                log_down("action", _act)
                await websocket.send_text(_act)

            if terminate:
                break

    return app


def _input_target_node(action: "Action", nodes):
    """把一条 input action 还原为当前屏被输入的目标 Node。

    与 _tap_hits_send_button 一致,用 params 里的 x/y 坐标(decision从目标
    node bounds 中心算出)命中节点:遍历当前屏,返回坐标落入 bounds 的第一个
    editable 节点。比 params["id"](实为 capped-nodes 列表下标,与完整
    nodeTree 索引不一定一致)更可靠。
    """
    try:
        x = int(action.params.get("x", ""))
        y = int(action.params.get("y", ""))
    except (ValueError, TypeError):
        return None
    for n in nodes:
        if not n.editable:
            continue
        if not n.bounds or len(n.bounds) != 4:
            continue
        left, top, right, bottom = n.bounds
        if left <= x <= right and top <= y <= bottom:
            return n
    return None


def _tap_hits_send_button(action: "Action", nodes) -> bool:
    """判断一条 tap action 是否命中当前屏的「发送」按钮。

    tap 的 params 里带 x/y(由 decision 从目标 node bounds 中心算出)。
    遍历当前屏所有发送按钮节点,若 tap 坐标落在其 bounds 内即视为命中。
    """
    from app.chat_title_helpers import is_send_button  # 局部 import

    try:
        x = int(action.params.get("x", ""))
        y = int(action.params.get("y", ""))
    except (ValueError, TypeError):
        return False
    for n in nodes:
        if not is_send_button(n):
            continue
        if not n.bounds or len(n.bounds) != 4:
            continue
        left, top, right, bottom = n.bounds
        if left <= x <= right and top <= y <= bottom:
            return True
    return False


def _extract_last_input_text(applied_steps: list[dict]) -> str:
    """从 applied_steps 里取出最近一条 input 操作的文本,作为 Toast 预览用。"""
    for step in reversed(applied_steps):
        if step.get("op") == "input":
            text = step.get("params", {}).get("text", "")
            if text:
                return text
    return ""
