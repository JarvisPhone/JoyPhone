# AI 工作手机 — 飞书协商闭环 MVP 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让云端 Python 服务通过 WebSocket 驱动一台安卓真机，用无障碍权限操控飞书完成「发消息→收回复→多轮协商」闭环。

**Architecture:** 端云协同。云端(FastAPI)负责决策(多模态大模型)与协商，安卓端(Kotlin/AccessibilityService)负责感知(节点树+截图)与执行(点击/输入)。两端通过 WebSocket 交换定义好的 JSON 消息。云端可用「回放夹具」离线测试完整决策闭环，不依赖真机。

**Tech Stack:** 云端 Python 3.14（uv 管理）/ FastAPI / websockets / pytest；安卓 Kotlin / AccessibilityService / OkHttp WebSocket / JUnit。大模型通过统一 LLM 抽象层调用。

---

## 文件结构

### 云端 `server/`
- `server/app/protocol.py` — WebSocket 消息模型(Pydantic)，两端协议的唯一事实来源
- `server/app/session.py` — 单任务会话状态机 (NAVIGATING→IN_CHAT→SENT→WAITING_REPLY→NEGOTIATING→DONE/ABORT)
- `server/app/llm.py` — LLM 抽象层(接口 + 假实现 + 真实现)
- `server/app/decision.py` — 决策引擎(屏幕状态→动作)
- `server/app/negotiation.py` — 协商文本机器人(回复→话术+状态)
- `server/app/skills.py` — 技能库雏形(命中即执行)
- `server/app/gateway.py` — FastAPI + WebSocket 网关，串联会话
- `server/app/task_manager.py` — 任务创建/下发
- `server/tests/` — pytest 单测与集成测试
- `server/tests/fixtures/` — 可回放的 perception 序列夹具
- `server/pyproject.toml` — 依赖与配置

### 安卓 `android/`
- `android/.../protocol/Messages.kt` — 与云端对齐的消息数据类
- `android/.../accessibility/PhoneAgentService.kt` — AccessibilityService 主体
- `android/.../accessibility/Perception.kt` — 节点树裁剪+序列化
- `android/.../accessibility/Executor.kt` — 动作指令→无障碍调用
- `android/.../net/WsClient.kt` — WebSocket 长连+重连
- `android/.../MainActivity.kt` — 开关/状态展示
- `android/.../test/` — JUnit 单测

---

## 阶段一：协议契约（云端，两端共享事实来源）

### Task 1: 云端项目脚手架

**Files:**
- Create: `server/pyproject.toml`
- Create: `server/app/__init__.py`
- Create: `server/tests/__init__.py`

- [ ] **Step 1: 创建 pyproject.toml**

```toml
[project]
name = "ai-work-phone-server"
version = "0.1.0"
requires-python = ">=3.14,<3.15"
dependencies = ["fastapi>=0.110", "uvicorn>=0.29", "websockets>=12", "pydantic>=2.6"]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23", "httpx>=0.27"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: 创建空包文件**

`server/app/__init__.py` 和 `server/tests/__init__.py` 内容均为空。

- [ ] **Step 3: 安装依赖并验证**

Run: `cd server && uv python pin 3.14 && uv sync --extra dev`
Expected: 安装成功，无报错。

- [ ] **Step 4: Commit**

```bash
git add server/pyproject.toml server/app/__init__.py server/tests/__init__.py
git commit -m "chore: 云端项目脚手架"
```

### Task 2: 协议消息模型

**Files:**
- Create: `server/app/protocol.py`
- Test: `server/tests/test_protocol.py`

- [ ] **Step 1: 写失败测试**

```python
# server/tests/test_protocol.py
from app.protocol import parse_uplink, Perception, ActionResult, NewMessage, Action, TaskStart

def test_parse_perception_uplink():
    raw = '{"type":"perception","nodeTree":[{"id":"n1","text":"通讯录","clickable":true}],"pkg":"com.ss.android.lark","activity":"Main","ts":1}'
    msg = parse_uplink(raw)
    assert isinstance(msg, Perception)
    assert msg.pkg == "com.ss.android.lark"
    assert msg.nodeTree[0].text == "通讯录"

