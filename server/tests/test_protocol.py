from app.protocol import parse_uplink, Perception, ActionResult, NewMessage, Action, TaskStart


def test_parse_perception_uplink():
    raw = '{"type":"perception","nodeTree":[{"id":"n1","text":"通讯录","clickable":true}],"pkg":"com.ss.android.lark","activity":"Main","ts":1}'
    msg = parse_uplink(raw)
    assert isinstance(msg, Perception)
    assert msg.pkg == "com.ss.android.lark"
    assert msg.nodeTree[0].text == "通讯录"


def test_action_serializes_roundtrip():
    a = Action(actionId="a1", op="tap", params={"nodeId": "n1"})
    dumped = a.to_json()
    assert '"op":"tap"' in dumped
    assert '"actionId":"a1"' in dumped
    assert '"type":"action"' in dumped


def test_task_start_build():
    t = TaskStart(taskId="t1", goal="确认还款时间", target="张三")
    assert t.type == "task.start"