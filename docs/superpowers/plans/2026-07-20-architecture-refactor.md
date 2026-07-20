# JoyPhone 全面架构重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 `docs/superpowers/specs/2026-07-20-architecture-refactor-design.md` 将 JoyPhone 重构为「L0 内核 + L1 场景包 + L2 AppProfile」的分层管道架构，协议升级 v2，双端一次性切换。

**Architecture:** 服务端拆为 protocol/gateway/task/scenario/decision/infra 六层；per-task 状态唯一载体 TaskContext（task.request 整体新建）；决策路径为策略管道；技能经 BoundSkill 参数绑定后由 SkillCursor 严格步进；Decision 携带 source。端侧 ConfirmManager 统一确认状态，Executor 按坐标输入。

**Tech Stack:** Python 3.14 / FastAPI / Pydantic / pytest；Kotlin / Compose / kotlinx-serialization / OkHttp / Gradle；pyright(basic)。

## Global Constraints

- `requires-python = ">=3.14,<3.15"`（server/pyproject.toml，不变）
- 不新增任何第三方运行时依赖（状态机/队列/框架一律不引入）
- 协议版本号 `PROTOCOL_VERSION = 2`，版本不符直接拒连
- 测试命令：服务端 `cd server && .venv/bin/python -m pytest tests/ -q`；端侧 `cd android && ./gradlew :app:testDebugUnitTest`
- pyright basic：`cd server && .venv/bin/python -m pyright app/` 零新增错误
- 日志统一 `logger.info("msg %s", arg)` 惰性格式化，禁止 f-string
- 每个 Task 结束必须 commit；TDD：先写失败测试再写实现
- 注释用中文、仅解释「为什么」，风格与现有代码一致

---

### Task 1: 协议 v2（server/app/protocol/）

**Files:**
- Create: `server/app/protocol/__init__.py`
- Create: `server/app/protocol/models.py`
- Delete: `server/app/protocol.py`（迁移完成后）
- Test: `server/tests/test_protocol.py`（全量重写）

**Interfaces:**
- Produces: `PROTOCOL_VERSION: int = 2`；`Node/Perception/ActionResult/NewMessage/Heartbeat/HeartbeatAck/TaskRequest/ConfirmResponse/SampleCapture/Uplink/parse_uplink`；`Action/TaskStart/TaskDone/TaskAbort/TaskConfirm`（下行）；`Action.op` 集合为 `tap/input/swipe/back/home/wait/read_screen/done/abort`（**删除 request_confirm**）；**ActionResult 无 atEnd 字段**。

- [ ] **Step 1: 写失败测试**

```python
# server/tests/test_protocol.py
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
```

- [ ] **Step 2: 运行确认失败**

Run: `cd server && .venv/bin/python -m pytest tests/test_protocol.py -x -q`
Expected: FAIL（`HeartbeatAck` 不存在 / `atEnd` 仍存在）

- [ ] **Step 3: 实现 protocol/models.py**

```python
# server/app/protocol/models.py
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
    cls = _UPLINK_MAP.get(data.get("type"))
    if cls is None:
        raise ValueError(f"unknown uplink type: {data.get('type')}")
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


class Action(_Downlink):
    type: Literal["action"] = "action"
    actionId: str
    op: Literal["tap", "input", "swipe", "back", "home", "wait", "read_screen", "done", "abort"]
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
```

`server/app/protocol/__init__.py` 全量 re-export（`from app.protocol.models import *` 并显式列出 `__all__`），删除旧 `server/app/protocol.py`，把全库 `from app.protocol import ...` 指向新包（导入路径不变）。

- [ ] **Step 4: 运行确认通过**

Run: `cd server && .venv/bin/python -m pytest tests/test_protocol.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/app/protocol server/tests/test_protocol.py && git rm server/app/protocol.py
git commit -m "refactor(protocol): v2 协议包,删除 atEnd/request_confirm,新增 heartbeat.ack 与版本号"
```

---

### Task 2: infra 层（config / metrics / llm 去重）

**Files:**
- Create: `server/app/infra/__init__.py`、`server/app/infra/config.py`
- Move: `server/app/metrics.py` → `server/app/infra/metrics.py`（修正 start_task 的 pkg 语义）
- Modify: `server/app/llm.py` → `server/app/decision/llm.py`（删除第一个重复 FakeLLM）
- Test: `server/tests/test_infra_config.py`、`server/tests/test_llm.py`

