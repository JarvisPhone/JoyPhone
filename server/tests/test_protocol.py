import json
import pytest
from app.protocol import (
    PROTOCOL_VERSION, Action, ActionResult, HeartbeatAck, Node, Perception, parse_uplink,
)

def test_version_is_2():
    assert PROTOCOL_VERSION == 2

def test_action_result_has_no_at_end():
    ar = ActionResult(actionId="a1", ok=True)
    assert not hasattr(ar, "atEnd")
    assert "atEnd" not in ar.model_dump()

def test_action_op_rejects_request_confirm():
    with pytest.raises(Exception):
        Action(actionId="a1", op="request_confirm", params={})

def test_perception_roundtrip_with_seq():
    raw = json.dumps({"type": "perception", "nodeTree": [], "pkg": "p", "seq": 7})
    up = parse_uplink(raw)
    assert isinstance(up, Perception) and up.seq == 7

def test_heartbeat_ack_serializes():
    ack = HeartbeatAck(deviceId="d1")
    assert json.loads(ack.to_json())["type"] == "heartbeat.ack"


def test_action_params_coerced_to_str():
    a = Action(actionId="a1", op="input", params={"text": 123, "flag": True, "none": None})
    assert a.params == {"text": "123", "flag": "True", "none": "None"}
    assert all(isinstance(v, str) for v in a.params.values())


def test_parse_uplink_malformed_json():
    with pytest.raises(ValueError, match="malformed JSON"):
        parse_uplink("{not json")


def test_parse_uplink_root_not_object():
    with pytest.raises(ValueError, match="root must be object"):
        parse_uplink("[1, 2, 3]")


def test_parse_uplink_unknown_type():
    with pytest.raises(ValueError, match="unknown uplink type"):
        parse_uplink(json.dumps({"type": "no.such.type"}))


def test_node_deserializes_bounds_tuple():
    node = Node(**{"id": "n1", "bounds": [1, 2, 3, 4], "clickable": True})
    assert node.id == "n1"
    assert node.bounds == (1, 2, 3, 4)
    assert node.clickable is True
