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


def test_perception_rejects_invalid_bounds_length():
    raw = '{"type":"perception","nodeTree":[{"id":"n1","bounds":[0,1,2]}]}'
    with pytest.raises(ValidationError):
        parse_uplink(raw)


def test_action_serializes_roundtrip_model_consistency():
    action = Action(actionId="a1", op="tap", params={"nodeId": "n1"})
    dumped = action.to_json()
    loaded = json.loads(dumped)
    rebuilt = Action.model_validate(loaded)

    assert rebuilt == action
    assert loaded["type"] == "action"
    assert loaded["actionId"] == "a1"
    assert loaded["op"] == "tap"
    assert loaded["params"] == {"nodeId": "n1"}


def test_action_rejects_unknown_op():
    with pytest.raises(ValidationError):
        Action(actionId="a1", op="unknown_op", params={})


def test_action_coerces_non_string_params_to_string():
    # 端侧 DownAction.params 是 Map<String,String>，云端须保证所有 value 为字符串，
    # 否则端侧 kotlinx.serialization 反序列化会抛异常。
    action = Action(actionId="a1", op="wait", params={"ms": 500, "flag": True, "ratio": 0.5})
    assert action.params == {"ms": "500", "flag": "True", "ratio": "0.5"}
    loaded = json.loads(action.to_json())
    assert all(isinstance(v, str) for v in loaded["params"].values())


def test_action_keeps_string_params_unchanged():
    action = Action(actionId="a1", op="tap", params={"nodeId": "n1", "match_text": "通讯录"})
    assert action.params == {"nodeId": "n1", "match_text": "通讯录"}


def test_task_start_build():
    task = TaskStart(taskId="t1", goal="确认还款时间", target="张三")
    assert task.type == "task.start"


def test_parse_uplink_malformed_json_raises_value_error():
    with pytest.raises(ValueError, match="malformed JSON"):
        parse_uplink('{"type":"perception"')


def test_parse_uplink_non_object_root_raises_value_error():
    with pytest.raises(ValueError, match="JSON root must be object"):
        parse_uplink('[{"type":"perception"}]')


def test_parse_uplink_missing_type_raises_value_error():
    with pytest.raises(ValueError, match="unknown uplink type: None"):
        parse_uplink('{"pkg":"com.ss.android.lark"}')


def test_parse_uplink_unknown_type_raises_value_error():
    with pytest.raises(ValueError, match="unknown uplink type: unknown"):
        parse_uplink('{"type":"unknown"}')


def test_parse_uplink_invalid_nested_node_raises_validation_error():
    raw = '{"type":"perception","nodeTree":["bad"]}'
    with pytest.raises(ValidationError):
        parse_uplink(raw)