# 完整飞书闭环 + 路径缓存 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 打通完整飞书场景端到端闭环（连 WS → 识别屏幕 → 滑桌面找飞书 → 打开 → 搜联系人 → 输入发送），并新增路径缓存机制减少 LLM 调用。

**Architecture:** 云端 FastAPI + WebSocket，用 Session 状态机 + DecisionEngine 驱动决策，决策优先查 SkillCache（JSON 持久化），未命中走 skills 脚本，再未命中走真实 LLM（OpenAI 兼容）。端侧 Kotlin AccessibilityService 抓节点树上报 perception、执行下发 action（真实手势），MainActivity 显示服务状态。

**Tech Stack:** Python 3.14 / FastAPI / pydantic / openai SDK / pytest；Kotlin / Android AccessibilityService / OkHttp / kotlinx.serialization / JUnit4。

---

## 文件结构总览

**云端（server/app/）**
- 新增 `skill_cache.py` — 路径缓存：get/learn/mark_miss + JSON 持久化
- 修改 `llm.py` — 新增 `RealLLM(LLM)`（OpenAI 兼容）+ `build_llm()` 工厂（env 缺失 fallback FakeLLM）
- 修改 `decision.py` — `DecisionEngine` 注入 SkillCache，decide 先查缓存
- 重写 `gateway.py` — WS 循环用 Session + DecisionEngine 驱动，done 后 learn
- 数据文件 `server/data/skill_cache.json` — 运行时生成（.gitignore）
- 依赖 `pyproject.toml` — 加 `openai`

**云端测试（server/tests/）**
- 新增 `test_skill_cache.py`
- 新增 `test_real_llm.py`
- 修改 `test_decision.py` — 补缓存路径用例
- 修改 `test_gateway_integration.py` — 补全链路回放

**端侧（android/app/src/main/java/com/example/phoneagent/）**
- 修改 `protocol/Messages.kt` — NodeDto 补 desc/bounds/className；引入 kotlinx.serialization
- 修改 `net/WsClient.kt` — WebSocketListener 回调解析下行
- 重写 `accessibility/Executor.kt` — 真实手势/输入/全局动作
- 重写 `accessibility/PhoneAgentService.kt` — 抓树上报 + 执行 action
- 修改 `MainActivity.kt` — onResume 刷新服务状态
- 修改 `build.gradle.kts` + `libs.versions.toml` — 加 kotlin plugin + serialization

**端侧测试（android/app/src/test/）**
- 修改 `protocol/MessagesTest.kt` — 序列化/反序列化断言

---

## Task 1: 云端 SkillCache（路径缓存核心）

**Files:**
- Create: `server/app/skill_cache.py`
- Test: `server/tests/test_skill_cache.py`

- [ ] **Step 1: Write the failing test**

```python
# server/tests/test_skill_cache.py
import json
from pathlib import Path

from app.skill_cache import SkillCache


def _steps():
    return [
        {"op": "tap", "params": {"match_text": "搜索"}},
        {"op": "input", "params": {"text": "$MESSAGE_TARGET"}},
        {"op": "tap", "params": {"match_text": "发送"}},
    ]


def test_get_returns_none_when_empty(tmp_path):
    cache = SkillCache(tmp_path / "c.json")
    assert cache.get("发飞书消息", "com.ss.android.lark") is None


def test_learn_then_get_roundtrip(tmp_path):
    cache = SkillCache(tmp_path / "c.json")
    cache.learn("发飞书消息", "com.ss.android.lark", _steps())

    hit = cache.get("发飞书消息", "com.ss.android.lark")
    assert hit is not None
    assert hit["steps"] == _steps()
    assert hit["hits"] == 0


def test_learn_persists_to_disk(tmp_path):
    path = tmp_path / "c.json"
    SkillCache(path).learn("发飞书消息", "launcher", _steps())

    data = json.loads(Path(path).read_text(encoding="utf-8"))
    assert "发飞书消息|launcher" in data
    assert data["发飞书消息|launcher"]["steps"] == _steps()


def test_reload_from_existing_file(tmp_path):
    path = tmp_path / "c.json"
    SkillCache(path).learn("g", "ctx", _steps())

    reloaded = SkillCache(path)
    assert reloaded.get("g", "ctx")["steps"] == _steps()


def test_mark_miss_removes_entry(tmp_path):
    cache = SkillCache(tmp_path / "c.json")
    cache.learn("g", "ctx", _steps())
    cache.mark_miss("g", "ctx", cursor=1)
    assert cache.get("g", "ctx") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_skill_cache.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.skill_cache'`

- [ ] **Step 3: Write minimal implementation**

```python
# server/app/skill_cache.py
from __future__ import annotations

import json
import time
from pathlib import Path


def _make_key(goal: str, context: str) -> str:
    return f"{goal}|{context}"


class SkillCache:
    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._data: dict[str, dict] = {}
        if self._path.exists():
            self._data = json.loads(self._path.read_text(encoding="utf-8"))

    def get(self, goal: str, context: str) -> dict | None:
        return self._data.get(_make_key(goal, context))

    def learn(self, goal: str, context: str, steps: list[dict]) -> None:
        key = _make_key(goal, context)
        now = int(time.time())
        existing = self._data.get(key)
        self._data[key] = {
            "key": key,
            "steps": steps,
            "hits": existing["hits"] if existing else 0,
            "created_ts": existing["created_ts"] if existing else now,
            "updated_ts": now,
        }
        self._flush()

    def mark_miss(self, goal: str, context: str, cursor: int) -> None:
        # 某步失效：整条失效等待重新学习（MVP 策略）
        self._data.pop(_make_key(goal, context), None)
        self._flush()

    def _flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_skill_cache.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add server/app/skill_cache.py server/tests/test_skill_cache.py
git commit -m "feat(server): add SkillCache with JSON persistence"
```

---

## Task 2: 云端 RealLLM（OpenAI 兼容）+ build_llm 工厂

**Files:**
- Modify: `server/pyproject.toml`（加 openai 依赖）
- Modify: `server/app/llm.py`
- Test: `server/tests/test_real_llm.py`

- [ ] **Step 1: 加依赖并安装**

编辑 `server/pyproject.toml`，在 `dependencies` 列表加入 `"openai"`：

```toml
dependencies = [
  "fastapi",
  "uvicorn",
  "websockets",
  "pydantic",
  "openai",
]
```

Run: `cd server && uv sync`
Expected: 安装 openai 成功

- [ ] **Step 2: Write the failing test**

```python
# server/tests/test_real_llm.py
import pytest

from app.llm import FakeLLM, RealLLM, build_llm


class _FakeChoice:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})()


class _FakeResp:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeClient:
    def __init__(self, content):
        self._content = content
        self.captured = {}

        parent = self

        class _Completions:
            def create(self, **kwargs):
                parent.captured = kwargs
                return _FakeResp(parent._content)

        self.chat = type("C", (), {"completions": _Completions()})()


def test_real_llm_sends_prompt_and_returns_content():
    client = _FakeClient('{"op":"tap","params":{"match_text":"搜索"}}')
    llm = RealLLM(client=client, model="gpt-4o-mini")

    out = llm.complete(system="sys", user="usr")

    assert out == '{"op":"tap","params":{"match_text":"搜索"}}'
    assert client.captured["model"] == "gpt-4o-mini"
    msgs = client.captured["messages"]
    assert msgs[0] == {"role": "system", "content": "sys"}
    assert msgs[1] == {"role": "user", "content": "usr"}


def test_build_llm_falls_back_to_fake_when_no_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    llm = build_llm()
    assert isinstance(llm, FakeLLM)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_real_llm.py -v`
