"""send_message 五道策略的正例/反例测试。

测试数据参照旧 gateway.py 对应分支条件(0d1ccbd):
10s 观察窗 :437-484 / POST_SEND_FORCE_DONE :386-405 / POST_SEND_PATROL :409-426 /
confirm 拦截 :546-586 / INPUT_GUARD :592-638。
"""
import time

from app.infra.config import Config
from app.protocol import Action, Node, Perception
from app.scenario.profiles import FEISHU_PROFILE
from app.scenario.send_message import (
    ConfirmInterceptPolicy,
    PostSendForceDonePolicy,
    PostSendPatrolPolicy,
    PreSendRevertPolicy,
    WrongChatInputPolicy,
)
from app.task.context import TaskStore
from app.task.fsm import TaskState

LARK = FEISHU_PROFILE.pkg


def _ctx(**kw):
    ctx = TaskStore().new_task(goal="给测试群发飞书消息", scenario="send_message")
    ctx.target_pkg = LARK
    ctx.target_chat = "测试群"
    for k, v in kw.items():
        setattr(ctx, k, v)
    return ctx


def _frame(pkg=LARK, nodes=None):
    return Perception(pkg=pkg, nodeTree=nodes or [])


def _title_node(text="测试群"):
    return Node(id="t1", text=text, viewIdResourceName=f"{LARK}:id/tv_title")


def _send_button(bounds=(0, 0, 100, 100)):
    return Node(id="b1", viewIdResourceName=f"{LARK}:id/btn_send", bounds=bounds)


def _msg_input(bounds=(0, 200, 100, 300)):
    return Node(id="e1", desc="发消息", editable=True, bounds=bounds)


def _tap():
    """命中发送按钮的 tap:match_rid 锚点解析到 btn_send 节点。"""
    return Action(actionId="a1", op="tap", params={"match_rid": "btn_send"})


def _tap_miss():
    """锚点指向发送按钮之外的节点(标题),不触发确认拦截。"""
    return Action(actionId="a1", op="tap", params={"match_text": "测试群"})


# ---- PostSendPatrolPolicy(旧 :409-426)----


def test_post_send_patrol_aborts_after_threshold():
    ctx = _ctx()
    ctx.post_send.acked = True
    ctx.post_send.patrol_count = Config.POST_SEND_PATROL_THRESHOLD - 1
    v = PostSendPatrolPolicy().inspect(_frame(), ctx)
    assert v.kind == "terminate"
    assert "post_send_patrol" in v.reason
    assert v.status == "aborted"
    assert ctx.fsm.state == TaskState.ABORT


def test_post_send_patrol_below_threshold_continues():
    ctx = _ctx()
    ctx.post_send.acked = True
    ctx.post_send.patrol_count = 0
    v = PostSendPatrolPolicy().inspect(_frame(), ctx)
    assert v.kind == "continue"
    assert ctx.post_send.patrol_count == 1


def test_post_send_patrol_not_acked_continues():
    ctx = _ctx()
    v = PostSendPatrolPolicy().inspect(_frame(), ctx)
    assert v.kind == "continue"
    assert ctx.post_send.patrol_count == 0


# ---- PostSendForceDonePolicy(旧 :386-405)----


def test_post_send_force_done_when_acked_and_title_matches():
    ctx = _ctx()
    ctx.post_send.acked = True
    v = PostSendForceDonePolicy().inspect(_frame(nodes=[_title_node()]), ctx)
    assert v.kind == "terminate"
    assert v.reason == "post_send_auto_done"
    assert v.status == "completed"
    assert ctx.fsm.state == TaskState.DONE


def test_post_send_force_done_title_mismatch_continues():
    ctx = _ctx()
    ctx.post_send.acked = True
    v = PostSendForceDonePolicy().inspect(_frame(nodes=[_title_node("别的群")]), ctx)
    assert v.kind == "continue"


def test_post_send_force_done_not_acked_continues():
    ctx = _ctx()
    v = PostSendForceDonePolicy().inspect(_frame(nodes=[_title_node()]), ctx)
    assert v.kind == "continue"


def test_post_send_force_done_wrong_pkg_continues():
    ctx = _ctx()
    ctx.post_send.acked = True
    v = PostSendForceDonePolicy().inspect(_frame(pkg="com.x.launcher", nodes=[_title_node()]), ctx)
    assert v.kind == "continue"


# ---- PreSendRevertPolicy(旧 :437-484)----


