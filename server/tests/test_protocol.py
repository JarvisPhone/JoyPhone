import json

import pytest
from pydantic import ValidationError

from app.protocol import Action, Perception, TaskStart, parse_uplink


def test_parse_perception_uplink():
    raw = '{"type":"perception","nodeTree":[{"id":"n1","text":"通讯录","clickable":true}],"pkg":"com.ss.android.lark","activity":"Main","ts":1}'
    msg = parse_uplink(raw)
    assert isinstance(msg, Perception)
    assert msg.pkg == "com.ss.android.lark"
    assert msg.nodeTree[0].text == "通讯录"


def test_action_serializes_roundtrip():
    a = Action(actionId="a1", op="tap", params={"nodeId": "n1"})
    dumped = a.to_json()
    data = json.loads(dumped)
    assert data["type"] == "action"
    assert data["actionId"] == "a1"
    assert data["op"] == "tap"
    assert data["params"] == {"nodeId": "n1"}


def test_action_rejects_unknown_op():
    with pytest.raises(ValidationError):
        Action(actionId="a1", op="unknown_op", params={})


def test_task_start_build():
    t = TaskStart(taskId="t1", goal="确认还款时间", target="张三")
    assert t.type == "task.start"


def test_parse_uplink_missing_type_raises_value_error():
    with pytest.raises(ValueError, match="unknown uplink type: None"):
        parse_uplink('{"pkg":"com.ss.android.lark"}')


def test_parse_uplink_unknown_type_raises_value_error():
    with pytest.raises(ValueError, match="unknown uplink type: unknown"):
        parse_uplink('{"type":"unknown"}')


def test_parse_uplink_invalid_field_type_raises_validation_error():
    raw = '{"type":"perception","nodeTree":"bad"}'
    with pytest.raises(ValidationError):
        parse_uplink(raw)