Expected: FAIL with `ImportError: cannot import name 'RealLLM'`

- [ ] **Step 4: Write minimal implementation**

在 `server/app/llm.py` 末尾追加（保留现有 `LLM` / `FakeLLM`）：

```python
import os


class RealLLM(LLM):
    def __init__(self, client, model: str):
        self._client = client
        self._model = model

    def complete(self, system: str, user: str, image_b64: str | None = None) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,
        )
        return resp.choices[0].message.content


def build_llm() -> LLM:
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        return FakeLLM(['{"op":"read_screen","params":{}}'])

    from openai import OpenAI

    base_url = os.environ.get("LLM_BASE_URL")
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    client = OpenAI(api_key=api_key, base_url=base_url)
    return RealLLM(client=client, model=model)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_real_llm.py tests/test_llm.py -v`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add server/pyproject.toml server/uv.lock server/app/llm.py server/tests/test_real_llm.py
git commit -m "feat(server): add RealLLM (OpenAI-compatible) and build_llm factory"
```

---

## Task 3: DecisionEngine 集成 SkillCache

**Files:**
- Modify: `server/app/decision.py`
- Test: `server/tests/test_decision.py`（追加用例）

- [ ] **Step 1: Write the failing test**（追加到 test_decision.py 末尾）

```python
from app.skill_cache import SkillCache


def test_cache_hit_returns_step_without_llm(tmp_path, monkeypatch):
    cache = SkillCache(tmp_path / "c.json")
    cache.learn("发消息", "com.ss.android.lark", [{"op": "tap", "params": {"match_text": "搜索"}}])

    llm = FakeLLM(['{"op":"back","params":{}}'])

    def _fail(system, user, image_b64=None):
        raise AssertionError("LLM must not be called on cache hit")

    monkeypatch.setattr(llm, "complete", _fail)
    engine = DecisionEngine(llm=llm, skills=SkillLibrary(), cache=cache)
    p = _perc([Node(id="n1", text="搜索", clickable=True)])

    action = engine.decide(goal="发消息", perception=p, skill_name=None, cursor=0, history=[])

    assert action.op == "tap"
    assert action.params == {"match_text": "搜索"}


def test_cache_miss_when_node_not_matchable_falls_through(tmp_path):
    cache = SkillCache(tmp_path / "c.json")
    cache.learn("发消息", "com.ss.android.lark", [{"op": "tap", "params": {"match_text": "搜索"}}])

    llm = FakeLLM(['{"op":"back","params":{}}'])
    engine = DecisionEngine(llm=llm, skills=SkillLibrary(), cache=cache)
    p = _perc([Node(id="n1", text="首页")])  # 无“搜索”节点，缓存步无法重定位

    action = engine.decide(goal="发消息", perception=p, skill_name=None, cursor=0, history=[])

    assert action.op == "back"  # 回退到 LLM
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_decision.py -v`
Expected: FAIL — `DecisionEngine.__init__() got an unexpected keyword argument 'cache'`

- [ ] **Step 3: Write minimal implementation**

改写 `server/app/decision.py`（保留原 skills/LLM 逻辑，新增 cache 优先）：

```python
import json
import uuid

from app.llm import LLM
from app.protocol import Action, Perception
from app.skills import SkillLibrary
from app.skill_cache import SkillCache


class DecisionEngine:
    def __init__(self, llm: LLM, skills: SkillLibrary, cache: SkillCache | None = None):
        self._llm = llm
        self._skills = skills
        self._cache = cache

    def _cache_step(self, goal, perception, cursor):
        if self._cache is None:
            return None
        entry = self._cache.get(goal, perception.pkg)
        if entry is None or cursor >= len(entry["steps"]):
            return None
        step = entry["steps"][cursor]
        match_text = step.get("params", {}).get("match_text", "")
        if match_text and not any(match_text in (n.text or "") for n in perception.nodeTree):
            return None  # 无法重定位 → 回退
        return step

    def decide(self, goal, perception, skill_name, cursor, history):
        step = self._cache_step(goal, perception, cursor)
        if step is not None:
            return Action(actionId=str(uuid.uuid4()), op=step["op"], params=step.get("params", {}))

        if skill_name:
            step = self._skills.next_step(skill_name, perception.nodeTree, cursor)
            if step is not None:
                params = {k: v for k, v in step.items() if k != "op"}
                return Action(actionId=str(uuid.uuid4()), op=step["op"], params=params)

        payload = {
            "goal": goal,
            "nodes": [n.model_dump(exclude_none=True) for n in perception.nodeTree],
            "history": history,
        }
        raw = self._llm.complete(system="decide next UI action", user=json.dumps(payload, ensure_ascii=False))
        data = json.loads(raw)
        return Action(actionId=str(uuid.uuid4()), op=data["op"], params=data.get("params", {}))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd server && uv run pytest tests/test_decision.py -v`
Expected: PASS（原有 2 + 新增 2）

- [ ] **Step 5: Commit**

```bash
git add server/app/decision.py server/tests/test_decision.py
git commit -m "feat(server): DecisionEngine consults SkillCache before skills/LLM"
```

---

## Task 4：重写 gateway 驱动 Session + DecisionEngine + cache.learn

**目标**：把当前硬编码下发 read_screen/done 的 `gateway.py` 重写为真实闭环调度器：每条连接建立一个 `Session` + 一个 `DecisionEngine`（注入 `build_llm()` / `SkillLibrary` / `SkillCache`）；收 perception → `decide` → 下发 action；收 action.result → 记录并推进 cursor；成功跑到 `done` 时 `cache.learn(applied_steps)` 写缓存；budget 耗尽 / abort 时收尾。

**兼容性约束**：`test_gateway_integration.py` 两个既有测试必须继续通过——
1. `test_gateway_replay_heartbeat_returns_expected_message_type`：收到 heartbeat 仍需回一个合法下行（这里回 `read_screen` action）。
2. `test_load_fixture_steps_returns_action_sequence`：`_load_fixture_steps()` 函数签名与行为不变，保留。

- [ ] **Step 1: 写失败测试**

新增 `server/tests/test_gateway_loop.py`：

```python
import json

from fastapi.testclient import TestClient

from app.gateway import create_app


def _perception(nodes, pkg="", activity="", ts=1):
    return json.dumps(
        {
            "type": "perception",
            "nodeTree": nodes,
            "pkg": pkg,
            "activity": activity,
            "ts": ts,
        }
    )


def _result(action_id, ok=True):
    return json.dumps(
        {"type": "action.result", "actionId": action_id, "ok": ok, "ts": 1}
    )