def _awaiting_ctx(**kw):
    ctx = _ctx(**kw)
    ctx.fsm.transition(TaskState.AWAITING_CONFIRM, reason="test")
    ctx.confirm.sent_ts = time.monotonic()
    ctx.confirm.confirm_id = "cfm-00000000"
    ctx.confirm.pending_action = _tap()
    return ctx


def test_pre_send_revert_within_window_launcher():
    ctx = _awaiting_ctx()
    v = PreSendRevertPolicy().inspect(_frame(pkg="com.android.launcher3"), ctx)
    assert v.kind == "terminate"
    assert v.reason == "pre_send_user_reverted"
    assert v.status == "aborted"
    assert ctx.confirm.reverted is True
    assert ctx.confirm.confirm_id is None
    assert ctx.confirm.pending_action is None
    assert ctx.fsm.state == TaskState.ABORT


def test_pre_send_revert_still_in_target_pkg_continues():
    ctx = _awaiting_ctx()
    v = PreSendRevertPolicy().inspect(_frame(pkg=LARK), ctx)
    assert v.kind == "continue"
    assert ctx.confirm.reverted is False


def test_pre_send_revert_outside_window_left_app_aborts_confirm_rejected():
    ctx = _awaiting_ctx()
    ctx.confirm.sent_ts = time.monotonic() - (Config.PRE_SEND_REVERT_WINDOW_SEC + 1.0)
    v = PreSendRevertPolicy().inspect(_frame(pkg="com.x.otherapp"), ctx)
    assert v.kind == "terminate"
    assert v.reason == "confirm_rejected:app_left_during_confirm"
    assert v.status == "aborted"


def test_pre_send_revert_not_awaiting_confirm_continues():
    ctx = _ctx()
    v = PreSendRevertPolicy().inspect(_frame(pkg="com.android.launcher3"), ctx)
    assert v.kind == "continue"


# ---- ConfirmInterceptPolicy(旧 :546-586)----


def test_confirm_intercept_captures_send_tap():
    ctx = _ctx()
    ctx.applied_steps.append({"op": "input", "params": {"text": "晚上好"}})
    ctx.decided_actions = [_tap()]
    frame = _frame(nodes=[_title_node(), _send_button()])
    v = ConfirmInterceptPolicy().inspect(frame, ctx)
    assert v.kind == "intercept"
    assert v.actions == []
    assert ctx.confirm.pending_action is not None
    assert ctx.confirm.pending_action.op == "tap"
    assert ctx.confirm.confirm_id is not None
    assert ctx.confirm.confirm_id.startswith(Config.CONFIRM_ID_PREFIX + "-")
    assert len(ctx.confirm.confirm_id) == len(Config.CONFIRM_ID_PREFIX) + 1 + Config.CONFIRM_ID_LENGTH
    assert ctx.confirm.message_text == "晚上好"
    assert ctx.confirm.sent_ts is not None
    assert ctx.confirm.count == 1
    assert ctx.fsm.state == TaskState.AWAITING_CONFIRM


def test_confirm_intercept_tap_misses_send_button_continues():
    ctx = _ctx()
    ctx.decided_actions = [_tap_miss()]
    frame = _frame(nodes=[_title_node(), _send_button()])
    v = ConfirmInterceptPolicy().inspect(frame, ctx)
    assert v.kind == "continue"
    assert ctx.confirm.count == 0


def test_confirm_intercept_title_mismatch_continues():
    ctx = _ctx()
    ctx.decided_actions = [_tap()]
    frame = _frame(nodes=[_title_node("别的群"), _send_button()])
    v = ConfirmInterceptPolicy().inspect(frame, ctx)
    assert v.kind == "continue"


def test_confirm_intercept_max_confirm_count_continues():
    ctx = _ctx()
    ctx.confirm.count = Config.MAX_CONFIRM_COUNT
    ctx.decided_actions = [_tap()]
    frame = _frame(nodes=[_title_node(), _send_button()])
    v = ConfirmInterceptPolicy().inspect(frame, ctx)
    assert v.kind == "continue"


def test_confirm_intercept_non_tap_action_continues():
    ctx = _ctx()
    ctx.decided_actions = [Action(actionId="a2", op="back", params={})]
    frame = _frame(nodes=[_title_node(), _send_button()])
    v = ConfirmInterceptPolicy().inspect(frame, ctx)
    assert v.kind == "continue"


# ---- WrongChatInputPolicy(旧 :592-638)----


def _input(text="正文", anchor="发消息"):
    """input 经 match_text 锚点解析到目标 editable(desc 精确匹配)。"""
    return Action(actionId="a3", op="input", params={"match_text": anchor, "text": text})


