from app.task.context import TaskStore
from app.task.fsm import TaskState


def test_new_task_replaces_context_entirely():
    store = TaskStore()
    ctx1 = store.new_task(goal="给张三发消息", scenario=None)
    ctx1.steps = 39
    ctx1.guard["stall_count"] = 5
    ctx1.post_send.acked = True
    ctx2 = store.new_task(goal="给李四发消息", scenario=None)
    assert ctx2.steps == 0 and ctx2.guard["stall_count"] == 0
    assert ctx2.post_send.acked is False and ctx2 is not ctx1
    assert ctx2.fsm.state.name == "RUNNING"


def test_clear_removes_context():
    store = TaskStore()
    store.new_task(goal="g", scenario=None)
    store.clear()
    assert store.current is None


def test_new_task_defaults():
    store = TaskStore()
    ctx = store.new_task(goal="g", scenario=None)
    assert store.current is ctx
    assert ctx.task_id.startswith("task-")
    assert len(ctx.task_id) == len("task-") + 8
    assert ctx.goal == "g"
    assert ctx.scenario is None
    assert ctx.steps == 0
    assert ctx.max_steps == 40
    assert ctx.cursor.index == 0 and ctx.cursor.state == "pending"
    assert ctx.history == [] and ctx.applied_steps == []
    assert ctx.target_pkg == "" and ctx.target_chat is None
    assert ctx.bindings == {} and ctx.bound_skill is None
    assert ctx.confirm.pending_action is None
    assert ctx.confirm.confirm_id is None
    assert ctx.confirm.sent_ts is None
    assert ctx.confirm.reverted is False
    assert ctx.confirm.count == 0
    assert ctx.confirm.message_text == ""
    assert ctx.post_send.acked is False and ctx.post_send.patrol_count == 0
    assert ctx.guard == {
        "scene_history": [],
        "stall_count": 0,
        "last_op": "",
        "escalation_level": 0,
    }
    assert ctx.negotiation == []
    assert ctx.last_consumed_seq == 0


def test_new_task_records_force_transition():
    store = TaskStore()
    ctx = store.new_task(goal="g", scenario=None)
    assert ctx.fsm.state == TaskState.RUNNING
    assert len(ctx.fsm.history) == 1
    rec = ctx.fsm.history[0]
    assert rec.frm == TaskState.IDLE and rec.to == TaskState.RUNNING
    assert rec.reason == "task.request"


def test_new_task_custom_max_steps_and_scenario():
    store = TaskStore()
    ctx = store.new_task(goal="g", scenario="s1", max_steps=7)
    assert ctx.max_steps == 7
    assert ctx.scenario == "s1"


def test_task_ids_unique():
    store = TaskStore()
    a = store.new_task(goal="a", scenario=None)
    b = store.new_task(goal="b", scenario=None)
    assert a.task_id != b.task_id