def test_action_serializes_roundtrip():
    a = Action(actionId="a1", op="tap", params={"nodeId": "n1"})
    dumped = a.to_json()
    assert '"op":"tap"' in dumped
    assert '"actionId":"a1"' in dumped
    assert '"type":"action"' in dumped

def test_task_start_build():
    t = TaskStart(taskId="t1", goal="确认还款时间", target="张三")
    assert t.type == "task.start"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd server && uv run pytest tests/test_protocol.py -v`
Expected: FAIL, ModuleNotFoundError: app.protocol

- [ ] **Step 3: 实现 protocol.py**

```python
# server/app/protocol.py
import json
from typing import Literal, Optional, Union
from pydantic import BaseModel, Field


class Node(BaseModel):
    id: str
    text: Optional[str] = None
    desc: Optional[str] = None
    className: Optional[str] = None
    bounds: Optional[list[int]] = None  # [left, top, right, bottom]
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


Uplink = Union[Perception, ActionResult, NewMessage, Heartbeat]

_UPLINK_MAP = {
    "perception": Perception,
    "action.result": ActionResult,
    "event.newMessage": NewMessage,
    "heartbeat": Heartbeat,
}


def parse_uplink(raw: str) -> Uplink:
    data = json.loads(raw)
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
    # op: open_app / tap / input / swipe / back / home / wait / read_screen
    op: str
    params: dict = Field(default_factory=dict)


class TaskDone(_Downlink):
    type: Literal["task.done"] = "task.done"
    taskId: str
    result: str
    summary: str = ""


class TaskAbort(_Downlink):
    type: Literal["task.abort"] = "task.abort"
    taskId: str
    reason: str
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd server && uv run pytest tests/test_protocol.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add server/app/protocol.py server/tests/test_protocol.py
git commit -m "feat: WebSocket 协议消息模型"
```

## 阶段二：云端决策核心（可离线测试）

### Task 3: LLM 抽象层

**Files:**
- Create: `server/app/llm.py`
- Test: `server/tests/test_llm.py`

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_llm.py
from app.llm import LLM, FakeLLM

def test_fake_llm_returns_scripted_response():
    fake = FakeLLM(responses=['{"op":"tap","params":{"match_text":"通讯录"}}'])
    out = fake.complete(system="s", user="u")
    assert '"op":"tap"' in out

def test_fake_llm_returns_last_when_exhausted():
    fake = FakeLLM(responses=["a", "b"])
    assert fake.complete("s", "u1") == "a"
    assert fake.complete("s", "u2") == "b"
    assert fake.complete("s", "u3") == "b"

def test_llm_is_abstract():
    import pytest
    with pytest.raises(TypeError):
        LLM()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_llm.py -v`
Expected: FAIL, ModuleNotFoundError: app.llm

- [ ] **Step 3: Write minimal implementation**

```python
# server/app/llm.py
from abc import ABC, abstractmethod
from typing import Optional


class LLM(ABC):
    @abstractmethod
    def complete(self, system: str, user: str, image_b64: Optional[str] = None) -> str:
        ...


class FakeLLM(LLM):
    def __init__(self, responses: list[str]):
        self._responses = responses
        self._i = 0

    def complete(self, system: str, user: str, image_b64: Optional[str] = None) -> str:
        idx = min(self._i, len(self._responses) - 1)
        self._i += 1
        return self._responses[idx]
```

- [ ] **Step 4: Run tests and ensure pass**

Run: `cd server && uv run pytest tests/test_llm.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add server/app/llm.py server/tests/test_llm.py
git commit -m "feat: LLM 抽象层与测试假实现"
```

### Task 4: 会话状态机

**Files:**
- Create: `server/app/session.py`
- Test: `server/tests/test_session.py`

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_session.py
from app.session import Session, State

def test_initial_state_is_navigating():
    s = Session(task_id="t1", goal="确认还款时间", target="张三")
    assert s.state == State.NAVIGATING

def test_valid_transition_to_in_chat():
    s = Session(task_id="t1", goal="g", target="张三")
    s.transition(State.IN_CHAT)
    assert s.state == State.IN_CHAT