def test_wrong_chat_input_intercepts_with_back():
    ctx = _ctx()
    ctx.decided_actions = [_input()]
    frame = _frame(nodes=[_title_node("别的群"), _msg_input()])
    v = WrongChatInputPolicy().inspect(frame, ctx)
    assert v.kind == "intercept"
    assert len(v.actions) == 1
    assert v.actions[0].op == "back"
    assert ctx.wrong_chat_input_count == 1


def test_wrong_chat_input_threshold_aborts():
    ctx = _ctx()
    ctx.wrong_chat_input_count = Config.WRONG_CHAT_INPUT_THRESHOLD - 1
    ctx.decided_actions = [_input()]
    frame = _frame(nodes=[_title_node("别的群"), _msg_input()])
    v = WrongChatInputPolicy().inspect(frame, ctx)
    assert v.kind == "terminate"
    assert "wrong_chat_repeated" in v.reason
    assert v.status == "aborted"
    assert ctx.fsm.state == TaskState.ABORT


def test_wrong_chat_input_title_matches_continues():
    ctx = _ctx()
    ctx.decided_actions = [_input()]
    frame = _frame(nodes=[_title_node(), _msg_input()])
    v = WrongChatInputPolicy().inspect(frame, ctx)
    assert v.kind == "continue"
    assert ctx.wrong_chat_input_count == 0


def test_wrong_chat_input_search_box_continues():
    """搜索框输群名(is_message_input=False)不进守卫分支,正常放行。"""
    ctx = _ctx()
    ctx.decided_actions = [_input(text="测试群", anchor="搜索")]
    search = Node(id="s1", desc="搜索", editable=True, bounds=(0, 200, 100, 300))
    frame = _frame(nodes=[_title_node("别的群"), search])
    v = WrongChatInputPolicy().inspect(frame, ctx)
    assert v.kind == "continue"


def test_wrong_chat_input_wrong_pkg_continues():
    ctx = _ctx()
    ctx.decided_actions = [_input()]
    frame = _frame(pkg="com.x.other", nodes=[_title_node("别的群"), _msg_input()])
    v = WrongChatInputPolicy().inspect(frame, ctx)
    assert v.kind == "continue"


# ---- SendGuardPolicy(done 门槛:未真实发送拦截幻觉 done)----


def _done_action():
    return Action(actionId="d1", op="done", params={})


def test_send_guard_blocks_premature_done():
    from app.scenario.send_message import SendGuardPolicy
    ctx = _ctx()
    ctx.decided_actions = [_done_action()]
    v = SendGuardPolicy().inspect(_frame(), ctx)
    assert v.kind == "intercept"
    assert v.actions[0].op == "read_screen"
    assert ctx.send_guard_count == 1


def test_send_guard_passes_after_real_send():
    from app.scenario.send_message import SendGuardPolicy
    ctx = _ctx()
    ctx.post_send.acked = True
    ctx.decided_actions = [_done_action()]
    v = SendGuardPolicy().inspect(_frame(), ctx)
    assert v.kind == "continue"


def test_send_guard_ignores_non_done_actions():
    from app.scenario.send_message import SendGuardPolicy
    ctx = _ctx()
    ctx.decided_actions = [_tap()]
    v = SendGuardPolicy().inspect(_frame(), ctx)
    assert v.kind == "continue"
    assert ctx.send_guard_count == 0


def test_send_guard_aborts_on_done_loop():
    from app.scenario.send_message import SendGuardPolicy
    ctx = _ctx()
    ctx.decided_actions = [_done_action()]
    ctx.send_guard_count = Config.SEND_GUARD_MAX - 1
    v = SendGuardPolicy().inspect(_frame(), ctx)
    assert v.kind == "terminate"
    assert "premature_done_loop" in v.reason
    assert ctx.fsm.state == TaskState.ABORT


# ---- classify_entry(入口落地页分类)----


def test_classify_entry_target_chat():
    from app.scenario.send_message import SendMessagePack
    ctx = _ctx()
    frame = _frame(nodes=[_title_node("测试群")])
    assert SendMessagePack().classify_entry(frame, ctx) == "target_chat"


def test_classify_entry_unknown_for_other_pages():
    from app.scenario.send_message import SendMessagePack
    ctx = _ctx()
    assert SendMessagePack().classify_entry(_frame(nodes=[_title_node("别的群")]), ctx) == "unknown"
    assert SendMessagePack().classify_entry(_frame(nodes=[]), ctx) == "unknown"