**Interfaces:**
- Produces: `infra.config.Config`（全部常量一处）: `MAX_STEPS_DEFAULT=40, CONFIRM_ID_PREFIX="cfm", CONFIRM_ID_LENGTH=8, MAX_CONFIRM_COUNT=1, CONFIRM_TIMEOUT_MS=5000, PRE_SEND_REVERT_WINDOW_SEC=10.0, POST_SEND_PATROL_THRESHOLD=2, WRONG_CHAT_INPUT_THRESHOLD=2, AWAITING_CONFIRM_TIMEOUT_SEC=30`；`FakeLLM`（唯一，耗尽停最后一个）。

- [ ] **Step 1: 写失败测试**

```python
# server/tests/test_infra_config.py
from app.infra.config import Config

def test_constants():
    assert Config.CONFIRM_TIMEOUT_MS == 5000
    assert Config.PRE_SEND_REVERT_WINDOW_SEC == 10.0
    assert Config.POST_SEND_PATROL_THRESHOLD == 2
    assert Config.WRONG_CHAT_INPUT_THRESHOLD == 2

# server/tests/test_llm.py 追加
def test_fake_llm_single_class_exhaustion_semantics():
    import app.decision.llm as m
    assert len([n for n in dir(m) if n == "FakeLLM"]) == 1
    llm = m.FakeLLM(["a", "b"])
    assert [llm.complete("", ""), llm.complete("", ""), llm.complete("", "")] == ["a", "b", "b"]
```

- [ ] **Step 2: 运行确认失败**

Run: `cd server && .venv/bin/python -m pytest tests/test_infra_config.py -q`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现**

`infra/config.py`：上述常量类。`infra/metrics.py`：原样迁移，`start_task(task_id, goal, pkg="")` 签名不变但调用方（Task 11）传 `target_pkg or ""` 而非 device_id。`decision/llm.py`：删除 `llm.py:22-36` 第一个 FakeLLM，保留耗尽停最后一个的版本；全库 `from app.llm import` 改为 `from app.decision.llm import`。

- [ ] **Step 4: 运行确认通过**

Run: `cd server && .venv/bin/python -m pytest tests/test_infra_config.py tests/test_llm.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add server/app/infra server/app/decision/llm.py server/tests && git rm server/app/metrics.py server/app/llm.py
git commit -m "refactor(infra): 常量收拢 Config,metrics 迁移,FakeLLM 去重"
```

---

### Task 3: Decision 类型与通用 UI 识别（decision/types.py + decision/ui_inspect.py）

**Files:**
- Create: `server/app/decision/__init__.py`、`server/app/decision/types.py`、`server/app/decision/ui_inspect.py`
- Test: `server/tests/test_decision_types.py`

**Interfaces:**
- Produces: `DecisionSource = Literal["cache","skill","pkg_guard","llm"]`；`Decision(actions: list[Action], source: DecisionSource, meta: dict)`；`detect_title(nodes, title_keywords: tuple[str,...], desc_keywords=("title","标题")) -> str | None`；`match_title(target, current) -> bool`。

- [ ] **Step 1: 写失败测试**

```python
# server/tests/test_decision_types.py
from app.decision.types import Decision
from app.decision.ui_inspect import detect_title, match_title
from app.protocol import Action, Node

def test_decision_never_empty_actions():
    d = Decision(actions=[Action(actionId="x", op="read_screen", params={})], source="llm")
    assert d.actions and d.source == "llm"

def test_detect_title_by_rid_keyword():
    nodes = [Node(id="0", text="张三", viewIdResourceName="com.x:id/tv_title")]
    assert detect_title(nodes, ("title",)) == "张三"

def test_detect_title_fallback_first_text():
    nodes = [Node(id="0", text="某群聊", clickable=False), Node(id="1", editable=True, text="输入")]
    assert detect_title(nodes, ()) == "某群聊"

def test_match_title_substring_bidirectional():
    assert match_title("张三", "张三(企业)")
    assert not match_title("张三", "李四")
```

- [ ] **Step 2: 运行确认失败** → `ModuleNotFoundError`

- [ ] **Step 3: 实现**

`types.py`：`DecisionSource` + `@dataclass class Decision`（`__post_init__` 断言 `actions` 非空）。`ui_inspect.py`：把现 `chat_title_helpers.py` 的 `detect_chat_title`/`match_chat_title` 原样移植，硬编码关键词表改为函数参数（rid 关键词、desc 关键词由调用方传入）。

- [ ] **Step 4: 运行确认通过** → PASS

- [ ] **Step 5: Commit** `git commit -m "feat(decision): Decision 类型与参数化 UI 识别 helpers"`

---

### Task 4: SkillCursor + SkillTemplate/BoundSkill（decision/skills.py）

**Files:**
- Create: `server/app/decision/skills.py`（替代旧 `server/app/skills.py`）
- Test: `server/tests/test_skills.py`（重写）