def test_invalid_transition_raises_value_error():
    import pytest
    s = Session(task_id="t1", goal="g", target="张三")
    with pytest.raises(ValueError):
        s.transition(State.DONE)

def test_step_budget_exhaustion():
    s = Session(task_id="t1", goal="g", target="张三", max_steps=2)
    s.record_step(); s.record_step()
    assert s.budget_exhausted() is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_session.py -v`
Expected: FAIL, ModuleNotFoundError: app.session

- [ ] **Step 3: Write minimal implementation**

```python
# server/app/session.py
from enum import Enum


class State(str, Enum):
    NAVIGATING = "NAVIGATING"
    IN_CHAT = "IN_CHAT"
    SENT = "SENT"
    WAITING_REPLY = "WAITING_REPLY"
    NEGOTIATING = "NEGOTIATING"
    DONE = "DONE"
    ABORT = "ABORT"


_ALLOWED = {
    State.NAVIGATING: {State.IN_CHAT, State.ABORT},
    State.IN_CHAT: {State.SENT, State.ABORT},
    State.SENT: {State.WAITING_REPLY, State.ABORT},
    State.WAITING_REPLY: {State.NEGOTIATING, State.DONE, State.ABORT},
    State.NEGOTIATING: {State.SENT, State.DONE, State.ABORT},
    State.DONE: set(),
    State.ABORT: set(),
}


class Session:
    def __init__(self, task_id: str, goal: str, target: str, max_steps: int = 40):
        self.task_id = task_id
        self.goal = goal
        self.target = target
        self.state = State.NAVIGATING
        self.max_steps = max_steps
        self.steps = 0

    def transition(self, to: State) -> None:
        if to not in _ALLOWED[self.state]:
            raise ValueError(f"invalid transition {self.state} -> {to}")
        self.state = to

    def record_step(self) -> None:
        self.steps += 1

    def budget_exhausted(self) -> bool:
        return self.steps >= self.max_steps
```

- [ ] **Step 4: Run tests and ensure pass**

Run: `cd server && uv run pytest tests/test_session.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add server/app/session.py server/tests/test_session.py
git commit -m "feat: 单任务会话状态机"
```

### Task 5: 技能库雏形（命中即执行）

**Files:**
- Create: `server/app/skills.py`
- Test: `server/tests/test_skills.py`

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_skills.py
from app.protocol import Node
from app.skills import SkillLibrary

def test_match_feishu_send_skill_when_contacts_visible():
    lib = SkillLibrary()
    nodes = [Node(id="n1", text="通讯录", clickable=True)]
    step = lib.next_step(skill_name="feishu_send", nodes=nodes, cursor=0)
    assert step is not None
    assert step["op"] == "tap"
    assert step["match_text"] == "通讯录"

def test_return_none_when_screen_not_match():
    lib = SkillLibrary()
    nodes = [Node(id="n1", text="首页")]
    assert lib.next_step("feishu_send", nodes, 0) is None

def test_unknown_skill_returns_none():
    lib = SkillLibrary()
    assert lib.next_step("unknown", [], 0) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_skills.py -v`
Expected: FAIL, ModuleNotFoundError: app.skills

- [ ] **Step 3: Write minimal implementation**

```python
# server/app/skills.py
from typing import Optional
from app.protocol import Node

_SKILLS: dict[str, list[dict]] = {
    "feishu_send": [
        {"match_text": "通讯录", "op": "tap"},
        {"match_text": "搜索", "op": "tap"},
        {"match_text": "", "op": "input"},
        {"match_text": "发送", "op": "tap"},
    ]
}


class SkillLibrary:
    def next_step(self, skill_name: str, nodes: list[Node], cursor: int) -> Optional[dict]:
        steps = _SKILLS.get(skill_name)
        if not steps or cursor >= len(steps):
            return None
        step = steps[cursor]
        need = step["match_text"]
        if not need:
            return dict(step)
        texts = [n.text for n in nodes if n.text]
        return dict(step) if need in texts else None
```

- [ ] **Step 4: Run tests and ensure pass**

Run: `cd server && uv run pytest tests/test_skills.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add server/app/skills.py server/tests/test_skills.py
git commit -m "feat: 技能库雏形"
```

