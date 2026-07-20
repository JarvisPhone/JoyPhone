import json
from pathlib import Path

import pytest

from app.protocol import (
    Action,
    ActionResult,
    ConfirmResponse,
    Heartbeat,
    HeartbeatAck,
    NewMessage,
    Perception,
    SampleCapture,
    TaskAbort,
    TaskConfirm,
    TaskDone,
    TaskRequest,
    TaskStart,
    parse_uplink,
)

GOLDEN_DIR = Path(__file__).resolve().parents[2] / "shared" / "protocol" / "v2"


def _load(name: str) -> dict:
    return json.loads((GOLDEN_DIR / name).read_text(encoding="utf-8"))


def test_golden_dir_has_all_samples():
    expected = {
        "perception.json",
        "action_result.json",
        "new_message.json",
        "heartbeat.json",
        "task_request.json",
        "confirm_response.json",
        "sample_capture.json",
        "task_start.json",
        "action.json",
        "task_done.json",
        "task_abort.json",
        "task_confirm.json",
        "heartbeat_ack.json",
    }
    actual = {p.name for p in GOLDEN_DIR.glob("*.json")}
    assert expected == actual


# ---- 上行:parse_uplink 解析 + 关键字段断言 ----


def test_uplink_perception():
    raw = _load("perception.json")
    msg = parse_uplink(json.dumps(raw))
    assert isinstance(msg, Perception)
    assert msg.seq == 42
    assert msg.seq > 0
    assert msg.pkg == "com.ss.android.lark"
    assert msg.activity == ".MainActivity"
    assert len(msg.nodeTree) == 2
    editable = msg.nodeTree[0]
    assert editable.editable is True
    assert editable.bounds == (10, 20, 300, 80)
    assert msg.nodeTree[1].editable is False


def test_uplink_action_result_has_seq_and_no_at_end():
    raw = _load("action_result.json")
    assert "atEnd" not in raw
    msg = parse_uplink(json.dumps(raw))
    assert isinstance(msg, ActionResult)
    assert msg.actionId == "act-0007"
    assert msg.ok is False
    assert msg.error == "node_not_found"
    assert msg.seq == 43
    assert "atEnd" not in msg.model_dump()


def test_uplink_new_message():
    raw = _load("new_message.json")
    msg = parse_uplink(json.dumps(raw))
    assert isinstance(msg, NewMessage)
    assert msg.app == "com.ss.android.lark"
    assert msg.sender == "张三"
    assert msg.text == "周报记得发我"


def test_uplink_heartbeat():
    raw = _load("heartbeat.json")
    msg = parse_uplink(json.dumps(raw))
    assert isinstance(msg, Heartbeat)
    assert msg.deviceId == "pixel-7-pro-01"


def test_uplink_task_request():
    raw = _load("task_request.json")
    msg = parse_uplink(json.dumps(raw))
    assert isinstance(msg, TaskRequest)
    assert msg.goal == "给张三发一条飞书消息:周报已提交"


def test_uplink_confirm_response():
    raw = _load("confirm_response.json")
    msg = parse_uplink(json.dumps(raw))
    assert isinstance(msg, ConfirmResponse)
    assert msg.taskId == "task-20260720-001"
    assert msg.confirmId == "cfm-0001"
    assert msg.approved is True


def test_uplink_sample_capture():
    raw = _load("sample_capture.json")
    msg = parse_uplink(json.dumps(raw))
    assert isinstance(msg, SampleCapture)
    assert msg.label == "lark_chat_page"
    assert len(msg.nodeTree) == 2
    assert msg.nodeTree[0].editable is True
    assert msg.device == "pixel-7-pro-01"


# ---- 下行:model_validate 后 model_dump 与 golden 逐字段一致 ----


@pytest.mark.parametrize(
    "golden_name,model",
    [
        ("task_start.json", TaskStart),
        ("action.json", Action),
        ("task_done.json", TaskDone),
        ("task_abort.json", TaskAbort),
        ("task_confirm.json", TaskConfirm),
        ("heartbeat_ack.json", HeartbeatAck),
    ],
)
def test_downlink_roundtrip_matches_golden(golden_name, model):
    raw = _load(golden_name)
    msg = model.model_validate(raw)
    assert msg.model_dump() == raw


def test_downlink_action_params_all_strings():
    raw = _load("action.json")
    assert raw["params"]
    assert all(isinstance(v, str) for v in raw["params"].values())
    msg = Action.model_validate(raw)
    assert all(isinstance(v, str) for v in msg.params.values())
    assert msg.op == "input"


def test_downlink_task_confirm_timeout():
    raw = _load("task_confirm.json")
    msg = TaskConfirm.model_validate(raw)
    assert msg.timeoutMs == 5000
