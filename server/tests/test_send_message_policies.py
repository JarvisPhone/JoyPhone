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


def _tap(x=50, y=50):
    return Action(actionId="a1", op="tap", params={"x": x, "y": y})


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
    ctx.decided_actions = [_tap(50, 50)]
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
    ctx.decided_actions = [_tap(500, 500)]
    frame = _frame(nodes=[_title_node(), _send_button()])
    v = ConfirmInterceptPolicy().inspect(frame, ctx)
    assert v.kind == "continue"
    assert ctx.confirm.count == 0


def test_confirm_intercept_title_mismatch_continues():
    ctx = _ctx()
    ctx.decided_actions = [_tap(50, 50)]
    frame = _frame(nodes=[_title_node("别的群"), _send_button()])
    v = ConfirmInterceptPolicy().inspect(frame, ctx)
    assert v.kind == "continue"


def test_confirm_intercept_max_confirm_count_continues():
    ctx = _ctx()
    ctx.confirm.count = Config.MAX_CONFIRM_COUNT
    ctx.decided_actions = [_tap(50, 50)]
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


def _input(x=50, y=250, text="正文"):
    return Action(actionId="a3", op="input", params={"x": x, "y": y, "text": text})


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
    ctx.decided_actions = [_input(text="测试群")]
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
