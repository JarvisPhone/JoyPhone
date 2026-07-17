import json
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator


class Node(BaseModel):
    id: str
    text: Optional[str] = None
    desc: Optional[str] = None
    className: Optional[str] = None
    viewIdResourceName: Optional[str] = None
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
    seq: int = 0  # 端侧递增序号，用于检测乱序


class ActionResult(BaseModel):
    type: Literal["action.result"] = "action.result"
    actionId: str
    ok: bool
    error: Optional[str] = None
    ts: int = 0
    seq: int = 0  # 端侧递增序号，用于检测乱序


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
    """上行:App 收到 task.confirm 后的结果(Toast 5秒倒计时结束,或飞书被切走视为取消)。"""
    type: Literal["task.confirm_response"] = "task.confirm_response"
    taskId: str
    confirmId: str
    approved: bool
    reason: str = ""
    ts: int = 0


class SampleCapture(BaseModel):
    """上行:探针采样帧。App 延时抓帧后上报,云端落盘供人工分析场景特征。"""
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
        "wait",
        "read_screen",
        "done",
        "abort",
        "request_confirm",
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


class TaskConfirm(_Downlink):
    """下行:发消息前的 Toast 确认请求。
    Android 端弹 5 秒 Toast,到时自动 approved=true,
    期间若飞书被切走(perception.pkg != target_pkg)则云端自动 approved=false。
    """
    type: Literal["task.confirm"] = "task.confirm"
    taskId: str
    confirmId: str
    target: str       # 期望的群名/联系人
    message: str      # 待发送文案(预览)
    timeoutMs: int    # 等待毫秒,Android 到点自动确认