def test_confirm_intercept_skips_when_no_prior_input():
    # 无 input 正文时点发送:不进确认流(message 为空的确认无意义)
    ctx = _ctx()
    ctx.decided_actions = [_tap()]
    frame = _frame(nodes=[_title_node(), _send_button()])
    v = ConfirmInterceptPolicy().inspect(frame, ctx)
    assert v.kind == "continue"
    assert ctx.confirm.confirm_id is None


# ---- TitleTapGuardPolicy(标题栏点击守卫)----

from app.scenario.send_message import TitleTapGuardPolicy


def _title_zone_node(text="测试群"):
    return Node(id="tz", text=text, viewIdResourceName=f"{LARK}:id/title_zone",
                clickable=True)


def test_title_tap_guard_intercepts_title_tap():
    ctx = _ctx()
    ctx.decided_actions = [Action(actionId="a9", op="tap",
                                  params={"match_text": "测试群", "match_rid": "title_zone"})]
    frame = _frame(nodes=[_title_zone_node(), _send_button()])
    v = TitleTapGuardPolicy().inspect(frame, ctx)
    assert v.kind == "intercept"
    assert v.actions[0].op == "read_screen"


def test_title_tap_guard_passes_send_button_tap():
    ctx = _ctx()
    ctx.decided_actions = [_tap()]  # match_rid=btn_send,非标题栏
    frame = _frame(nodes=[_title_zone_node(), _send_button()])
    v = TitleTapGuardPolicy().inspect(frame, ctx)
    assert v.kind == "continue"


def test_title_tap_guard_passes_outside_target_pkg():
    ctx = _ctx()
    ctx.decided_actions = [Action(actionId="a9", op="tap",
                                  params={"match_rid": "title_zone"})]
    frame = _frame(pkg="com.other", nodes=[_title_zone_node()])
    v = TitleTapGuardPolicy().inspect(frame, ctx)
    assert v.kind == "continue"


def test_confirm_intercept_uses_draft_text_when_no_prior_input():
    # 输入框残留草稿(非本任务输入):确认消息取草稿文本,草稿也要过人审
    ctx = _ctx()
    ctx.decided_actions = [_tap()]
    draft_input = Node(id="e9", text="大家好", editable=True)
    frame = _frame(nodes=[_title_node(), draft_input, _send_button()])
    v = ConfirmInterceptPolicy().inspect(frame, ctx)
    assert v.kind == "intercept"
    assert ctx.confirm.message_text == "大家好"


# ---- SidebarDismissPolicy(侧边栏抽屉消除)----

from app.scenario.send_message import SidebarDismissPolicy


def _sidebar_node(rid, bounds=(0, 0, 888, 2374)):
    return Node(id="s-" + rid, viewIdResourceName=f"{LARK}:id/{rid}",
                text="x", clickable=True, bounds=bounds)


def _drawer_frame():
    nodes = [
        _sidebar_node("cl_join_team", (0, 676, 288, 1092)),
        _sidebar_node("layout_personal_status", (588, 174, 840, 267)),
        _sidebar_node("my_profile", (288, 1552, 888, 1720)),
    ]
    return _frame(nodes=nodes)


def test_sidebar_dismiss_intercepts_with_tap_at_blank():
    ctx = _ctx()
    v = SidebarDismissPolicy().inspect(_drawer_frame(), ctx)
    assert v.kind == "intercept"
    act = v.actions[0]
    assert act.op == "tap_at"
    # 点在特征节点右缘(888)之外的空白区
    assert int(act.params["x"]) > 888
    assert ctx.sidebar_dismiss_count == 1


def test_sidebar_dismiss_single_marker_passes():
    ctx = _ctx()
    frame = _frame(nodes=[_sidebar_node("cl_join_team")])
    v = SidebarDismissPolicy().inspect(frame, ctx)
    assert v.kind == "continue"


def test_sidebar_dismiss_cap_after_max_attempts():
    ctx = _ctx()
    p = SidebarDismissPolicy()
    p.inspect(_drawer_frame(), ctx)
    p.inspect(_drawer_frame(), ctx)
    assert p.inspect(_drawer_frame(), ctx).kind == "continue"  # 达上限交还 LLM


def test_sidebar_dismiss_counter_resets_when_gone():
    ctx = _ctx()
    p = SidebarDismissPolicy()
    p.inspect(_drawer_frame(), ctx)
    p.inspect(_frame(nodes=[_title_node()]), ctx)  # 抽屉消失
    assert ctx.sidebar_dismiss_count == 0


def test_sidebar_dismiss_wrong_pkg_passes():
    ctx = _ctx()
    frame = Perception(pkg="com.other", nodeTree=_drawer_frame().nodeTree)
    assert SidebarDismissPolicy().inspect(frame, ctx).kind == "continue"