def test_gateway_starts_task_on_connect(monkeypatch):
    # 隔离缓存，避免污染真实 data 目录
    monkeypatch.setenv("SKILL_CACHE_PATH", "/tmp/test_gw_cache.json")
    monkeypatch.setenv("PHONEAGENT_FAKE_LLM", '["{\\"op\\":\\"done\\",\\"params\\":{}}"]')

    app = create_app()
    client = TestClient(app)
    with client.websocket_connect("/ws/device-1") as ws:
        first = ws.receive_json()

    assert first["type"] == "task.start"
    assert first["taskId"]
    assert first["goal"]


def test_gateway_perception_yields_action_then_done(monkeypatch):
    monkeypatch.setenv("SKILL_CACHE_PATH", "/tmp/test_gw_cache2.json")
    # 第一步 LLM 让点“搜索”，第二步 done
    monkeypatch.setenv(
        "PHONEAGENT_FAKE_LLM",
        json.dumps(
            [
                '{"op":"tap","params":{"match_text":"搜索"}}',
                '{"op":"done","params":{}}',
            ]
        ),
    )

    app = create_app()
    client = TestClient(app)
    nodes = [{"id": "n1", "text": "搜索", "clickable": True}]

    with client.websocket_connect("/ws/device-1") as ws:
        ws.receive_json()  # task.start
        ws.send_text(_perception(nodes, pkg="com.ss.android.lark"))
        action = ws.receive_json()
        assert action["type"] == "action"
        assert action["op"] == "tap"

        ws.send_text(_result(action["actionId"], ok=True))
        # 第二轮 perception 触发 done
        ws.send_text(_perception(nodes, pkg="com.ss.android.lark"))
        done = ws.receive_json()
        assert done["type"] == "task.done"


def test_gateway_budget_exhausted_aborts(monkeypatch):
    monkeypatch.setenv("SKILL_CACHE_PATH", "/tmp/test_gw_cache3.json")
    # 永远回一个 wait，永不 done —— 靠 max_steps 收尾
    monkeypatch.setenv("PHONEAGENT_FAKE_LLM", '["{\\"op\\":\\"wait\\",\\"params\\":{}}"]')
    monkeypatch.setenv("PHONEAGENT_MAX_STEPS", "2")

    app = create_app()
    client = TestClient(app)
    nodes = [{"id": "n1", "text": "x", "clickable": True}]

    with client.websocket_connect("/ws/device-1") as ws:
        ws.receive_json()  # task.start
        seen_abort = False
        for _ in range(5):
            ws.send_text(_perception(nodes))
            msg = ws.receive_json()
            if msg["type"] == "task.abort":
                seen_abort = True
                break
        assert seen_abort


