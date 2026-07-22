import json
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator

PROTOCOL_VERSION = 2


class Node(BaseModel):
    id: str
    text: Optional[str] = None
    desc: Optional[str] = None
    className: Optional[str] = None
    viewIdResourceName: Optional[str] = None
    bounds: Optional[tuple[int, int, int, int]] = None
    clickable: bool = False
    editable: bool = False


# ---- 上行 ----
class Perception(BaseModel):
    type: Literal["perception"] = "perception"
    nodeTree: list[Node] = Field(default_factory=list)
    screenshot: Optional[str] = None
    pkg: str = ""
    activity: str = ""
    ts: int = 0
    seq: int = 0


class ActionResult(BaseModel):
    type: Literal["action.result"] = "action.result"
    actionId: str
    ok: bool
    error: Optional[str] = None
    ts: int = 0
    seq: int = 0


class NewMessage(BaseModel):
    type: Literal["event.newMessage"] = "event.newMessage"
    app: str
    sender: str
    text: str
    ts: int = 0


class Heartbeat(BaseModel):
    type: Literal["heartbeat"] = "heartbeat"
    deviceId: str
    ts: int = 0


class TaskRequest(BaseModel):
    type: Literal["task.request"] = "task.request"
    goal: str


class ConfirmResponse(BaseModel):
    type: Literal["task.confirm_response"] = "task.confirm_response"
    taskId: str
    confirmId: str
    approved: bool
    reason: str = ""
    ts: int = 0


class SampleCapture(BaseModel):
    type: Literal["sample.capture"] = "sample.capture"
    label: str
    nodeTree: list[Node] = Field(default_factory=list)
    pkg: str = ""
    activity: str = ""
    ts: int = 0
    device: str = ""


Uplink = Union[Perception, ActionResult, NewMessage, Heartbeat, TaskRequest, ConfirmResponse, SampleCapture]

_UPLINK_MAP = {
    "perception": Perception,
    "action.result": ActionResult,
    "event.newMessage": NewMessage,
    "heartbeat": Heartbeat,
    "task.request": TaskRequest,
    "task.confirm_response": ConfirmResponse,
    "sample.capture": SampleCapture,
}


def parse_uplink(raw: str) -> Uplink:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON: {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be object, got {type(data).__name__}")
    uplink_type = data.get("type")
    cls = _UPLINK_MAP.get(uplink_type) if isinstance(uplink_type, str) else None
    if cls is None:
        raise ValueError(f"unknown uplink type: {uplink_type}")
    return cls(**data)


# ---- 下行 ----
class _Downlink(BaseModel):
    def to_json(self) -> str:
        return self.model_dump_json()


class TaskStart(_Downlink):
    type: Literal["task.start"] = "task.start"
    taskId: str
    goal: str
    target: str


Op = Literal["tap", "tap_at", "input", "swipe", "back", "home", "wait", "read_screen", "done", "abort"]


class Action(_Downlink):
    type: Literal["action"] = "action"
    actionId: str
    op: Op
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("params", mode="before")
    @classmethod
    def _coerce_params_to_str(cls, v: Any) -> dict[str, str]:
        # 端侧 params 是 Map<String,String>,统一强转防止端侧反序列化异常
        if not isinstance(v, dict):
            return v
        return {str(k): str(val) for k, val in v.items()}


class TaskDone(_Downlink):
    type: Literal["task.done"] = "task.done"
    taskId: str
    result: str
    summary: str = ""


class TaskAbort(_Downlink):
    type: Literal["task.abort"] = "task.abort"
    taskId: str
    reason: str


class TaskConfirm(_Downlink):
    type: Literal["task.confirm"] = "task.confirm"
    taskId: str
    confirmId: str
    target: str
    message: str
    timeoutMs: int


class HeartbeatAck(_Downlink):
    type: Literal["heartbeat.ack"] = "heartbeat.ack"
    deviceId: str
    ts: int = 0