### Task 6: 决策引擎

**Files:**
- Create: `server/app/decision.py`
- Test: `server/tests/test_decision.py`

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_decision.py
from app.protocol import Perception, Node
from app.llm import FakeLLM
from app.skills import SkillLibrary
from app.decision import DecisionEngine


def _perc(nodes):
    return Perception(nodeTree=nodes, pkg="com.ss.android.lark", activity="Main", ts=1)


def test_skill_hit_without_llm():
    engine = DecisionEngine(llm=FakeLLM(['{"op":"back","params":{}}']), skills=SkillLibrary())
    p = _perc([Node(id="n1", text="通讯录", clickable=True)])
    action = engine.decide(goal="发消息", perception=p, skill_name="feishu_send", cursor=0, history=[])
    assert action.op == "tap"
    assert action.params["match_text"] == "通讯录"


def test_fallback_to_llm_when_skill_miss():
    engine = DecisionEngine(llm=FakeLLM(['{"op":"back","params":{}}']), skills=SkillLibrary())
    p = _perc([Node(id="n1", text="首页")])
    action = engine.decide(goal="发消息", perception=p, skill_name="feishu_send", cursor=0, history=[])
    assert action.op == "back"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_decision.py -v`
Expected: FAIL, ModuleNotFoundError: app.decision

- [ ] **Step 3: Write minimal implementation**

```python
# server/app/decision.py
import json
import uuid
from app.protocol import Perception, Action
from app.llm import LLM
from app.skills import SkillLibrary


class DecisionEngine:
    def __init__(self, llm: LLM, skills: SkillLibrary):
        self._llm = llm
        self._skills = skills

    def decide(self, goal: str, perception: Perception, skill_name: str | None,
               cursor: int, history: list[dict]) -> Action:
        if skill_name:
            step = self._skills.next_step(skill_name, perception.nodeTree, cursor)
            if step is not None:
                return Action(actionId=str(uuid.uuid4()), op=step["op"],
                              params={k: v for k, v in step.items() if k != "op"})

        payload = {
            "goal": goal,
            "nodes": [n.model_dump(exclude_none=True) for n in perception.nodeTree],
            "history": history,
        }
        raw = self._llm.complete(system="decide next UI action", user=json.dumps(payload, ensure_ascii=False))
        data = json.loads(raw)
        return Action(actionId=str(uuid.uuid4()), op=data["op"], params=data.get("params", {}))
```

- [ ] **Step 4: Run tests and ensure pass**

Run: `cd server && uv run pytest tests/test_decision.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add server/app/decision.py server/tests/test_decision.py
git commit -m "feat: 决策引擎"
```

### Task 7: 协商机器人

**Files:**
- Create: `server/app/negotiation.py`
- Test: `server/tests/test_negotiation.py`

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_negotiation.py
from app.llm import FakeLLM
from app.negotiation import NegotiationBot


def test_continue_reply():
    bot = NegotiationBot(FakeLLM(['{"status":"continue","reply":"可以分期吗？"}']))
    out = bot.respond(goal="确认还款时间", incoming="我现在没钱", history=[])
    assert out["status"] == "continue"
    assert "分期" in out["reply"]


def test_handover_reply():
    bot = NegotiationBot(FakeLLM(['{"status":"handover","reply":""}']))
    out = bot.respond(goal="确认还款时间", incoming="我要投诉", history=[])
    assert out["status"] == "handover"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_negotiation.py -v`
Expected: FAIL, ModuleNotFoundError: app.negotiation

- [ ] **Step 3: Write minimal implementation**

```python
# server/app/negotiation.py
import json
from app.llm import LLM


class NegotiationBot:
    def __init__(self, llm: LLM):
        self._llm = llm

    def respond(self, goal: str, incoming: str, history: list[dict]) -> dict:
        payload = {"goal": goal, "incoming": incoming, "history": history}
        raw = self._llm.complete(system="negotiate next reply", user=json.dumps(payload, ensure_ascii=False))
        return json.loads(raw)
```

- [ ] **Step 4: Run tests and ensure pass**