def test_gateway_heartbeat_still_returns_action(monkeypatch):
    # 兼容旧行为：心跳回一个合法下行
    monkeypatch.setenv("SKILL_CACHE_PATH", "/tmp/test_gw_cache4.json")
    monkeypatch.setenv("PHONEAGENT_FAKE_LLM", '["{\\"op\\":\\"read_screen\\",\\"params\\":{}}"]')

    app = create_app()
    client = TestClient(app)
    heartbeat = json.dumps({"type": "heartbeat", "deviceId": "device-1", "ts": 1})
    with client.websocket_connect("/ws/device-1") as ws:
        ws.receive_json()  # task.start
        ws.send_text(heartbeat)
        msg = ws.receive_json()
        assert msg["type"] in {"action", "task.done", "task.abort"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd server && uv run pytest tests/test_gateway_loop.py -v`
Expected: FAIL（gateway 尚未接入 Session/DecisionEngine/cache）

- [ ] **Step 3: 最小实现——重写 `server/app/gateway.py`**

```python
import json
import os
import uuid
from pathlib import Path

from fastapi import FastAPI, WebSocket
from starlette.websockets import WebSocketDisconnect

from app.decision import DecisionEngine
from app.llm import FakeLLM, build_llm
from app.protocol import (
    Action,
    TaskAbort,
    TaskDone,
    TaskStart,
    parse_uplink,
)
from app.skill_cache import SkillCache
from app.skills import SkillLibrary

_FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "feishu_happy_path.json"

_DEFAULT_GOAL = "在飞书里给指定联系人发送消息"


def _load_fixture_steps() -> list[dict]:
    """保留：供 test_gateway_integration 使用。"""
    if not _FIXTURE.exists():
        return []
    return json.loads(_FIXTURE.read_text(encoding="utf-8"))


def _build_engine() -> DecisionEngine:
    """构造决策引擎；测试可用 PHONEAGENT_FAKE_LLM 注入 FakeLLM 响应序列。"""
    fake = os.getenv("PHONEAGENT_FAKE_LLM")
    llm = FakeLLM(json.loads(fake)) if fake else build_llm()
    cache = SkillCache(Path(os.getenv("SKILL_CACHE_PATH", "data/skill_cache.json")))
    return DecisionEngine(llm=llm, skills=SkillLibrary(), cache=cache)


def create_app() -> FastAPI:
    app = FastAPI()
    max_steps = int(os.getenv("PHONEAGENT_MAX_STEPS", "40"))

    @app.websocket("/ws/{device_id}")
    async def ws_gateway(websocket: WebSocket, device_id: str) -> None:
        await websocket.accept()
        from app.session import Session, State

        engine = _build_engine()
        session = Session(
            task_id=f"task-{uuid.uuid4().hex[:8]}",
            goal=_DEFAULT_GOAL,
            target=device_id,
            max_steps=max_steps,
        )
        cursor = 0
        history: list[dict] = []
        applied_steps: list[dict] = []  # 成功推进的语义步序列，用于 learn
        last_pkg = ""

        await websocket.send_text(
            TaskStart(taskId=session.task_id, goal=session.goal, target=device_id).to_json()
        )

        while True:
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                break

            try:
                uplink = parse_uplink(raw)
            except ValueError:
                await websocket.send_text(
                    TaskAbort(taskId=session.task_id, reason="invalid_uplink").to_json()
                )
                break

            # action.result：记录并推进 cursor，不直接下发
            if uplink.type == "action.result":
                history.append({"actionId": uplink.actionId, "ok": uplink.ok})
                if uplink.ok:
                    cursor += 1
                continue

            # heartbeat：回一个安全动作（读屏），兼容旧测试
            if uplink.type == "heartbeat":
                await websocket.send_text(
                    Action(actionId=str(uuid.uuid4()), op="read_screen", params={}).to_json()
                )
                continue

            # 仅 perception 触发决策
            if uplink.type != "perception":
                continue

            if session.budget_exhausted():
                await websocket.send_text(
                    TaskAbort(taskId=session.task_id, reason="budget_exhausted").to_json()
                )
                break

            last_pkg = uplink.pkg or last_pkg
            action = engine.decide(
                goal=session.goal,
                perception=uplink,
                skill_name=None,
                cursor=cursor,
                history=history,
            )
            session.record_step()

            if action.op == "done":
                # 成功闭环：学习本次走过的语义步序列
                if applied_steps:
                    engine._cache.learn(session.goal, last_pkg, applied_steps)
                await websocket.send_text(
                    TaskDone(taskId=session.task_id, result="ok", summary="task completed").to_json()
                )
                break

            if action.op == "abort":
                await websocket.send_text(
                    TaskAbort(taskId=session.task_id, reason="llm_abort").to_json()
                )
                break

            # 记录语义步（不含绝对坐标），用于命中缓存学习
            applied_steps.append({"op": action.op, "params": action.params})
            await websocket.send_text(action.to_json())

    return app
```

> 说明：`engine._cache` 为 `DecisionEngine` 持有的 `SkillCache`（Task 3 已加 `cache` 参数并存为 `self._cache`）。gateway 直接复用同一实例调 `learn`，避免二次构造。

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd server && uv run pytest tests/test_gateway_loop.py tests/test_gateway_integration.py -v`
Expected: PASS（新增 5 + 旧 2 全绿；旧心跳/夹具测试兼容）

- [ ] **Step 5: Commit**

```bash
git add server/app/gateway.py server/tests/test_gateway_loop.py
git commit -m "feat(server): rewrite gateway to drive Session+DecisionEngine with cache learning"
```

---

## Task 5：端侧引入 kotlinx.serialization 并重写 Messages.kt

**目标**：用 `kotlinx.serialization` 替代手写 JSON，`NodeDto` 补齐 `desc/bounds/className`，`DownAction.params` 从 `Map<String,String>` 放宽为可解析下行任意标量（这里保持 `Map<String, String>` 以匹配 Executor 消费方式，`swipe` 坐标以字符串传入），并提供 `UplinkPerception` 的编码与 `DownAction` 的解码工具。

**现状关键点**：
- `build.gradle.kts` 仅 `alias(libs.plugins.android.application)`，**未显式应用 kotlin-android**，也无 serialization plugin。
- `libs.versions.toml` 已有 `kotlin-android` plugin 定义，但**无** serialization plugin 与 kotlinx-serialization-json 库。

- [ ] **Step 1: 写失败测试——重写 `MessagesTest.kt`**

`android/app/src/test/java/com/example/phoneagent/protocol/MessagesTest.kt`：

```kotlin
package com.example.phoneagent.protocol

import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class MessagesTest {

    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }

    @Test
    fun perception_serializes_with_node_fields() {
        val p = UplinkPerception(
            nodeTree = listOf(
                NodeDto(
                    id = "n1",
                    text = "搜索",
                    desc = "search",
                    className = "android.widget.TextView",
                    bounds = listOf(0, 0, 100, 50),
                    clickable = true,
                    editable = false,
                )
            ),
            pkg = "com.ss.android.lark",
            activity = ".MainActivity",
            ts = 123L,
        )
        val out = json.encodeToString(p)

        assertTrue(out.contains("\"type\":\"perception\""))
        assertTrue(out.contains("\"pkg\":\"com.ss.android.lark\""))
        assertTrue(out.contains("\"bounds\":[0,0,100,50]"))
        assertTrue(out.contains("\"desc\":\"search\""))
    }

    @Test
    fun action_deserializes_from_downlink_json() {
        val raw = """{"type":"action","actionId":"a1","op":"tap","params":{"match_text":"搜索"}}"""
        val action = json.decodeFromString<DownAction>(raw)

        assertEquals("a1", action.actionId)
        assertEquals("tap", action.op)
        assertEquals("搜索", action.params["match_text"])
    }

    @Test
    fun action_deserializes_empty_params() {
        val raw = """{"type":"action","actionId":"a2","op":"read_screen","params":{}}"""
        val action = json.decodeFromString<DownAction>(raw)

        assertEquals("read_screen", action.op)
        assertTrue(action.params.isEmpty())
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd android && ./gradlew :app:testDebugUnitTest --tests "com.example.phoneagent.protocol.MessagesTest"`
Expected: FAIL（无 serialization 依赖 / NodeDto 未加注解 / 编译��败）

- [ ] **Step 3: 最小实现**

**3a. `android/gradle/libs.versions.toml` 追加 serialization plugin 与库：**

```toml
[versions]
# ...existing...
kotlinxSerialization = "1.7.3"

[libraries]
# ...existing...
kotlinx-serialization-json = { group = "org.jetbrains.kotlinx", name = "kotlinx-serialization-json", version.ref = "kotlinxSerialization" }

[plugins]
# ...existing android-application / kotlin-android...
kotlin-serialization = { id = "org.jetbrains.kotlin.plugin.serialization", version.ref = "kotlin" }
```

**3b. `android/app/build.gradle.kts` 应用 plugin + 加依赖：**

```kotlin
plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.serialization)
}

// android { ... } 保持不变

dependencies {
    implementation(libs.appcompat)
    implementation(libs.okhttp)
    implementation(libs.kotlinx.serialization.json)

    testImplementation(libs.junit)
}
```

> 注：AGP 9 虽内置 Kotlin 支持，但显式应用 `kotlin-android` 可确保 serialization 编译器插件挂载稳定。

**3c. 重写 `android/app/src/main/java/com/example/phoneagent/protocol/Messages.kt`：**

```kotlin
package com.example.phoneagent.protocol

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class NodeDto(
    val id: String,
    val text: String? = null,
    val desc: String? = null,
    val className: String? = null,
    val bounds: List<Int>? = null,
    val clickable: Boolean = false,
    val editable: Boolean = false,
)

@Serializable
data class UplinkPerception(
    val type: String = "perception",
    val nodeTree: List<NodeDto>,
    val screenshot: String? = null,
    val pkg: String,
    val activity: String,
    val ts: Long,
)

@Serializable
data class UplinkActionResult(
    val type: String = "action.result",
    val actionId: String,
    val ok: Boolean,
    val error: String? = null,
    val ts: Long = 0,
)

@Serializable
data class UplinkHeartbeat(
    val type: String = "heartbeat",
    val deviceId: String,
    val ts: Long = 0,
)

@Serializable
data class DownAction(
    val type: String = "action",
    val actionId: String,
    val op: String,
    val params: Map<String, String> = emptyMap(),
)

@Serializable
data class DownTaskStart(
    val type: String = "task.start",
    val taskId: String,
    val goal: String,
    val target: String,
)

@Serializable
data class DownTaskDone(
    val type: String = "task.done",
    val taskId: String,
    val result: String,
    val summary: String = "",
)

@Serializable
data class DownTaskAbort(
    val type: String = "task.abort",
    val taskId: String,
    val reason: String,
)
```

> 手写的 `DownAction.toJson()` 被移除；序列化统一交给 `Json`（在 WsClient/Service 中持有单例 `Json { ignoreUnknownKeys = true }`）。下行只需 `type` 字段做分发，故 WsClient 先解 `type` 再按需 `decodeFromString<DownAction>`。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd android && ./gradlew :app:testDebugUnitTest --tests "com.example.phoneagent.protocol.MessagesTest"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add android/gradle/libs.versions.toml android/app/build.gradle.kts \
        android/app/src/main/java/com/example/phoneagent/protocol/Messages.kt \
        android/app/src/test/java/com/example/phoneagent/protocol/MessagesTest.kt
git commit -m "feat(android): adopt kotlinx.serialization for protocol messages"
```

---

## Task 6：WsClient 增强——内部 WebSocketListener + 下行回调分发

**目标**：`WsClient` 不再要求调用方传入 `WebSocketListener`，改为内部持有一个 Listener，`onMessage` 收到文本后解析 `type` 字段，分发到三个可选回调：`onTaskStart` / `onAction` / `onTaskEnd`（done/abort 合并）。同时暴露 `sendPerception` / `sendActionResult` 便捷方法。构造只需 `baseUrl`。

- [ ] **Step 1: 写失败测试**

新增 `android/app/src/test/java/com/example/phoneagent/net/WsDispatchTest.kt`（只测**下行分发纯逻辑**，不起真实连接——把分发逻辑抽到可单测的 `WsDispatcher`）：

```kotlin
package com.example.phoneagent.net

import com.example.phoneagent.protocol.DownAction
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class WsDispatchTest {

    @Test
    fun dispatch_action_invokes_action_callback() {
        var gotAction: DownAction? = null
        val d = WsDispatcher(
            onTaskStart = { _, _ -> },
            onAction = { gotAction = it },
            onTaskEnd = { _ -> },
        )
        d.dispatch("""{"type":"action","actionId":"a1","op":"tap","params":{"match_text":"搜索"}}""")

        assertEquals("a1", gotAction?.actionId)
        assertEquals("搜索", gotAction?.params?.get("match_text"))
    }

    @Test
    fun dispatch_task_start_invokes_start_callback() {
        var goal: String? = null
        val d = WsDispatcher(
            onTaskStart = { g, _ -> goal = g },
            onAction = { },
            onTaskEnd = { },
        )
        d.dispatch("""{"type":"task.start","taskId":"t1","goal":"发消息","target":"dev"}""")
        assertEquals("发消息", goal)
    }

    @Test
    fun dispatch_task_done_invokes_end_callback() {
        var reason: String? = null
        val d = WsDispatcher(
            onTaskStart = { _, _ -> },
            onAction = { },
            onTaskEnd = { reason = it },
        )
        d.dispatch("""{"type":"task.done","taskId":"t1","result":"ok","summary":"done"}""")
        assertEquals("ok", reason)
    }

    @Test
    fun dispatch_unknown_type_is_ignored() {
        var touched = false
        val d = WsDispatcher(
            onTaskStart = { _, _ -> touched = true },
            onAction = { touched = true },
            onTaskEnd = { touched = true },
        )
        d.dispatch("""{"type":"event.unknown"}""")
        assertEquals(false, touched)
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd android && ./gradlew :app:testDebugUnitTest --tests "com.example.phoneagent.net.WsDispatchTest"`
Expected: FAIL（`WsDispatcher` 不存在）

- [ ] **Step 3: 最小实现**

**3a. 新增 `android/app/src/main/java/com/example/phoneagent/net/WsDispatcher.kt`：**

```kotlin
package com.example.phoneagent.net

import com.example.phoneagent.protocol.DownAction
import com.example.phoneagent.protocol.DownTaskDone
import com.example.phoneagent.protocol.DownTaskStart
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive

/**
 * 下行消息分发器：按 type 字段路由到回调。抽出为独立类以便纯单测。
 * onTaskEnd 的参数：done -> result，abort -> "abort:<reason>"。
 */
class WsDispatcher(
    private val onTaskStart: (goal: String, taskId: String) -> Unit,
    private val onAction: (DownAction) -> Unit,
    private val onTaskEnd: (reason: String) -> Unit,
) {
    private val json = Json { ignoreUnknownKeys = true }

    fun dispatch(text: String) {
        val type = runCatching {
            json.parseToJsonElement(text).jsonObject["type"]?.jsonPrimitive?.content
        }.getOrNull() ?: return

        when (type) {
            "task.start" -> {
                val m = json.decodeFromString<DownTaskStart>(text)
                onTaskStart(m.goal, m.taskId)
            }
            "action" -> onAction(json.decodeFromString<DownAction>(text))
            "task.done" -> {
                val m = json.decodeFromString<DownTaskDone>(text)
                onTaskEnd(m.result)
            }
            "task.abort" -> onTaskEnd("abort")
            else -> Unit
        }
    }
}
```

**3b. 重写 `android/app/src/main/java/com/example/phoneagent/net/WsClient.kt`：**

```kotlin
package com.example.phoneagent.net

import com.example.phoneagent.protocol.DownAction
import com.example.phoneagent.protocol.UplinkActionResult
import com.example.phoneagent.protocol.UplinkPerception
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener

class WsClient(
    private val baseUrl: String,
    onTaskStart: (goal: String, taskId: String) -> Unit,
    onAction: (DownAction) -> Unit,
    onTaskEnd: (reason: String) -> Unit,
) {
    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }
    private val client = OkHttpClient()
    private var ws: WebSocket? = null
    private val dispatcher = WsDispatcher(onTaskStart, onAction, onTaskEnd)

    private val listener = object : WebSocketListener() {
        override fun onMessage(webSocket: WebSocket, text: String) {
            dispatcher.dispatch(text)
        }

        override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
            // 连接失败：交由上层通过重连策略处理（MVP 暂仅记录）
        }
    }

    fun connect(deviceId: String) {
        val req = Request.Builder().url("$baseUrl/ws/$deviceId").build()
        ws = client.newWebSocket(req, listener)
    }

    fun sendPerception(p: UplinkPerception) {
        ws?.send(json.encodeToString(p))
    }

    fun sendActionResult(actionId: String, ok: Boolean, error: String? = null) {
        ws?.send(json.encodeToString(UplinkActionResult(actionId = actionId, ok = ok, error = error)))
    }

    fun close() {
        ws?.close(1000, "bye")
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd android && ./gradlew :app:testDebugUnitTest --tests "com.example.phoneagent.net.WsDispatchTest"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add android/app/src/main/java/com/example/phoneagent/net/WsDispatcher.kt \
        android/app/src/main/java/com/example/phoneagent/net/WsClient.kt \
        android/app/src/test/java/com/example/phoneagent/net/WsDispatchTest.kt
git commit -m "feat(android): WsClient internal listener + downlink dispatcher"
```

---

## Task 7：Executor 真实实现——手势/输入/导航/启动

**目标**：`Executor` 从"永远返回 true"改为真实执行动作。构造需注入 `AccessibilityService`（提供 `dispatchGesture` / `performGlobalAction` / `rootInActiveWindow`）与 `Context`（`packageManager`）。支持：
- `tap`：按`match_text` 在当前树找可点节点 → 取 bounds 中心 → `dispatchGesture` 单击；
- `input`：找 editable 节点 → `ACTION_SET_TEXT` 填 `params["text"]`；
- `back` / `home`：`performGlobalAction`；
- `swipe`：`params` 提供 `x1,y1,x2,y2`（字符串）→ `dispatchGesture` 划动；缺省用屏幕中部上滑找图标；
- `open_app`：`params["pkg"]` → `packageManager.getLaunchIntentForPackage` 启动；
- `read_screen` / `wait`：no-op 返回 true（读屏由 Service 主动抓树上报）。

**可单测部分**：坐标几何计算（bounds→中心、默认上滑向量）抽为纯函数 `GestureGeometry`，其余 framework 调用属真机集成，仅在真机联调验证。

- [ ] **Step 1: 写失败测试**

新增 `android/app/src/test/java/com/example/phoneagent/accessibility/GestureGeometryTest.kt`：

```kotlin
package com.example.phoneagent.accessibility

import org.junit.Assert.assertEquals
import org.junit.Test

class GestureGeometryTest {

    @Test
    fun center_of_bounds_is_midpoint() {
        val (cx, cy) = GestureGeometry.centerOf(listOf(0, 0, 100, 60))
        assertEquals(50f, cx, 0.001f)
        assertEquals(30f, cy, 0.001f)
    }

    @Test
    fun center_of_offset_bounds() {
        val (cx, cy) = GestureGeometry.centerOf(listOf(200, 400, 260, 460))
        assertEquals(230f, cx, 0.001f)
        assertEquals(430f, cy, 0.001f)
    }

    @Test
    fun default_swipe_up_moves_from_lower_to_upper() {
        val s = GestureGeometry.defaultSwipeUp(width = 1080, height = 1920)
        assertEquals(540f, s.startX, 0.001f)
        // 起点在下方（y 更大），终点在上方（y 更小）
        assert(s.startY > s.endY)
        assertEquals(540f, s.endX, 0.001f)
    }

    @Test
    fun parse_swipe_params_reads_four_coords() {
        val s = GestureGeometry.fromParams(
            mapOf("x1" to "100", "y1" to "800", "x2" to "100", "y2" to "200")
        )
        assertEquals(100f, s!!.startX, 0.001f)
        assertEquals(800f, s.startY, 0.001f)
        assertEquals(200f, s.endY, 0.001f)
    }

    @Test
    fun parse_swipe_params_missing_returns_null() {
        assertEquals(null, GestureGeometry.fromParams(mapOf("x1" to "100")))
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd android && ./gradlew :app:testDebugUnitTest --tests "com.example.phoneagent.accessibility.GestureGeometryTest"`
Expected: FAIL（`GestureGeometry` 不存在）

- [ ] **Step 3: 最小实现**

**3a. 新增 `android/app/src/main/java/com/example/phoneagent/accessibility/GestureGeometry.kt`：**

```kotlin
package com.example.phoneagent.accessibility

data class Swipe(
    val startX: Float,
    val startY: Float,
    val endX: Float,
    val endY: Float,
)

/** 纯几何计算，无 framework 依赖，可单测。 */
object GestureGeometry {

    /** bounds = [left, top, right, bottom] → 中心点 (cx, cy)。 */
    fun centerOf(bounds: List<Int>): Pair<Float, Float> {
        val cx = (bounds[0] + bounds[2]) / 2f
        val cy = (bounds[1] + bounds[3]) / 2f
        return cx to cy
    }

    /** 默认上滑：屏幕水平居中，从下方 80% 滑到 30%（用于桌面翻页找图标）。 */
    fun defaultSwipeUp(width: Int, height: Int): Swipe {
        val x = width / 2f
        return Swipe(startX = x, startY = height * 0.8f, endX = x, endY = height * 0.3f)
    }

    /** 从 params 读 x1,y1,x2,y2；任一缺失返回 null。 */
    fun fromParams(params: Map<String, String>): Swipe? {
        val x1 = params["x1"]?.toFloatOrNull()
        val y1 = params["y1"]?.toFloatOrNull()
        val x2 = params["x2"]?.toFloatOrNull()
        val y2 = params["y2"]?.toFloatOrNull()
        if (x1 == null || y1 == null || x2 == null || y2 == null) return null
        return Swipe(x1, y1, x2, y2)
    }
}
```

**3b. 重写 `android/app/src/main/java/com/example/phoneagent/accessibility/Executor.kt`：**

```kotlin
package com.example.phoneagent.accessibility

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.Context
import android.graphics.Path
import android.os.Bundle
import android.view.accessibility.AccessibilityNodeInfo

/**
 * 真实动作执行器。framework 集成部分仅在真机联调验证；
 * 坐标几何委托给可单测的 GestureGeometry。
 */
class Executor(
    private val service: AccessibilityService,
    private val context: Context,
) {
    fun execute(op: String, params: Map<String, String>): Boolean {
        return when (op) {
            "tap" -> tap(params["match_text"].orEmpty())
            "input" -> input(params["text"].orEmpty())
            "swipe" -> swipe(params)
            "back" -> service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK)
            "home" -> service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_HOME)
            "open_app" -> openApp(params["pkg"].orEmpty())
            "read_screen", "wait" -> true
            else -> false
        }
    }

    private fun findByText(text: String): AccessibilityNodeInfo? {
        if (text.isBlank()) return null
        val root = service.rootInActiveWindow ?: return null
        val matches = root.findAccessibilityNodeInfosByText(text)
        // 优先可点击节点，否则回退首个匹配
        return matches.firstOrNull { it.isClickable } ?: matches.firstOrNull()
    }

    private fun tap(matchText: String): Boolean {
        val node = findByText(matchText) ?: return false
        val rect = android.graphics.Rect()
        node.getBoundsInScreen(rect)
        val (cx, cy) = GestureGeometry.centerOf(listOf(rect.left, rect.top, rect.right, rect.bottom))
        return dispatchTap(cx, cy)
    }

    private fun input(text: String): Boolean {
        val root = service.rootInActiveWindow ?: return false
        val editable = findEditable(root) ?: return false
        val args = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
        }
        return editable.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
    }

    private fun findEditable(node: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        if (node.isEditable) return node
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            val found = findEditable(child)
            if (found != null) return found
        }
        return null
    }

    private fun swipe(params: Map<String, String>): Boolean {
        val metrics = context.resources.displayMetrics
        val s = GestureGeometry.fromParams(params)
            ?: GestureGeometry.defaultSwipeUp(metrics.widthPixels, metrics.heightPixels)
        val path = Path().apply {
            moveTo(s.startX, s.startY)
            lineTo(s.endX, s.endY)
        }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, 300))
            .build()
        return service.dispatchGesture(gesture, null, null)
    }

    private fun dispatchTap(x: Float, y: Float): Boolean {
        val path = Path().apply { moveTo(x, y) }
        val gesture = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, 50))
            .build()
        return service.dispatchGesture(gesture, null, null)
    }

    private fun openApp(pkg: String): Boolean {
        if (pkg.isBlank()) return false
        val intent = context.packageManager.getLaunchIntentForPackage(pkg) ?: return false
        intent.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(intent)
        return true
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd android && ./gradlew :app:testDebugUnitTest --tests "com.example.phoneagent.accessibility.GestureGeometryTest"`
Expected: PASS（几何纯函数全绿；Executor framework 部分靠真机验证）

- [ ] **Step 5: Commit**

```bash
git add android/app/src/main/java/com/example/phoneagent/accessibility/GestureGeometry.kt \
        android/app/src/main/java/com/example/phoneagent/accessibility/Executor.kt \
        android/app/src/test/java/com/example/phoneagent/accessibility/GestureGeometryTest.kt
git commit -m "feat(android): real Executor with gesture/input/nav/launch + testable geometry"
```

---

## Task 8：PhoneAgentService 串联——连 WS + 抓树上报 + 执行回传

**目标**：把 `PhoneAgentService` 从空实现改为真实闭环端点：
- `onServiceConnected`：初始化 `WsClient`（`WS_URL` 常量）与 `Executor`，注册三个下行回调，`connect(deviceId)`；收到 `onAction` 时用 `Executor` 执行 → `sendActionResult` 回传，若为 `read_screen` 则主动抓一次树上报。
- `onAccessibilityEvent`：debounce（如 400ms）抓 `rootInActiveWindow` → 递归成 `List<NodeDto>` → `sendPerception` 上报（含 pkg/activity）。
- `onInterrupt` / `onDestroy`：`close()`。

**前置确认**：`android/app/src/main/res/xml/accessibility_service_config.xml` 已存在（Manifest 已引用）；若缺失需补 `canRetrieveWindowContent="true"` + `flagRequestFilterKeyEvents` 等。

**可单测部分**：`AccessibilityNodeInfo → NodeDto` 的递归扁平化含 framework 类型，无法纯 JVM 单测；把「id 生成 / bounds Rect→List<Int>」这类可提炼逻辑放进 `NodeFlattener` 的纯函数辅助方法测试。Service 主体属真机集成，联调验证。

- [ ] **Step 1: 写失败测试**

新增 `android/app/src/test/java/com/example/phoneagent/accessibility/NodeFlattenerTest.kt`：

```kotlin
package com.example.phoneagent.accessibility

import android.graphics.Rect
import org.junit.Assert.assertEquals
import org.junit.Test

class NodeFlattenerTest {

    @Test
    fun rect_to_bounds_list_is_ltrb() {
        val rect = Rect(10, 20, 110, 80)
        assertEquals(listOf(10, 20, 110, 80), NodeFlattener.rectToBounds(rect))
    }

    @Test
    fun make_id_is_stable_for_same_index_path() {
        assertEquals("0-2-1", NodeFlattener.makeId(listOf(0, 2, 1)))
    }

    @Test
    fun make_id_root_is_zero() {
        assertEquals("0", NodeFlattener.makeId(listOf(0)))
    }
}
```

> 说明：`Rect` 在 Robolectric/单测环境下若不可用，可改为传 `left,top,right,bottom` 四个 Int 的重载；此处保留 `rectToBounds(Rect)` 并额外提供 `rectToBounds(l,t,r,b)` 纯 Int 重载供单测，避免依赖 Android 运行时。

- [ ] **Step 2: Run test to verify it fails**

Run: `cd android && ./gradlew :app:testDebugUnitTest --tests "com.example.phoneagent.accessibility.NodeFlattenerTest"`
Expected: FAIL（`NodeFlattener` 不存在）

- [ ] **Step 3: 最小实现**

**3a. 新增 `android/app/src/main/java/com/example/phoneagent/accessibility/NodeFlattener.kt`：**

```kotlin
package com.example.phoneagent.accessibility

import android.graphics.Rect
import android.view.accessibility.AccessibilityNodeInfo
import com.example.phoneagent.protocol.NodeDto

/** 节点扁平化：递归 AccessibilityNodeInfo → List<NodeDto>。纯辅助方法可单测。 */
object NodeFlattener {

    fun makeId(indexPath: List<Int>): String = indexPath.joinToString("-")

    fun rectToBounds(l: Int, t: Int, r: Int, b: Int): List<Int>= listOf(l, t, r, b)

    fun rectToBounds(rect: Rect): List<Int> = rectToBounds(rect.left, rect.top, rect.right, rect.bottom)

    /** 递归收集节点（framework 集成，真机验证）。 */
    fun flatten(root: AccessibilityNodeInfo?): List<NodeDto> {
        val out = mutableListOf<NodeDto>()
        if (root != null) walk(root, listOf(0), out)
        return out
    }

    private fun walk(node: AccessibilityNodeInfo, path: List<Int>, out: MutableList<NodeDto>) {
        val rect = Rect().also { node.getBoundsInScreen(it) }
        val visible = rect.width() > 0 && rect.height() > 0
        val text = node.text?.toString()
        // ��云端 PerceptionFilter 对齐：可见且(可点击或有文本)才上报
        if (visible && (node.isClickable || !text.isNullOrBlank())) {
            out.add(
                NodeDto(
                    id = makeId(path),
                    text = text,
                    desc = node.contentDescription?.toString(),
                    className = node.className?.toString(),
                    bounds = rectToBounds(rect),
                    clickable = node.isClickable,
                    editable = node.isEditable,
                )
            )
        }
        for (i in 0 until node.childCount) {
            val child = node.getChild(i) ?: continue
            walk(child, path + i, out)
        }
    }
}
```

**3b. 重写 `android/app/src/main/java/com/example/phoneagent/accessibility/PhoneAgentService.kt`：**

```kotlin
package com.example.phoneagent.accessibility

import android.accessibilityservice.AccessibilityService
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.view.accessibility.AccessibilityEvent
import com.example.phoneagent.net.WsClient
import com.example.phoneagent.protocol.UplinkPerception

class PhoneAgentService : AccessibilityService() {

    companion object {
        // 真机联调：填 Mac 局域网 IP，如 "ws://192.168.1.20:8000"
        const val WS_URL = "ws://10.0.2.2:8000"
        private const val DEBOUNCE_MS = 400L
    }

    private lateinit var executor: Executor
    private var wsClient: WsClient? = null
    private val handler = Handler(Looper.getMainLooper())
    private var pendingReport: Runnable? = null

    override fun onServiceConnected() {
        super.onServiceConnected()
        executor = Executor(service = this, context = applicationContext)
        val deviceId = Settings.Secure.getString(contentResolver, Settings.Secure.ANDROID_ID) ?: "device"
        wsClient = WsClient(
            baseUrl = WS_URL,
            onTaskStart = { _, _ -> reportScreen() },
            onAction = { action ->
                val ok = executor.execute(action.op, action.params)
                wsClient?.sendActionResult(action.actionId, ok)
                if (action.op == "read_screen") reportScreen()
            },
            onTaskEnd = { /* done/abort：MVP 仅结束，可扩展 UI 提示 */ },
        ).also { it.connect(deviceId) }
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        // debounce：频繁事件只保留最后一次抓树
        pendingReport?.let { handler.removeCallbacks(it) }
        val r = Runnable { reportScreen() }
        pendingReport = r
        handler.postDelayed(r, DEBOUNCE_MS)
    }

    private fun reportScreen() {
        val root = rootInActiveWindow ?: return
        val nodes = NodeFlattener.flatten(root)
        val perception = UplinkPerception(
            nodeTree = nodes,
            pkg = root.packageName?.toString() ?: "",
            activity = "",
            ts = System.currentTimeMillis(),
        )
        wsClient?.sendPerception(perception)
    }

    override fun onInterrupt() {
        wsClient?.close()
    }

    override fun onDestroy() {
        pendingReport?.let { handler.removeCallbacks(it) }
        wsClient?.close()
        super.onDestroy()
    }
}
```

> 注：模拟器访问宿主机用 `10.0.2.2`；真机联调改为 Mac 局域网 IP。后续可迁移到 `BuildConfig` 字段，MVP 先用常量（符合"改一处"决策）。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd android && ./gradlew :app:testDebugUnitTest --tests "com.example.phoneagent.accessibility.NodeFlattenerTest"`
Expected: PASS（纯函数全绿；Service/flatten 真机验证）

- [ ] **Step 5: Commit**

```bash
git add android/app/src/main/java/com/example/phoneagent/accessibility/NodeFlattener.kt \
        android/app/src/main/java/com/example/phoneagent/accessibility/PhoneAgentService.kt \
        android/app/src/test/java/com/example/phoneagent/accessibility/NodeFlattenerTest.kt
git commit -m "feat(android): PhoneAgentService connects WS, reports tree, executes actions"
```

---

## Task 9：MainActivity onResume 刷新无障碍开启状态

**目标**：`MainActivity` 在 `onResume` 检查 `PhoneAgentService` 是否已启用，刷新提示文案（"未开启 → 请开启" / "已开启 → 可联调"），并把按钮文案随状态更新。判断逻辑：读 `Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES` 字符串，检查是否包含本服务的 `ComponentName` 扁平字符串。

**可单测部分**：把"给定 enabled 字符串 + 目标组件名 → 是否启用"的纯字符串匹配抽为 `AccessibilityStatus.isEnabled(enabledSetting, componentFlat)`。

- [ ] **Step 1: 写失败测试**

新增 `android/app/src/test/java/com/example/phoneagent/AccessibilityStatusTest.kt`：

```kotlin
package com.example.phoneagent

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AccessibilityStatusTest {

    private val target = "com.example.phoneagent/com.example.phoneagent.accessibility.PhoneAgentService"

    @Test
    fun enabled_when_setting_contains_component() {
        val setting = "com.other/foo:$target"
        assertTrue(AccessibilityStatus.isEnabled(setting, target))
    }

    @Test
    fun enabled_when_only_component() {
        assertTrue(AccessibilityStatus.isEnabled(target, target))
    }

    @Test
    fun disabled_when_setting_null() {
        assertFalse(AccessibilityStatus.isEnabled(null, target))
    }

    @Test
    fun disabled_when_component_absent() {
        assertFalse(AccessibilityStatus.isEnabled("com.other/foo:com.bar/baz", target))
    }
}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd android && ./gradlew :app:testDebugUnitTest --tests "com.example.phoneagent.AccessibilityStatusTest"`
Expected: FAIL（`AccessibilityStatus` 不存在）

- [ ] **Step 3: 最小实现**

**3a. 新增 `android/app/src/main/java/com/example/phoneagent/AccessibilityStatus.kt`：**

```kotlin
package com.example.phoneagent

/** 无障碍启用状态判定：纯字符串匹配，可单测。 */
object AccessibilityStatus {

    /**
     * @param enabledSetting Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES 的值（冒号分隔的组件列表）
     * @param componentFlat  目标服务的 ComponentName.flattenToString()
     */
    fun isEnabled(enabledSetting: String?, componentFlat: String): Boolean {
        if (enabledSetting.isNullOrBlank()) return false
        return enabledSetting.split(':').any { it.equals(componentFlat, ignoreCase = true) }
    }
}
```

**3b. 修改 `android/app/src/main/java/com/example/phoneagent/MainActivity.kt`：**

```kotlin
package com.example.phoneagent

import android.content.ComponentName
import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.example.phoneagent.accessibility.PhoneAgentService

class MainActivity : AppCompatActivity() {

    private lateinit var tip: TextView
    private lateinit var btn: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(48, 48, 48, 48)
        }

        tip = TextView(this)
        btn = Button(this).apply {
            setOnClickListener {
                startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
            }
        }

        root.addView(tip)
        root.addView(btn)
        setContentView(root)
    }

    override fun onResume() {
        super.onResume()
        refreshStatus()
    }

    private fun refreshStatus() {
        val componentFlat = ComponentName(this, PhoneAgentService::class.java).flattenToString()
        val setting = Settings.Secure.getString(
            contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES
        )
        val enabled = AccessibilityStatus.isEnabled(setting, componentFlat)

        if (enabled) {
            tip.text = "JoyPhone Agent\n\n无障碍服务已开启，可开始真机联调。"
            btn.text = "查看无障碍设置"
        } else {
            tip.text = "JoyPhone Agent\n\n请先开启无障碍服务后再进行真机联调。"
            btn.text = "打开无障碍设置"
        }
    }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd android && ./gradlew :app:testDebugUnitTest --tests "com.example.phoneagent.AccessibilityStatusTest"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add android/app/src/main/java/com/example/phoneagent/AccessibilityStatus.kt \
        android/app/src/main/java/com/example/phoneagent/MainActivity.kt \
        android/app/src/test/java/com/example/phoneagent/AccessibilityStatusTest.kt
git commit -m "feat(android): MainActivity reflects accessibility enabled status on resume"
```

---

## 全量回归

- [ ] **云端全量测试**

Run: `cd server && uv run pytest -v`
Expected: 原 27 + 新增（test_skill_cache 5 + test_real_llm + test_decision +2 + test_gateway_loop 5）全绿。

- [ ] **端侧全量单测**

Run: `cd android && ./gradlew :app:testDebugUnitTest`
Expected: MessagesTest / WsDispatchTest / GestureGeometryTest / NodeFlattenerTest / AccessibilityStatusTest / 原 PerceptionTest 全绿。

- [ ] **构建 APK**

Run: `cd android && ./gradlew :app:assembleDebug`
Expected: BUILD SUCCESSFUL，产出 `app/build/outputs/apk/debug/app-debug.apk`。

- [ ] **真机联调前置**
  1. Mac 与手机同局域网；`PhoneAgentService.WS_URL` 改为 Mac 局域网 IP（如 `ws://192.168.x.x:8000`）。
  2. 云端起服务：`cd server && uv run uvicorn app.gateway:create_app --factory --host 0.0.0.0 --port 8000`。
  3. 配置 LLM 环境变量：`OPENAI_BASE_URL` / `OPENAI_API_KEY` / `OPENAI_MODEL`（未配则 fallback FakeLLM）。
  4. 装 APK → 开无障碍 → 回主界面确认"已开启" → App 自动连 WS → 观察飞书闭环。

- [ ] **收尾**
  - `server/data/skill_cache.json` 加入 `.gitignore`。
  - 首次真机跑通后检查 `skill_cache.json` 是否写入语义步序列。

---

## 风险与回退

1. **节点树稳定性**：飞书/桌面节点结构随 ROM 与飞书版本变化，`match_text` 可能失配 → 靠 LLM 兜底重新决策。
2. **缓存失效**：飞书大版本更新后语义步可能过时 → 某步执行失败（`action.result.ok=false`）时 cursor 不推进，回退 LLM 重新决策，成功后 `learn` 覆盖更新缓存。
3. **WS 连接**：真机需与 Mac 同网段；`10.0.2.2` 仅模拟器可用，真机必须改局域网 IP。
4. **手势坐标**：`dispatchGesture` 用屏幕绝对坐标，多分辨率设备下依赖实时 bounds（已按实时 `getBoundsInScreen` 取中心，不缓存绝对坐标）。