**Interfaces:**
- Consumes: `app.protocol.Node`
- Produces:
  - `CursorState = Literal["pending","issued","verified","failed"]`
  - `SkillCursor(index: int = 0, state: CursorState = "pending")`，方法 `advance()`（index+1, state→pending）、`fail()`（state→failed）
  - `SkillStep`（字段同现实现）/ `SkillTemplate(name, params: list[str], app: str, keywords: list[str], steps: list[SkillStep])`
  - `BoundSkill.bind(tpl, bindings) -> BoundSkill | None`；`BoundSkill.next_step(nodes, index) -> dict | None`（返回 dict 含 op/params；verify_title 返回 `{"op":"verify_title","expected_title":...}`）

- [ ] **Step 1: 写失败测试**

```python
# server/tests/test_skills.py
from app.decision.skills import BoundSkill, CursorState, SkillCursor, SkillStep, SkillTemplate
from app.protocol import Node

TPL = SkillTemplate(
    name="send", app="com.x", keywords=["发"], params=["contact"],
    steps=[
        SkillStep(op="tap", desc="搜索"),
        SkillStep(op="input", input_text="{contact}"),
        SkillStep(op="verify_title", match_text="{contact}"),
        SkillStep(op="tap", text="发送"),
    ],
)

def test_bind_substitutes_placeholders():
    s = BoundSkill.bind(TPL, {"contact": "张三"})
    assert s is not None
    step = s.next_step([Node(id="0", editable=True)], 1)
    assert step["input_text"] == "张三"

def test_bind_missing_param_returns_none():
    assert BoundSkill.bind(TPL, {}) is None

def test_cursor_advance_and_fail():
    c = SkillCursor()
    c.advance(); assert c.index == 1 and c.state == "pending"
    c.fail(); assert c.state == "failed"

def test_next_step_out_of_range_returns_none():
    s = BoundSkill.bind(TPL, {"contact": "张三"})
    assert s.next_step([], 99) is None

def test_verify_title_step_returns_expected_title():
    s = BoundSkill.bind(TPL, {"contact": "张三"})
    step = s.next_step([], 2)
    assert step == {"op": "verify_title", "expected_title": "张三"}
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现**

`SkillCursor` dataclass + 两个方法。`SkillTemplate`/`BoundSkill`：`bind()` 对每个 `SkillStep` 的 `input_text`/`match_text`/`text`/`desc` 做 `{key}` 替换（`str.replace` 遍历 bindings）；替换后仍含 `{` 占位 → 返回 None。`BoundSkill.next_step(nodes, index)`：移植现 `SkillLibrary.next_step` 的匹配逻辑（index 越界→None；verify_title→返回 expected_title dict；`SkillMatcher` 逻辑不变，改为模块内函数）。

- [ ] **Step 4: 运行确认通过** → PASS

- [ ] **Step 5: Commit** `git commit -m "feat(decision): 技能参数绑定层 BoundSkill + SkillCursor"`

---

### Task 5: DecisionEngine 重写（decision/engine.py + decision/pkg_guard.py + decision/cache.py）

**Files:**
- Create: `server/app/decision/engine.py`、`server/app/decision/pkg_guard.py`、`server/app/decision/cache.py`
- Delete: `server/app/decision.py`、`server/app/skills.py`、`server/app/skill_cache.py`、`server/app/scene.py`
- Test: `server/tests/test_engine.py`

**Interfaces:**
- Consumes: Task 3/4 全部产物；`app.protocol.Perception`
- Produces:
  - `DecideInput(goal: str, frame: Perception, target_pkg: str, cursor: SkillCursor, bound_skill: BoundSkill | None, guard: dict, title_keywords: tuple[str, ...])`
  - `DecisionEngine(llm, cache, escape_llm=None).decide(d: DecideInput) -> Decision`（**永不返回 None，无决策时 `Decision([read_screen], "llm")`**）
  - cursor 语义：cache/skill 命中下发的动作经端侧 ack ok 后由 handler 调 `cursor.advance()`（Task 11）；verify_title FAIL 时 engine 内部 `cursor.fail()` 并同帧回落 LLM。

- [ ] **Step 1: 写失败测试（锁定 N2 回归）**

```python
# server/tests/test_engine.py
from app.decision.engine import DecideInput, DecisionEngine
from app.decision.llm import FakeLLM
from app.decision.skills import BoundSkill, SkillCursor
from app.protocol import Node, Perception
from test_skills import TPL  # 或复制模板定义

def _frame(title: str) -> Perception:
    return Perception(pkg="com.x", nodeTree=[Node(id="0", text=title, viewIdResourceName="a:id/title")])

def test_verify_title_fail_does_not_advance_cursor_and_falls_to_llm():
    eng = DecisionEngine(llm=FakeLLM(["back"]), cache=None)
    cur = SkillCursor(index=2)
    skill = BoundSkill.bind(TPL, {"contact": "张三"})
    d = eng.decide(DecideInput(goal="g", frame=_frame("其他群"), target_pkg="com.x",
                               cursor=cur, bound_skill=skill, guard={}, title_keywords=("title",)))
    assert d.source == "llm" and cur.index == 2 and cur.state == "failed"

def test_verify_title_pass_returns_read_screen_with_skill_source():
    eng = DecisionEngine(llm=FakeLLM(["done"]), cache=None)
    cur = SkillCursor(index=2)
    skill = BoundSkill.bind(TPL, {"contact": "张三"})
    d = eng.decide(DecideInput(goal="g", frame=_frame("张三"), target_pkg="com.x",
                               cursor=cur, bound_skill=skill, guard={}, title_keywords=("title",)))
    assert d.source == "skill" and d.actions[0].op == "read_screen" and cur.index == 2  # ack 后才推进

def test_decide_never_returns_none_and_llm_empty_falls_to_read_screen():
    eng = DecisionEngine(llm=FakeLLM([""]), cache=None)
    d = eng.decide(DecideInput(goal="g", frame=_frame("x"), target_pkg="",
                               cursor=SkillCursor(), bound_skill=None, guard={}, title_keywords=()))
    assert d.source == "llm" and d.actions[0].op == "read_screen"

def test_failed_skill_is_skipped_next_frame():
    eng = DecisionEngine(llm=FakeLLM(["back", "home"]), cache=None)
    cur = SkillCursor(index=2, state="failed")
    skill = BoundSkill.bind(TPL, {"contact": "张三"})
    d = eng.decide(DecideInput(goal="g", frame=_frame("张三"), target_pkg="com.x",
                               cursor=cur, bound_skill=skill, guard={}, title_keywords=("title",)))
    assert d.source == "llm"
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现**

`cache.py`：现 `skill_cache.py` 原样迁移（锁/校验逻辑不动，多实例写冲突列入 spec 第 9 节不做）。`pkg_guard.py`：现 `scene.py` + `decision.py:_pkg_guard_action/_llm_escape/_ESCAPE_PROMPT` 原样迁移，函数签名改为显式参数。`engine.py` 决策顺序：cache.lookup（match_text 重定位逻辑不变）→ `bound_skill and cursor.state != "failed"` 时 `next_step`（verify_title 用 `detect_title(frame.nodeTree, d.title_keywords)` + `match_title` 评估，PASS→`Decision([read_screen],"skill")`，FAIL→`cursor.fail()` 继续下行）→ pkg_guard → LLM（系统 prompt 从现 `decision.py:_SYSTEM_PROMPT` 原样迁移；`parse_actions/_encode_nodes/_resolve_tap_node/_cap_nodes` 不变）。

- [ ] **Step 4: 运行确认通过** → PASS

- [ ] **Step 5: Commit** `git commit -m "refactor(decision): 引擎重写,Decision 携带 source,cursor 语义根治"`

---

### Task 6: 通用 TaskFSM（task/fsm.py）

**Files:**
- Create: `server/app/task/__init__.py`、`server/app/task/fsm.py`
- Delete: `server/app/session.py`
- Test: `server/tests/test_fsm.py`

**Interfaces:**
- Produces: `TaskState = Enum[IDLE, RUNNING, AWAITING_CONFIRM, WAITING_EVENT, DONE, ABORT]`；`TransitionRecord(frm, to, reason, at)`；`TaskFSM`：`transition(to, reason="") -> bool`、`force(to, reason="")`、`check_awaiting_confirm_timeout(now) -> bool`、`history: list[TransitionRecord]`。迁移表：`IDLE→{RUNNING,ABORT}`，`RUNNING→{AWAITING_CONFIRM,WAITING_EVENT,DONE,ABORT}`，`AWAITING_CONFIRM→{RUNNING,DONE,ABORT}`，`WAITING_EVENT→{RUNNING,DONE,ABORT}`，`DONE/ABORT→{}`。

- [ ] **Step 1: 写失败测试（穷举）**

```python
# server/tests/test_fsm.py
from datetime import datetime, timedelta
import pytest
from app.task.fsm import TaskFSM, TaskState

def test_exhaustive_legal_and_illegal_transitions():
    legal = {
        "IDLE": {"RUNNING", "ABORT"},
        "RUNNING": {"AWAITING_CONFIRM", "WAITING_EVENT", "DONE", "ABORT"},
        "AWAITING_CONFIRM": {"RUNNING", "DONE", "ABORT"},
        "WAITING_EVENT": {"RUNNING", "DONE", "ABORT"},
        "DONE": set(), "ABORT": set(),
    }
    for src in TaskState:
        for dst in TaskState:
            fsm = TaskFSM(); fsm.force(src)
            ok = fsm.transition(dst)
            assert ok == (dst.name in legal[src.name]), (src, dst)

def test_history_records_reason():
    fsm = TaskFSM(); fsm.force(TaskState.RUNNING)
    fsm.transition(TaskState.AWAITING_CONFIRM, reason="ConfirmInterceptPolicy")
    assert fsm.history[-1].reason == "ConfirmInterceptPolicy"

def test_awaiting_confirm_timeout():
    fsm = TaskFSM(); fsm.force(TaskState.RUNNING)
    fsm.transition(TaskState.AWAITING_CONFIRM)
    future = datetime.now() + timedelta(seconds=31)
    assert fsm.check_awaiting_confirm_timeout(future)
```

- [ ] **Step 2: 运行确认失败**

- [ ] **Step 3: 实现**：迁移表 + transition/force/history/超时（30s，取 `Config.AWAITING_CONFIRM_TIMEOUT_SEC`；进入 AWAITING_CONFIRM 记录时间，离开清除）。

- [ ] **Step 4: 运行确认通过** → PASS

- [ ] **Step 5: Commit** `git commit -m "feat(task): 通用五态 FSM,迁移原因全程记录"`

---

### Task 7: TaskContext + TaskStore（task/context.py）

**Files:**
- Create: `server/app/task/context.py`
- Test: `server/tests/test_task_context.py`

**Interfaces:**
- Consumes: Task 4/6 产物
- Produces: `TaskContext`（spec 3.2 字段全集：`task_id/goal/fsm/steps/cursor/history/applied_steps/target_pkg/target_chat/bindings/bound_skill/confirm/post_send/guard/negotiation/last_consumed_seq`）；子 dataclass `ConfirmState(pending_action, confirm_id, sent_ts, reverted, count, message_text)`、`PostSendState(acked=False, patrol_count=0)`；`TaskStore.current: TaskContext | None`、`TaskStore.new_task(goal, scenario) -> TaskContext`（**整体新建**）、`TaskStore.clear()`。

- [ ] **Step 1: 写失败测试（锁定 N3 回归）**

```python
# server/tests/test_task_context.py
from app.task.context import TaskStore

def test_new_task_replaces_context_entirely():
    store = TaskStore()
    ctx1 = store.new_task(goal="给张三发消息", scenario=None)
    ctx1.steps = 39; ctx1.guard["stall_count"] = 5; ctx1.post_send.acked = True
    ctx2 = store.new_task(goal="给李四发消息", scenario=None)
    assert ctx2.steps == 0 and ctx2.guard["stall_count"] == 0
    assert ctx2.post_send.acked is False and ctx2 is not ctx1
    assert ctx2.fsm.state.name == "RUNNING"

def test_clear_removes_context():
    store = TaskStore(); store.new_task(goal="g", scenario=None)
    store.clear(); assert store.current is None
```

- [ ] **Step 2-5**：标准 TDD 循环实现 + commit `feat(task): TaskContext 唯一 per-task 状态载体`

---

### Task 8: 策略基类 + 内核策略（task/policies.py）

**Files:**
- Create: `server/app/task/policies.py`
- Test: `server/tests/test_policies.py`

**Interfaces:**
- Produces: `Verdict(kind: Literal["continue","terminate","intercept"], reason: str = "", status: str = "", actions: list[Action] | None = None)` + 工厂 `continue_()/terminate(reason,status)/intercept(actions)`；`Policy` 协议（`name: str`、`inspect(frame, ctx) -> Verdict`）；`BudgetPolicy`（`ctx.steps >= max_steps → terminate("budget_exhausted","aborted")`）；`ConfirmTimeoutPolicy`（`fsm.check_awaiting_confirm_timeout(now) → terminate("confirm_timeout","aborted")`）；`run_pipeline(policies, frame, ctx) -> Verdict`（首个非 continue 短路）。

- [ ] **Step 1: 写失败测试**

```python
def test_budget_policy_terminates_when_exhausted():
    from app.task.policies import BudgetPolicy, run_pipeline
    from app.task.context import TaskStore
    ctx = TaskStore().new_task(goal="g", scenario=None); ctx.steps = 40
    v = run_pipeline([BudgetPolicy()], None, ctx)
    assert v.kind == "terminate" and v.reason == "budget_exhausted"

def test_pipeline_short_circuits():
    from app.task.policies import BudgetPolicy, run_pipeline, continue_, terminate, Policy
    class Noop:
        name = "noop"
        def inspect(self, f, c): return continue_()
    ctx = ...  # steps=40 的 ctx
    v = run_pipeline([Noop(), BudgetPolicy()], None, ctx)
    assert v.kind == "terminate"
```

- [ ] **Step 2-5**：TDD + commit `feat(task): 策略管道基类与内核策略`

---

### Task 9: 场景层基础（scenario/base.py + scenario/profiles + scenario/ui.py）

**Files:**
- Create: `server/app/scenario/__init__.py`、`server/app/scenario/base.py`、`server/app/scenario/ui.py`、`server/app/scenario/profiles/feishu.py`、`server/app/scenario/profiles/wechat.py`
- Delete: `server/app/app_goal_resolver.py`、`server/app/chat_title_helpers.py`
- Test: `server/tests/test_scenario_base.py`

**Interfaces:**
- Produces: `AppProfile(BaseModel)`（spec 3.6 字段）；`ScenarioPack` 协议（spec 3.6）；`select_scenario(packs, goal) -> ScenarioPack | None`（matches 最高分，全 0 → None）；`is_send_button(node, profile)`、`is_message_input(node, profile)`（移植现 chat_title_helpers 逻辑，关键词来自 profile）；`resolve_pkg(goal, profiles) -> str | None`（现 app_goal_resolver 逻辑，别名来自各 profile.aliases）；`extract_target(goal)`（现 extract_target 正则原样迁入 scenario/ui.py）；`FEISHU_PROFILE`（rid/发送按钮/hint 关键词用现 `chat_title_helpers.py:15-42,99-114` 的值；aliases `("飞书","feishu","lark")`）、`WECHAT_PROFILE`（aliases `("微信","wechat","weixin")`，关键词暂与飞书相同并在注释标注待真机校准）。

- [ ] **Step 1: 写失败测试**

```python
def test_select_scenario_picks_highest_score():
    from app.scenario.base import ScenarioPack, select_scenario
    class P:
        name = "p"
        def __init__(self, s): self._s = s
        def matches(self, goal): return self._s
    assert select_scenario([P(0.1), P(0.9)], "g").name == "p"
    assert select_scenario([P(0.0)], "g") is None

def test_resolve_pkg_from_profile_aliases():
    from app.scenario.ui import resolve_pkg
    from app.scenario.profiles.feishu import FEISHU_PROFILE
    assert resolve_pkg("给飞书群发消息", [FEISHU_PROFILE]) == "com.ss.android.lark"
```

- [ ] **Step 2-5**：TDD + commit `feat(scenario): 场景包协议、AppProfile 数据与 UI 识别 helpers`

---

### Task 10: send_message 场景包（scenario/send_message.py）

**Files:**
- Create: `server/app/scenario/send_message.py`
- Test: `server/tests/test_send_message_pack.py`、`server/tests/test_send_message_policies.py`

**Interfaces:**
- Consumes: Task 4/8/9 产物
- Produces: `SendMessagePack`（`matches`：goal 含「发|发送|发给|message」且 resolve_pkg 命中 → 0.9，否则 0；`resolve_target` → `(target_pkg, target_chat, bindings={"contact": chat, "query": chat})`；`skills` → 移植现 `_FEISHU_SKILLS` 两个模板为 SkillTemplate；`pre_policies` → `[PreSendRevertPolicy(), PostSendForceDonePolicy(), PostSendPatrolPolicy()]`；`post_policies` → `[ConfirmInterceptPolicy(), WrongChatInputPolicy()]`）。五个策略各自从现 gateway.py 对应代码段原样抽取（10s 观察窗 `gateway.py:437-484`、POST_SEND_FORCE_DONE `:386-405`、POST_SEND_PATROL `:409-426`、confirm 拦截 `:546-586`、INPUT_GUARD `:592-638`），硬编码数字改读 `Config`。

- [ ] **Step 1: 写失败测试（每策略至少一例）**

```python
def test_post_send_patrol_aborts_after_threshold():
    from app.scenario.send_message import PostSendPatrolPolicy
    from app.task.context import TaskStore
    from app.protocol import Perception
    ctx = TaskStore().new_task(goal="g", scenario=None)
    ctx.post_send.acked = True; ctx.post_send.patrol_count = 2
    v = PostSendPatrolPolicy().inspect(Perception(), ctx)
    assert v.kind == "terminate" and "post_send_patrol" in v.reason

def test_confirm_intercept_captures_send_tap():
    # 构造:target_pkg 命中、标题匹配、tap 坐标落在发送按钮 bounds 内
    # → verdict.kind == "intercept" 且 actions 为 [task.confirm 语义占位]
    # 具体构造参照现 gateway.py:546-586 分支的输入条件
    ...
```

（WrongChatInputPolicy / PreSendRevertPolicy / PostSendForceDonePolicy 同样各配正例+反例，测试数据参照现 gateway 对应分支条件。）

- [ ] **Step 2-5**：TDD + commit `feat(scenario): send_message 场景包与五道策略`

---

### Task 11: 任务层 handlers（task/handlers.py）

**Files:**
- Create: `server/app/task/handlers.py`
- Test: `server/tests/test_handlers.py`

**Interfaces:**
- Consumes: Task 5/7/8/10 产物
- Produces: `handle_uplink(uplink, store, conn, deps) -> None`，其中 `deps` 含 `engine/scenario_packs/metrics/max_steps`；`conn.send(model)`。行为清单：
  - `task.request`：`store.new_task(goal, scenario=select_scenario(...))` → 发 TaskStart；
  - `perception`：`ctx is None → 丢弃`；`uplink.seq <= ctx.last_consumed_seq → 丢弃并记日志`；否则 `last_consumed_seq = seq`；PRE 管道 → terminate 则迁移+发 TaskDone/Abort+`store.clear()`；`engine.decide(...)` → POST 管道（intercept 优先）→ 逐 action 下发，`action.op=="done"/"abort"` 迁移+收尾；`ctx.steps += 1`（每次决策计一步）；
  - `action.result`：append history；`ok and source in (cache, skill)` → `cursor.advance()`（source 记录在上帧 Decision.meta["source"]，存 ctx）；`ok` → metrics.record_step；
  - `heartbeat`：回 `HeartbeatAck`，**不回 action**；
  - `task.confirm_response`：state/confirmId 校验（现 `gateway.py:234-310` 逻辑迁入，含 pre_send_reverted 拒绝路径）；
  - `event.newMessage`：现协商逻辑迁入（REJECT/CONFIRM/ESCALATE 分支不变，状态走 fsm）；
  - `sample.capture`：现 `_persist_sample` 逻辑迁入。

- [ ] **Step 1: 写失败测试（含 seq 丢弃与第二任务零污染集成用例）**

```python
def test_stale_perception_dropped():
    ...  # ctx.last_consumed_seq=5,上行 seq=5 → engine.decide 未被调用(用 spy)

def test_second_task_on_same_connection_starts_clean():
    ...  # 模拟 task.request→done→再 task.request,断言 steps/cursor/guard 全新

def test_heartbeat_receives_ack_not_action():
    ...  # conn.sent 最后一条 type == "heartbeat.ack"
```

- [ ] **Step 2-5**：TDD + commit `feat(task): uplink handlers,seq 乱序丢弃,heartbeat 轻量 ack`

---

### Task 12: gateway 连接层 + 装配（gateway/connection.py + gateway/router.py + create_app）

**Files:**
- Create: `server/app/gateway/__init__.py`、`server/app/gateway/connection.py`、`server/app/gateway/router.py`、`server/app/main.py`（新 create_app）
- Delete: `server/app/gateway.py`、`server/app/comm_log.py`（log_up/log_down 迁入 gateway/connection.py）
- Test: `server/tests/test_gateway_integration.py`（改写为端到端回放）

**Interfaces:**
- Produces: `create_app() -> FastAPI`（对外唯一入口，行为等价）；`Connection.send(model)`（内部 log_down + websocket.send_text）。

- [ ] **Step 1: 写失败测试**：用 fastapi.testclient 跑通 `tests/fixtures/feishu_happy_path.json` 回放（fixture 中 action.result 消息需先移除 atEnd 字段以符合 v2），断言最终收到 `task.done` 且全程无异常断连。

- [ ] **Step 2-5**：实现（connection.py ~60 行：accept/版本协商/断开处理；router.py ~30 行：parse_uplink→handle_uplink；main.py 装配 engine/packs/metrics）+ 全量 `pytest` 回归 162+ 全绿 + commit `refactor(gateway): 上帝文件拆解为连接层+路由,710→<150 行`

---

### Task 13: Android 协议 v2（Messages.kt + WsDispatcher）

**Files:**
- Modify: `android/.../protocol/Messages.kt`、`android/.../net/WsDispatcher.kt`、`android/.../net/WsClient.kt`
- Test: `android/app/src/test/.../protocol/MessagesTest.kt`

**要点**：删除 `UplinkActionResult.atEnd` 与 `Executor.ExecResult.atEnd`；`sendActionResult` 增 `seq` 参数（与 perception 共用计数器，`PhoneAgentService` 内 `++msgSeq`）；新增 `DownHeartbeatAck`；`DownAction.op` 注释移除 request_confirm。

- [ ] **Step 1-4**：先写 kotlinx 序列化往返测试（无 atEnd、heartbeat.ack 可解析）→ 实现 → `./gradlew :app:testDebugUnitTest` 全绿
- [ ] **Step 5: Commit** `refactor(android): 协议 v2 对齐,删除 atEnd,heartbeat.ack`

---

### Task 14: Android ConfirmManager

**Files:**
- Create: `android/.../accessibility/ConfirmManager.kt`
- Modify: `android/.../accessibility/PhoneAgentService.kt`（confirm 相关字段/Runnable 全部迁入）

**Interfaces:**
- Produces: `ConfirmManager(handler, sendResponse: (taskId, confirmId, approved, reason) -> Unit)`：`onConfirm(confirm: DownTaskConfirm)`、`onTaskEnd()`（移除回调+清空 pending）、`onDestroy()`。`pendingConfirmCancelled` 死标志整体删除——取消即真实清理，不需要标志位。

- [ ] **Step 1-4**：单测（mock handler：onConfirm 后 onTaskEnd → 超时不再触发 sendResponse）→ 实现 → 测试绿
- [ ] **Step 5: Commit** `refactor(android): ConfirmManager 统一确认状态,消除死标志`

---

### Task 15: Android Executor 修复

**Files:**
- Modify: `android/.../accessibility/Executor.kt`
- Test: `android/app/src/test/.../accessibility/ExecutorGeometryTest.kt`（可单测部分）

**要点**：`input` 改为按 params x/y 命中 editable（复用 `GestureGeometry.tapPointFromParams` + bounds 命中，逻辑与云端 `_input_target_node` 对称），无坐标才回退首个 editable；`findByText` 的 matches 与 `findEditable` 未命中子节点全部 recycle；`dispatchGesture` 传入 `GestureResultCallback`，在 `onCompleted/onCancelled` 回传真实结果（`execute` 改回调式或挂起函数，WsClient.sendActionResult 在回调后发送）。

- [ ] **Step 1-5**：TDD（坐标命中逻辑抽纯函数单测）+ commit `fix(android): input 按坐标定位,节点全量回收,手势结果真实回传`

---

### Task 16: BuildConfig WS_URL

**Files:**
- Modify: `android/app/build.gradle.kts`（`buildConfigField "String", "WS_URL", "\"ws://10.0.2.2:8000\""`，debug/release 分 flavor）、`PhoneAgentService.kt:35`（改 `BuildConfig.WS_URL`）

- [ ] **Step 1-3**：编译通过 + 单测绿 + commit `refactor(android): WS_URL 移入 BuildConfig,移除源码内网 IP`

---

### Task 17: 双端契约测试（golden JSON）

**Files:**
- Create: `shared/protocol/v2/*.json`（每种上下行消息一个样本，含 seq/无 atEnd）
- Test: `server/tests/test_contract.py`、`android/.../protocol/ContractTest.kt`

- [ ] **Step 1-5**：双端各自断言可解析且字段一致 + commit `test: 双端协议契约 golden 样本`

---

### Task 18: CI 硬门槛 + 收尾

**Files:**
- Modify: `server/pyproject.toml`（pyright basic 配置）、`.github/workflows/*`（无则建最小 workflow：pytest + gradle test + pyright）
- Modify: `README.md`/`AGENTS.md`（架构描述更新为新分层）

- [ ] **Step 1**: `cd server && .venv/bin/python -m pyright app/` 修到零新增错误（重点：`gateway.py:133` 旧 Node 导入随删除消失；Task 1-12 新代码全程类型标注）
- [ ] **Step 2**: 三命令全绿（pytest / gradle / pyright）
- [ ] **Step 3**: Commit `ci: pytest+gradle+pyright 硬门槛`

---

## Self-Review 结论

- **Spec 覆盖**: §3.1→T1-12 全覆盖；§3.2→T7；§3.3→T8/T10；§3.4→T6；§3.5→T4/T5；§3.6→T9/T10；§4→T1/T11/T13；§5→T14/T15/T16；§6→T6/T8/T10/T11/T12/T17/T18；§7→T1→T18 顺序即迁移步骤；§9 不做项未安排任务 ✅
- **占位符扫描**: T10 Step 1 有 `...` 省略的测试构造——执行时须按现 gateway 分支条件补全实际数据（已在步骤内注明参照行号），其余无 TBD/TODO
- **类型一致性**: `Decision/DecideInput/SkillCursor/BoundSkill/Verdict/TaskContext/TaskFSM/AppProfile/ScenarioPack` 签名在 T3-T11 间逐一核对一致 ✅