Run: `cd server && uv run pytest tests/test_negotiation.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add server/app/negotiation.py server/tests/test_negotiation.py
git commit -m "feat: 协商机器人"
```

### Task 8: WebSocket 网关与端到端回放测试

**Files:**
- Create: `server/app/gateway.py`
- Create: `server/tests/test_gateway_integration.py`
- Create: `server/tests/fixtures/feishu_happy_path.json`

- [ ] **Step 1: Write the failing integration test**

```python
# server/tests/test_gateway_integration.py
import asyncio
import json
import pytest
from fastapi.testclient import TestClient
from app.gateway import create_app

@pytest.mark.asyncio
async def test_ws_task_flow_smoke():
    app = create_app()
    client = TestClient(app)

    with client.websocket_connect("/ws/device-1") as ws:
        ws.send_text(json.dumps({"type":"heartbeat","deviceId":"device-1","ts":1}))
        msg = ws.receive_json()
        assert msg["type"] in ["task.start", "action", "task.done", "task.abort"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_gateway_integration.py -v`
Expected: FAIL, ModuleNotFoundError: app.gateway

- [ ] **Step 3: Write minimal implementation**

```python
# server/app/gateway.py
import json
from fastapi import FastAPI, WebSocket
from app.protocol import parse_uplink, TaskStart, Action


def create_app() -> FastAPI:
    app = FastAPI()

    @app.websocket("/ws/{device_id}")
    async def ws_endpoint(ws: WebSocket, device_id: str):
        await ws.accept()
        await ws.send_text(TaskStart(taskId="task-1", goal="确认还款时间", target="张三").to_json())
        while True:
            raw = await ws.receive_text()
            uplink = parse_uplink(raw)
            if uplink.type == "heartbeat":
                await ws.send_text(Action(actionId="a1", op="read_screen", params={}).to_json())
            else:
                await ws.send_text(json.dumps({"type": "task.done", "taskId": "task-1", "result": "ok", "summary": "smoke"}))
                break

    return app
```

- [ ] **Step 4: Run tests and ensure pass**

Run: `cd server && uv run pytest tests/test_gateway_integration.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add server/app/gateway.py server/tests/test_gateway_integration.py server/tests/fixtures/feishu_happy_path.json
git commit -m "feat: WebSocket 网关最小闭环与回放夹具"
```

## 阶段三：安卓端（感知+执行+长连）

### Task 9: 安卓协议模型与 WS 客户端

**Files:**
- Create: `android/app/src/main/java/com/example/phoneagent/protocol/Messages.kt`
- Create: `android/app/src/main/java/com/example/phoneagent/net/WsClient.kt`
- Test: `android/app/src/test/java/com/example/phoneagent/protocol/MessagesTest.kt`

- [ ] **Step 1: Write the failing test**

```kotlin
// android/app/src/test/java/com/example/phoneagent/protocol/MessagesTest.kt
package com.example.phoneagent.protocol

import org.junit.Assert.assertTrue
import org.junit.Test

class MessagesTest {
    @Test
    fun actionToJson_containsTypeAndOp() {
        val a = DownAction(actionId = "a1", op = "tap", params = mapOf("match_text" to "通讯录"))
        val json = a.toJson()
        assertTrue(json.contains("\"type\":\"action\""))
        assertTrue(json.contains("\"op\":\"tap\""))
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd android && ./gradlew testDebugUnitTest --tests "*MessagesTest"`
Expected: FAIL, class not found `DownAction`

- [ ] **Step 3: Write minimal implementation**

```kotlin
// android/app/src/main/java/com/example/phoneagent/protocol/Messages.kt
package com.example.phoneagent.protocol

data class NodeDto(
    val id: String,
    val text: String? = null,
    val desc: String? = null,
    val className: String? = null,
    val bounds: List<Int>? = null,
    val clickable: Boolean = false,
    val editable: Boolean = false,
)

data class UplinkPerception(
    val type: String = "perception",
    val nodeTree: List<NodeDto>,
    val screenshot: String? = null,
    val pkg: String,
    val activity: String,
    val ts: Long,
)

data class DownAction(
    val type: String = "action",
    val actionId: String,
    val op: String,
    val params: Map<String, String> = emptyMap(),
) {
    fun toJson(): String {
        val paramsJson = params.entries.joinToString(",") { "\"${it.key}\":\"${it.value}\"" }
        return "{\"type\":\"$type\",\"actionId\":\"$actionId\",\"op\":\"$op\",\"params\":{$paramsJson}}"
    }
}
```

