import json
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator


class Node(BaseModel):
    id: str
    text: Optional[str] = None
    desc: Optional[str] = None
    className: Optional[str] = None
    bounds: Optional[tuple[int, int, int, int]] = None  # [left, top, right, bottom]
    clickable: bool = False
    editable: bool = False


# ---- 上行：App -> 云端 ----
class Perception(BaseModel):
    type: Literal["perception"] = "perception"
    nodeTree: list[Node] = Field(default_factory=list)
    screenshot: Optional[str] = None  # base64，可选
    pkg: str = ""
    activity: str = ""
    ts: int = 0


class ActionResult(BaseModel):
    type: Literal["action.result"] = "action.result"
    actionId: str
    ok: bool
    atEnd: bool = False
    error: Optional[str] = None
    ts: int = 0


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


Uplink = Union[Perception, ActionResult, NewMessage, Heartbeat, TaskRequest]

_UPLINK_MAP = {
    "perception": Perception,
    "action.result": ActionResult,
    "event.newMessage": NewMessage,
    "heartbeat": Heartbeat,
    "task.request": TaskRequest,
}


def parse_uplink(raw: str) -> Uplink:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed JSON: {exc.msg}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"JSON root must be object, got {type(data).__name__}")

    t = data.get("type")
    cls = _UPLINK_MAP.get(t)
    if cls is None:
        raise ValueError(f"unknown uplink type: {t}")
    return cls(**data)


# ---- 下行：云端 -> App ----
class _Downlink(BaseModel):
    def to_json(self) -> str:
        return self.model_dump_json()


class TaskStart(_Downlink):
    type: Literal["task.start"] = "task.start"
    taskId: str
    goal: str
    target: str


class Action(_Downlink):
    type: Literal["action"] = "action"
    actionId: str
    op: Literal[
        "tap",
        "input",
        "swipe",
        "back",
        "home",
        "home_first_page",
        "next_page",
        "wait",
        "read_screen",
        "done",
        "abort",
    ]
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("params", mode="before")
    @classmethod
    def _coerce_params_to_str(cls, v: Any) -> dict[str, str]:
        # 端侧 DownAction.params 是 Map<String,String>，此处统一将所有 value 强转为字符串，
        # 覆盖 SkillCache / SkillLibrary / LLM 三条决策分支，防止端侧反序列化抛异常。
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