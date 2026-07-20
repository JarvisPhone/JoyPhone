import json
import pytest
from app.protocol import (
    PROTOCOL_VERSION, Action, ActionResult, HeartbeatAck, Perception, parse_uplink,
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