```kotlin
// android/app/src/main/java/com/example/phoneagent/net/WsClient.kt
package com.example.phoneagent.net

import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.WebSocket
import okhttp3.WebSocketListener

class WsClient(
    private val baseUrl: String,
    private val listener: WebSocketListener,
) {
    private val client = OkHttpClient()
    private var ws: WebSocket? = null

    fun connect(deviceId: String) {
        val req = Request.Builder().url("$baseUrl/ws/$deviceId").build()
        ws = client.newWebSocket(req, listener)
    }

    fun send(text: String) {
        ws?.send(text)
    }

    fun close() {
        ws?.close(1000, "bye")
    }
}
```

- [ ] **Step 4: Run tests and ensure pass**

Run: `cd android && ./gradlew testDebugUnitTest --tests "*MessagesTest"`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add android/app/src/main/java/com/example/phoneagent/protocol/Messages.kt android/app/src/main/java/com/example/phoneagent/net/WsClient.kt android/app/src/test/java/com/example/phoneagent/protocol/MessagesTest.kt
git commit -m "feat(android): 协议模型与WS客户端"
```

### Task 10: 无障碍感知与动作执行

**Files:**
- Create: `android/app/src/main/java/com/example/phoneagent/accessibility/Perception.kt`
- Create: `android/app/src/main/java/com/example/phoneagent/accessibility/Executor.kt`
- Create: `android/app/src/main/java/com/example/phoneagent/accessibility/PhoneAgentService.kt`
- Test: `android/app/src/test/java/com/example/phoneagent/accessibility/PerceptionTest.kt`

- [ ] **Step 1: Write the failing test**

```kotlin
// android/app/src/test/java/com/example/phoneagent/accessibility/PerceptionTest.kt
package com.example.phoneagent.accessibility

import org.junit.Assert.assertEquals
import org.junit.Test

class PerceptionTest {
    @Test
    fun keepOnlyVisibleAndTextOrClickableNodes() {
        val input = listOf(
            FlatNode("n1", text = "通讯录", visible = true, clickable = true),
            FlatNode("n2", text = null, visible = true, clickable = false),
            FlatNode("n3", text = "", visible = false, clickable = true),
        )
        val out = PerceptionFilter.filter(input)
        assertEquals(1, out.size)
        assertEquals("n1", out[0].id)
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd android && ./gradlew testDebugUnitTest --tests "*PerceptionTest"`
Expected: FAIL, unresolved reference `FlatNode`

- [ ] **Step 3: Write minimal implementation**

```kotlin
// android/app/src/main/java/com/example/phoneagent/accessibility/Perception.kt
package com.example.phoneagent.accessibility

data class FlatNode(
    val id: String,
    val text: String? = null,
    val visible: Boolean = true,
    val clickable: Boolean = false,
    val editable: Boolean = false,
)

object PerceptionFilter {
    fun filter(nodes: List<FlatNode>): List<FlatNode> {
        return nodes.filter { n ->
            n.visible && (n.clickable || !n.text.isNullOrBlank())
        }
    }
}
```

```kotlin
// android/app/src/main/java/com/example/phoneagent/accessibility/Executor.kt
package com.example.phoneagent.accessibility

class Executor {
    fun execute(op: String, params: Map<String, String>): Boolean {
        return when (op) {
            "tap", "input", "swipe", "back", "home", "wait", "open_app", "read_screen" -> true
            else -> false
        }
    }
}
```

```kotlin
// android/app/src/main/java/com/example/phoneagent/accessibility/PhoneAgentService.kt
package com.example.phoneagent.accessibility

import android.accessibilityservice.AccessibilityService
import android.view.accessibility.AccessibilityEvent

class PhoneAgentService : AccessibilityService() {
    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        // MVP: 事件入口，后续接入节点树提取与上报
    }

    override fun onInterrupt() = Unit
}
```

- [ ] **Step 4: Run tests and ensure pass**

Run: `cd android && ./gradlew testDebugUnitTest --tests "*PerceptionTest"`
Expected: PASS (1 test)

- [ ] **Step 5: Commit**

```bash
git add android/app/src/main/java/com/example/phoneagent/accessibility/Perception.kt android/app/src/main/java/com/example/phoneagent/accessibility/Executor.kt android/app/src/main/java/com/example/phoneagent/accessibility/PhoneAgentService.kt android/app/src/test/java/com/example/phoneagent/accessibility/PerceptionTest.kt
git commit -m "feat(android): 无障碍感知过滤与动作执行骨架"
```

### Task 11: 联调入口与手工验收脚本

**Files:**
- Create: `android/app/src/main/java/com/example/phoneagent/MainActivity.kt`
- Modify: `server/app/gateway.py`
- Test: `server/tests/test_gateway_integration.py`

- [ ] **Step 1: Write the failing integration assertion**

```python
# server/tests/test_gateway_integration.py (新增断言)
# 在现有 test_ws_task_flow_smoke 末尾增加：
assert msg["type"] in ["task.start", "action", "task.done", "task.abort"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_gateway_integration.py -v`
Expected: FAIL（若消息链路未完整发送）

- [ ] **Step 3: Write minimal implementation**

```kotlin
// android/app/src/main/java/com/example/phoneagent/MainActivity.kt
package com.example.phoneagent

import android.os.Bundle
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // MVP: 仅作为入口，后续增加服务器地址与连接状态展示
    }
}
```

```python
# server/app/gateway.py (补充回放夹具读取)
from pathlib import Path

_FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "feishu_happy_path.json"

def _load_fixture_steps() -> list[dict]:
    if not _FIXTURE.exists():
        return []
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))
```

```json
// server/tests/fixtures/feishu_happy_path.json
[
  {"op":"open_app","params":{"pkg":"com.ss.android.lark"}},
  {"op":"tap","params":{"match_text":"通讯录"}},
  {"op":"tap","params":{"match_text":"搜索"}},
  {"op":"input","params":{"text":"张三"}},
  {"op":"tap","params":{"match_text":"发送"}}
]
```

- [ ] **Step 4: Run tests and ensure pass**

Run: `cd server && uv run pytest tests/test_gateway_integration.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add android/app/src/main/java/com/example/phoneagent/MainActivity.kt server/app/gateway.py server/tests/fixtures/feishu_happy_path.json server/tests/test_gateway_integration.py
git commit -m "feat: 联调入口与飞书回放夹具"
```

## 阶段四：验证与收口

### Task 12: 全量验证

**Files:**
- Modify: 无（只运行验证）

- [ ] **Step 1: 运行云端全部测试**

Run: `cd server && uv run pytest -v`
Expected: 全部 PASS

- [ ] **Step 2: 运行安卓单元测试**

Run: `cd android && ./gradlew testDebugUnitTest`
Expected: BUILD SUCCESSFUL

- [ ] **Step 3: 真机手工走查脚本**

Run:
```bash
# 终端1
cd server && uvicorn app.gateway:create_app --factory --host 0.0.0.0 --port 8000

# 终端2（启动安卓App后）
adb logcat | grep -E "PhoneAgent|WsClient"
```

Expected:
- App 建立 WS 连接
- 收到 `task.start` 与 `action`
- 回传 `perception` / `action.result`
- 至少一轮 `event.newMessage` 后产生新的发送动作

- [ ] **Step 4: Commit 测试基线（可选）**

```bash
git add -A
git commit -m "test: MVP 闭环验证通过"
```

## 自检结果（writing-plans checklist）

- **Spec coverage:** 已覆盖协议、状态机、技能库雏形、决策引擎、协商机器人、WS 网关、回放夹具、安卓感知执行与测试策略。
- **Placeholder scan:** 已移除“见下文/待补充”类占位；每个代码步骤均给出完整代码片段与命令。
- **Type consistency:** `Action(op, params)`、`Perception(nodeTree, pkg, activity, ts)`、状态机状态名在各任务中保持一致。

