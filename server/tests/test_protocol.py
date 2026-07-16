import json
import typing

import pytest
from pydantic import ValidationError

from app.protocol import ActionResult, Action, Perception, TaskRequest, TaskStart, parse_uplink


def test_parse_perception_uplink():
    raw = '{"type":"perception","nodeTree":[{"id":"n1","text":"通讯录","clickable":true}],"pkg":"com.ss.android.lark","activity":"Main","ts":1}'
    msg = parse_uplink(raw)
    assert isinstance(msg, Perception)
    assert msg.pkg == "com.ss.android.lark"
    assert msg.nodeTree[0].text == "通讯录"


def test_node_accepts_view_id_resource_name():
    raw = '{"type":"perception","nodeTree":[{"id":"n1","viewIdResourceName":"com.ss.android.lark:id/contacts"}],"pkg":"com.ss.android.lark","activity":"Main","ts":1}'
    msg = parse_uplink(raw)
    assert isinstance(msg, Perception)
    assert msg.nodeTree[0].viewIdResourceName == "com.ss.android.lark:id/contacts"


def test_node_view_id_resource_name_defaults_none():
    raw = '{"type":"perception","nodeTree":[{"id":"n1"}],"pkg":"p","activity":"a","ts":0}'
    msg = parse_uplink(raw)
    assert msg.nodeTree[0].viewIdResourceName is None


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


def test_action_op_excludes_open_app():
    # 打开应用改为真人式翻屏找图标：不再有直启的 open_app；
    # 复合导航 op(home_first_page/next_page)已收窄为原子动作(home/swipe)。
    op_field = Action.model_fields["op"]
    valid_ops = set(typing.get_args(op_field.annotation))
    assert "open_app" not in valid_ops
    assert "home_first_page" not in valid_ops
    assert "next_page" not in valid_ops
    assert "home" in valid_ops
    assert "swipe" in valid_ops


def test_action_op_rejects_deprecated_ops():
    for dead in ("home_first_page", "next_page"):
        with pytest.raises(Exception):
            Action(actionId="x", op=dead)


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


def test_action_result_parses_at_end():
    result = ActionResult.model_validate(
        {"type": "action.result", "actionId": "a1", "ok": True, "atEnd": True}
    )
    assert result.atEnd is True


def test_action_result_at_end_defaults_false():
    result = ActionResult(actionId="a1", ok=True)
    assert result.atEnd is False


def test_task_start_build():
    task = TaskStart(taskId="t1", goal="确认还款时间", target="张三")
    assert task.type == "task.start"


def test_parse_task_request_uplink():
    raw = '{"type":"task.request","goal":"帮我完成一件事"}'
    msg = parse_uplink(raw)
    assert isinstance(msg, TaskRequest)
    assert msg.goal == "帮我完成一件事"


def test_task_request_rejects_missing_goal():
    with pytest.raises(ValidationError):
        parse_uplink('{"type":"task.request"}')


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


def test_parse_sample_capture_uplink():
    from app.protocol import SampleCapture
    raw = (
        '{"type":"sample.capture","label":"minus_one",'
        '"nodeTree":[{"id":"n1","text":"小布建议"}],'
        '"pkg":"com.android.launcher","activity":"Launcher","ts":123,"device":"OPPO"}'
    )
    msg = parse_uplink(raw)
    assert isinstance(msg, SampleCapture)
    assert msg.label == "minus_one"
    assert msg.pkg == "com.android.launcher"
    assert msg.nodeTree[0].text == "小布建议"
    assert msg.device == "OPPO"


def test_sample_capture_rejects_missing_label():
    with pytest.raises(ValidationError):
        parse_uplink('{"type":"sample.capture","pkg":"p","activity":"a","ts":0}')


def test_sample_capture_device_defaults_empty():
    raw = '{"type":"sample.capture","label":"home_first","nodeTree":[],"pkg":"p","activity":"a","ts":0}'
    msg = parse_uplink(raw)
    assert msg.device == ""