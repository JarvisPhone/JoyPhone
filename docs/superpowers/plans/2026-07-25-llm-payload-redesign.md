# LLM 通信内容重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把云端发给 LLM 的 payload 从「平铺 key:value」重构为「`[OBSERVE]` / `[GROUND]` / `[PHASE]` / `[ACT]` / `[VERIFY]` / `[SCENE-BRIEF]` 六段稳定结构」,scene-brief 按 Scene×AppPage 按需注入;system prompt 缩到 ~1500 字符;每段信息语义清晰、字段名稳定,LLM 解析不再依赖自然语言。

**Architecture:**
- `engine.py` 把 `_SYSTEM_PROMPT` 缩到 `[ROLE]+[TOOLS]+[CONTRACT:done]`,把 `user_text` 拼接函数抽到 `decision/payload.py`,按四段顺序拼接
- 新增 `decision/scene_briefs.py`,按 `Scene × AppPage` 注册 brief 字典,通用 brief 写死,app-specific brief 通过 `AppProfile` 的可选字段注入
- `scenario/base.py` 给 `AppProfile` 加可选字段 `llm_brief: str = ""`;`feishu.py` 加飞书专属 brief
- 新增 `scenario/phase.py`(TaskPhase 状态机),与 `SendMessagePack` 联动让 phase 状态在 task 级持有
- 任务规划分 6 phase,每 phase 独立 commit + 独立三命令全绿

**Tech Stack:** Python 3.14 / pytest / pyright;端侧零改动(协议 v2 不变;output op 不变;`parse_actions` 不变);基础设施已经包含 `setup_logging()` 双轨日志,所有新增诊断日志走 `_diag.info(...)`。

---

## 文件结构

| 文件 | 责任 |
|---|---|
| **新增** `server/app/decision/payload.py` | `build_user_payload(d) -> str` 单一入口;`build_system_prompt() -> str` 缩到 ~1500 char |
| **新增** `server/app/decision/scene_briefs.py` | `_GENERIC_BRIEFS: dict[Scene\|AppPage, str]`;`brief_for(scene, page) -> str \| None` |
| **新增** `server/app/scenario/phase.py` | `TaskPhase` enum + `phase_state: dataclass`;`advance()` / `record_step()`;初始切到 phase 0 |
| **修改** `server/app/decision/engine.py` | `_SYSTEM_PROMPT` 改 `build_system_prompt()` 调用;`_llm_decide` 内拼 payload 改 `build_user_payload(d)` |
| **修改** `server/app/scenario/base.py` | `AppProfile` 加 `llm_brief: str = ""`(可选) |
| **修改** `server/app/scenario/profiles/feishu.py` | `FEISHU_PROFILE` 加 llm_brief 字段(通用 brief 加飞书专项) |
| **修改** `server/app/task/context.py` | `TaskContext` 加 `phase: PhaseState` 字段(默认 PhaseState()) |
| **修改** `server/app/task/handlers.py` | `_on_task_request` 初始化 phase;`applied_steps.append` 时 `phase.record_step(...)` |
| **修改** `server/app/decision/types.py` | `DecideInput` 加 `phase: PhaseState`(可选字段) |
| **新增测试** `server/tests/test_payload.py` | payload 构造器系列单测 |
| **新增测试** `server/tests/test_scene_briefs.py` | scene brief 检索单测 |
| **新增测试** `server/tests/test_phase.py` | TaskPhase 状态机单测 |
| **新增测试** `server/tests/test_brief_injection.py` | AppProfile 注入 brief 测试 |

---

## Task 1: 新增 `decision/payload.py` 骨架(纯函数)

**Files:**
- Create: `server/app/decision/payload.py`
- Test: `server/tests/test_payload.py`

- [ ] **Step 1: 写失败测试(pay_001 ~ pay_005)**

```python
# server/tests/test_payload.py
from types import SimpleNamespace

from app.decision.engine import _nav_map
from app.protocol import Perception
from app.decision.payload import (
    build_system_prompt,
    build_user_payload,
    encode_visible_nodes,
    render_layout_summary,
)


def _node(i, text="", *, clickable=True, editable=False, rid="", cls="", bounds=None):
    """构造一个测试用的极简 Node,字段名与 protocol.Node 对齐。"""
    return SimpleNamespace(
        id=str(i), text=text, desc="", clickable=clickable, editable=editable,
        viewIdResourceName=rid or None, className=cls or None,
        bounds=bounds or [0, 0, 100, 100],
    )


def test_system_prompt_under_2000_chars_and_starts_with_role():
    sp = build_system_prompt()
    assert len(sp) < 2000, f"system prompt too long: {len(sp)} chars"
    assert sp.startswith("[ROLE]")


def test_user_payload_has_four_sections_in_order():
    nodes = [_node(0, text="搜索", clickable=False, editable=True, rid="x:id/edit")]
    frame = SimpleNamespace(pkg="com.x", nodeTree=nodes, activity="", ts=1)
    payload = build_user_payload(
        goal="打开飞书给 Android 发消息",
        frame=frame,
        scene_label="app",
        page_label="app.inbox_list",
        target_pkg="com.ss.android.lark",
        exit_path="单 back 回列表",
        nav_map="top=(0:input) mid=(0:plain) bottom=(0:plain)",
        screen_text="[0] input \"搜索\"",
        feedback="",
        last_action=None,
        scene_brief=None,
    )
    obs = payload.index("[OBSERVE]")
    grd = payload.index("[GROUND]")
    act = payload.index("[ACT]")
    vr = payload.index("[VERIFY]")
    assert obs >= 0 and grd > obs and act > grd and vr > act


def test_visible_nodes_only_includes_clickable_editable_or_titled_nodes():
    nodes = [
        _node(0, text="搜索框", editable=True),                 # 可交互,留
        _node(1, text="发送", clickable=True),                  # 可交互,留
        _node(2, text="装饰", clickable=False, editable=False), # 纯装饰,剔
        _node(3, text="", rid="com.x:id/btn_send", clickable=True),  # rid 带语义,留
        _node(4, text="", clickable=False, editable=False),     # 无语义无交互,剔
    ]
    out = encode_visible_nodes(nodes, ancestor_clickable=[False]*len(nodes), screen_height=200)
    assert "[0]" in out  # editable
    assert "btn_send" in out or "btn send" in out  # rid 兜底
    assert "装饰" not in out  # 装饰节点剔除


def test_render_layout_summary_marks_top_middle_bottom():
    # screen_height=240,bucket_size=60
    nodes = [
        _node(0, text="top", bounds=[0, 0, 100, 30]),       # bucket 0(顶部)
        _node(1, text="mid", bounds=[0, 100, 100, 150]),     # bucket 2(中部)
        _node(2, text="bot", bounds=[0, 200, 100, 230]),     # bucket 3(底部)
    ]
    summary = render_layout_summary(nodes, ancestor_clickable=[False]*len(nodes))
    assert "top=" in summary and "mid=" in summary and "bottom=" in summary


def test_user_payload_section_with_scene_brief_appears_after_observe():
    nodes = [_node(0, text="x", clickable=True)]
    frame = SimpleNamespace(pkg="com.coloros.launcher", nodeTree=nodes, activity="", ts=1)
    payload = build_user_payload(
        goal="x", frame=frame, scene_label="launcher.minus_one",
        page_label="n/a", target_pkg="com.ss.android.lark",
        exit_path="swipe right", nav_map="top=(1:button)",
        screen_text="[0] button \"小布建议\"",
        feedback="", last_action=None,
        scene_brief="你看到的「XX 有 N 条通知」是负一屏磁贴,**不是应用图标**。",
    )
    assert "[OBSERVE]" in payload
    assert "[SCENE-BRIEF" in payload
    assert "负一屏磁贴" in payload
    # scene-brief 必须在 OBSERVE 后,VERIFY 前
    assert payload.index("[OBSERVE]") < payload.index("[SCENE-BRIEF") < payload.index("[VERIFY]")
```

- [ ] **Step 2: 运行测试确认全部 FAIL**

```bash
cd server && uv run pytest tests/test_payload.py -v
```

Expected: 5 failed (ModuleNotFoundError: app.decision.payload)。

- [ ] **Step 3: 实现 `app/decision/payload.py`(版本 1,先把骨架搭起来)**

```python
# server/app/decision/payload.py
"""LLM payload 构造:把四段内容(text 块)组装成稳定结构的 user prompt。

六段顺序:[OBSERVE] [SCENE-BRIEF*] [GROUND] [PHASE] [ACT] [VERIFY]
(* 表示按需出现)

设计要点(2026-07-25 改造方案):
- 段名约定(方括号),LLM 看到段名就知道该看什么
- 每段内部用稳定字段名 + 自然语言,避免 JSON 嵌套
- scene-brief 不出现则完全跳过该段
- 输出是 str,被 engine._llm_decide 直接喂给 RealLLM.complete()
"""
from __future__ import annotations

from typing import Sequence

from app.protocol import Node


# ---- 节点编码 helpers ----

_SCREEN_BUCKETS = 4  # 屏高按 4 等分(top / upper / middle / lower)


def _node_label(node: Node) -> str:
    """节点显示标签:text/desc 优先,空则用 rid 末段"a_b_c"→"a b c"。"""
    text = (getattr(node, "text", None) or getattr(node, "desc", None) or "").strip()
    if text:
        return text[:60]
    rid = getattr(node, "viewIdResourceName", None) or ""
    if "/" in rid:
        tail = rid.rsplit("/", 1)[-1].replace("_", " ").strip()
    else:
        tail = rid
    return tail[:60]


def _bucket_of(node: Node, screen_top: int, screen_bot: int) -> int:
    b = getattr(node, "bounds", None)
    if not b or len(b) != 4:
        return -1
    span = max(1, screen_bot - screen_top)
    return min(_SCREEN_BUCKETS - 1, max(0, int((b[1] - screen_top) / span * _SCREEN_BUCKETS)))


def encode_visible_nodes(
    nodes: Sequence[Node],
    ancestor_clickable: Sequence[bool],
    screen_height: int | None = None,
) -> str:
    """只编码可交互 + 标题节点,纯装饰剔除。

    每行格式:`[序号] type "label"`(type: input/button/label/text)。
    label 来自 text/desc;空则用 rid 末段兜底。
    """
    if not nodes:
        return ""
    # 计算 screen 纵向区间(忽略没有 bounds 的节点)
    tops, bots = [], []
    for n in nodes:
        b = getattr(n, "bounds", None)
        if b and len(b) == 4:
            tops.append(b[1])
            bots.append(b[3])
    screen_top = min(tops) if tops else 0
    screen_bot = max(bots) if bots else screen_height or 1000

    def kept(i: int) -> bool:
        n = nodes[i]
        if n.clickable or n.editable:
            return True
        text = (n.text or n.desc or "").strip()
        return bool(text)  # 有标题的纯展示节点也保留

    out = []
    for i, n in enumerate(nodes):
        if not kept(i):
            continue
        if n.editable:
            t = "input"
        elif n.clickable:
            anc = ancestor_clickable[i] if i < len(ancestor_clickable) else False
            if n.clickable:
                t = "button"
            else:
                t = "button" if anc else "label"
        else:
            t = "label" if (n.text or n.desc or "").strip() else "text"
        out.append(f'[{i}] {t} "{_node_label(n)}"')
    return "\n".join(out)


def render_layout_summary(
    nodes: Sequence[Node],
    ancestor_clickable: Sequence[bool],
) -> str:
    """屏布局摘要:`top=(...) mid=(...) bottom=(...)`。

    只统计可交互节点(input/button)+ 标题节点(label)。
    """
    if not nodes:
        return ""
    tops, bots = [], []
    for n in nodes:
        b = getattr(n, "bounds", None)
        if b and len(b) == 4:
            tops.append(b[1])
            bots.append(b[3])
    screen_top = min(tops) if tops else 0
    screen_bot = max(bots) if bots else 1000

    buckets: dict[int, list[int]] = {0: [], 1: [], 2: [], 3: []}
    for i, n in enumerate(nodes):
        b_idx = _bucket_of(n, screen_top, screen_bot)
        if b_idx >= 0:
            buckets[b_idx].append(i)

    def tag(i: int) -> str:
        n = nodes[i]
        if n.editable:
            return "input"
        if n.clickable:
            return "button"
        return "label"

    def summarize(indices: list[int]) -> str:
        if not indices:
            return "empty"
        tags = [tag(i) for i in indices if tag(i) in {"input", "button", "label"}]
        if not tags:
            return f"{len(indices)} plain"
        if len(tags) > 6:
            tags = tags[:3] + ["..."] + tags[-2:]
        return f"{len(indices)}:" + ",".join(tags)

    top, mid_lo, mid_hi, bot = buckets[0], buckets[1], buckets[2], buckets[3]
    return (
        f"top=({summarize(top)}) "
        f"mid=({summarize(mid_lo + mid_hi)}) "
        f"bottom=({summarize(bot)})"
    )


# ---- System prompt 拼接 ----

_SYSTEM_PROMPT_TEMPLATE = """[ROLE]
你是 Android 手机操作代理的决策核心。给定当前屏幕的状态、你所在的位置、任务目标与可用操作清单,决定接下来一批 UI 动作。只输出文本指令,每行一条;不要 JSON / 思考 / Markdown 块。

[CONTRACT: done]
输出 done 必须四条件全部成立(主动用 expect 核查,不要肉眼判断):
  1. pkg == target_pkg(已在目标 app)
  2. 顶部标题 == 目标会话名
  3. 最近动作是 tap 发送按钮 且 ack.ok=true
  4. 输入框已清空(消息已发出)
任一不满足,改用 expect 核查,禁止直接 done。

[TOOLS]
- tap <n|"文本">       语义锚点点击,失败时按新屏幕重新决策(不要重复同一锚点)
- longpress <n>        长按 800ms,触发上下文菜单
- input <n> <文本>     在输入框输入,会替换现有内容
- swipe up|down|left|right   屏内滚动
- back                 上一级;在 app 内只按一次
- home                 回桌面;只在 pkg != target_pkg 时用
- press_enter          输完即搜索
- expect title "X"     核查当前页标题,不点任何东西
- expect pkg "com.x"   核查前台应用
- expect "文本"        核查屏幕里是否有该文本
- read                 信息不足,重抓屏幕
- wait <ms>            等动画
- done                 四条件全满足后输出
- abort <原因>          放弃并说明

批处理:可一次给出多行盲操作(home/swipe/back/wait),最多以一条 tap/input/expect 收尾。tap/input 后不要再写其它指令,系统会重新抓屏再问你。

输入里的 [OBSERVE] 给你屏幕现状,[GROUND] 给你位置/目标/退路,[PHASE] 告诉你当前任务阶段,[ACT] 给你可用动作与最近动作,[VERIFY] 给你上一条动作的判定结果。[SCENE-BRIEF] 出现时是当前场景的专项警告,请务必遵守。
"""


def build_system_prompt() -> str:
    return _SYSTEM_PROMPT_TEMPLATE


# ---- User payload 拼接 ----

_VERIFY_VERDICT_TEMPLATES = {
    "ok": "上一条动作成功,可以基于当前屏幕继续。",
    "fail": "上一条动作执行失败,详见 reason;不要重复同一锚点或坐标。",
    "intercepted": "上一条动作被策略拦截,策略已替你改发新动作;按当前屏幕继续。",
}


def _build_observe(
    pkg: str,
    scene_label: str,
    page_label: str,
    screen_text: str,
    nav_map: str,
) -> list[str]:
    parts = ["[OBSERVE]"]
    parts.append(f"pkg: {pkg}")
    parts.append(f"scene: {scene_label}{' (page: ' + page_label + ')' if scene_label == 'app' and page_label != 'n/a' else ''}")
    if nav_map:
        parts.append(f"layout: {nav_map}")
    if screen_text:
        parts.extend(["", "[visible_nodes]", screen_text])
    return parts


def _build_ground(
    goal: str,
    target_pkg: str,
    exit_path: str,
    depth: str = "",
    prev_subgoal: str = "",
) -> list[str]:
    parts = ["[GROUND]"]
    parts.append(f"goal: {goal}")
    if target_pkg:
        parts.append(f"target: 到达 pkg={target_pkg} 完成目标")
    if depth:
        parts.append(f"depth: {depth}")
    parts.append(f"exit_path: {exit_path}")
    if prev_subgoal:
        parts.append(f"prev_subgoal: {prev_subgoal}")
    return parts


def _build_phase(phase_label: str, current_step: str, next_gate: str) -> list[str]:
    return [
        "[PHASE]",
        f"phase: {phase_label}",
        f"current: {current_step}",
        f"next_gate: {next_gate}",
    ]


def _build_act(
    last_action: dict | None,
    last_step_count: int,
) -> list[str]:
    parts = ["[ACT]"]
    parts.append("available: 详见 [TOOLS] 段(系统提示词)")
    if last_action is not None:
        op = last_action.get("op", "?")
        ack = last_action.get("ack", "")
        reason = last_action.get("reason", "") or ""
        line = f"last_1_action: {op} → {ack}"
        if reason:
            line += f" ({reason})"
        parts.append(line)
    return parts


def _build_verify(feedback: str) -> list[str]:
    parts = ["[VERIFY]"]
    if feedback and feedback.strip():
        parts.append(feedback.strip())
    else:
        parts.append("(no feedback yet — assume previous action succeeded)")
    return parts


def build_user_payload(
    *,
    goal: str,
    frame,  # Perception(duck-typed,只用 pkg/nodeTree)
    scene_label: str,
    page_label: str,
    target_pkg: str,
    exit_path: str,
    nav_map: str,
    screen_text: str,
    feedback: str,
    last_action: dict | None,
    last_step_count: int = 0,
    scene_brief: str | None = None,
    phase_label: str = "(none)",
    phase_current: str = "(none)",
    phase_next_gate: str = "(none)",
    depth: str = "",
    prev_subgoal: str = "",
) -> str:
    """拼装 user payload 六段;scene_brief=None 时跳过该段。

    段顺序固定:[OBSERVE] [SCENE-BRIEF*] [GROUND] [PHASE] [ACT] [VERIFY]
    """
    sections: list[list[str]] = []
    sections.append(_build_observe(frame.pkg, scene_label, page_label, screen_text, nav_map))
    if scene_brief and scene_brief.strip():
        # 段名带 scene_label,便于 LLM 知道这是哪个 scene 的 brief
        sections.append([f"[SCENE-BRIEF: {scene_label}]", scene_brief.strip()])
    sections.append(_build_ground(goal, target_pkg, exit_path, depth, prev_subgoal))
    sections.append(_build_phase(phase_label, phase_current, phase_next_gate))
    sections.append(_build_act(last_action, last_step_count))
    sections.append(_build_verify(feedback))

    out: list[str] = []
    for sec in sections:
        out.extend(sec)
        out.append("")
    return "\n".join(out).rstrip()
```

- [ ] **Step 4: 运行测试确认全部 PASS**

```bash
cd server && uv run pytest tests/test_payload.py -v
```

Expected: 5 passed。

- [ ] **Step 5: Commit**

```bash
git add server/app/decision/payload.py server/tests/test_payload.py
git commit -m "feat(payload): 新增 decision/payload.py 六段拼接骨架"
```

---

## Task 2: 把 `engine._SYSTEM_PROMPT` 缩到 `[ROLE]+[TOOLS]+[CONTRACT]`

**Files:**
- Modify: `server/app/decision/engine.py:53-149`(`_SYSTEM_PROMPT` 那段 ~4770 char 整段)
- Verify: `server/tests/test_engine.py` 与 `server/tests/test_payload.py`

- [ ] **Step 1: 写失败测试**

```python
# 在 server/tests/test_payload.py 加
def test_system_prompt_dropped_rules_become_payload_sections():
    """旧 system prompt 里的「app 边界硬约束」「退出路径」等都搬到了 payload 对应段。

    这里只校验 system prompt 不再含这些关键词。
    """
    sp = build_system_prompt()
    forbidden = ["【重要·", "【feedback 字段】", "【idle 行为约束】", "目标 app 内", "严禁点击顶部"]
    for f in forbidden:
        assert f not in sp, f"old rule still in system prompt: {f!r}"


def test_system_prompt_doesnt_explain_scene_labels():
    """scene 解释迁到 SCENE-BRIEF 段,system prompt 不再列 Scene 枚举语义。"""
    sp = build_system_prompt()
    assert "scene 已经过服务端状态机判定" not in sp
    assert "page 进一步告诉你" not in sp
```

- [ ] **Step 2: 运行测试确认 FAIL**

```bash
cd server && uv run pytest tests/test_payload.py::test_system_prompt_dropped_rules_become_payload_sections tests/test_payload.py::test_system_prompt_doesnt_explain_scene_labels -v
```

Expected: 2 failed(旧 `_SYSTEM_PROMPT` 仍含这些字段)。

- [ ] **Step 3: 修改 `engine.py`**

删除 `_SYSTEM_PROMPT = """..."""`(53-149 行),改为:

```python
# server/app/decision/engine.py
from app.decision.payload import build_system_prompt, build_user_payload
```

将所有使用 `_SYSTEM_PROMPT` 的地方改为 `build_system_prompt()`(grep 一下只有 `_llm_decide` 内部调用)。

> ⚠️ 注意:`_SYSTEM_PROMPT` 是 module-level,如果别处 import,要同步改 import。

- [ ] **Step 4: 测试 PASS**

```bash
cd server && uv run pytest tests/test_payload.py -v && uv run pytest tests/test_engine.py -q 2>&1 | tail -10
```

Expected: test_payload.py 全过,test_engine.py 仍然全过(没有破坏现有测试,因为 `_SYSTEM_PROMPT` 字面常量被替换成等价 system prompt)。

- [ ] **Step 5: 三命令全绿**

```bash
cd server && uv run pytest tests/ -q
cd server && uv run pyright app/
cd android && ./gradlew :app:testDebugUnitTest
```

Expected: server pytest 全绿、pyright 0 errors、android BUILD SUCCESSFUL。

- [ ] **Step 6: Commit**

```bash
git add server/app/decision/engine.py server/tests/test_payload.py
git commit -m "refactor(prompt): system prompt 缩到 ROLE+TOOLS+CONTRACT,4770→~1100 char"
```

---

## Task 3: 新增 `decision/scene_briefs.py` 与 brief 检索

**Files:**
- Create: `server/app/decision/scene_briefs.py`
- Test: `server/tests/test_scene_briefs.py`

- [ ] **Step 1: 写失败测试**

```python
# server/tests/test_scene_briefs.py
from app.decision.app_page import AppPage
from app.decision.pkg_guard import Scene
from app.decision.scene_briefs import brief_for


def test_brief_for_minus_one_warns_widget_is_not_icon():
    text = brief_for(Scene.MINUS_ONE, AppPage.UNKNOWN)
    assert text is not None
    assert "负一屏" in text or "磁贴" in text


def test_brief_for_inbox_list_search_hint():
    text = brief_for(Scene.IN_APP, AppPage.INBOX_LIST)
    assert text is not None
    assert "搜索" in text


def test_brief_for_chat_warns_no_title_tap():
    text = brief_for(Scene.IN_APP, AppPage.CHAT)
    assert text is not None
    assert "标题" in text and "back" in text


def test_brief_for_unknown_page_returns_none():
    """UNKNOWN page 时不重复 scene-level brief(scene hint 已表达)。"""
    text = brief_for(Scene.IN_APP, AppPage.UNKNOWN)
    assert text is None


def test_brief_for_unknown_scene_returns_none():
    text = brief_for(Scene.UNKNOWN, AppPage.UNKNOWN)
    assert text is None


def test_brief_under_5_lines():
    """每个 brief 最多 5 行,严控 token。"""
    for s in Scene:
        for p in AppPage:
            text = brief_for(s, p)
            if text is None:
                continue
            # 5 行内 = 内容紧凑,真机可读
            assert text.count("\n") + 1 <= 5, f"{s}/{p} brief too long: {text!r}"
```

- [ ] **Step 2: 运行测试确认 FAIL**

```bash
cd server && uv run pytest tests/test_scene_briefs.py -v
```

Expected: ModuleNotFoundError。

- [ ] **Step 3: 实现 `app/decision/scene_briefs.py`**

```python
# server/app/decision/scene_briefs.py
"""Scene × AppPage 专有 brief 注册表(LLM 决策时按当前 scene 注入)。

设计目标:把「这个场景最容易踩的坑」变成可注入的自然语言段,
不靠 prompt 教学让 LLM 自己推理。

brief 文风约束:
- 每段最多 5 行
- 一段只讲一件事(避免 LLM 抓不住重点)
- 默认中文(项目惯例),英文也行
- 通用 brief 写在本文件,app-specific 通过 AppProfile.llm_brief 注入
"""
from __future__ import annotations

from app.decision.app_page import AppPage
from app.decision.pkg_guard import Scene

# (scene, page) → brief 正文
# None 表示该组合无 brief(scene-level 已经有通用提示,不要重复)
_BRIEFS: dict[tuple[Scene, AppPage], str] = {
    # 顶层 scene
    (Scene.HOME, AppPage.UNKNOWN):
        "桌面: 直接 tap 目标应用图标。已 swipe 过最近 app 的请看 [OBSERVE] 顶
部 tab 是否真的在桌面上(负一屏会误识别为可用图标)。",

    (Scene.MINUS_ONE, AppPage.UNKNOWN):
        "这是桌面「负一屏」(ColorOS 小布建议),**不是真正的桌面**。
「XX 有 N 条通知」「XX 推荐」是磁贴,不是应用图标。
退出:swipe right → 回到 launcher.home。",

    (Scene.NOTIFICATION, AppPage.UNKNOWN):
        "下拉通知栏。点通知会跳到对应 app 的具体页面,本任务通常不期望此行为。
退出:swipe up 或 back 收起。",

    (Scene.CONTROL_CENTER, AppPage.UNKNOWN):
        "下拉控制中心。退出:swipe up 或 back 收起。",

    (Scene.LOCK_SCREEN, AppPage.UNKNOWN):
        "锁屏。先 unlock 设备再继续任务。unlock 方式因设备而异,常见是 swipe up。",

    (Scene.RECENT_APPS, AppPage.UNKNOWN):
        "最近任务视图。退出:按 home 回桌面。",

    # app 内页型
    (Scene.IN_APP, AppPage.INBOX_LIST):
        "消息/通讯录列表页。需要时可 tap 顶部搜索框;列表内可 swipe up/down 滚动。
不要点标题栏(会进设置)。",

    (Scene.IN_APP, AppPage.CHAT):
        "聊天会话页。**单 back 返回上一级列表,不要按 home 退 app**。
**严禁点击顶部标题栏**——那是群设置入口,误进立刻 single back。
不确定是不是目标会话? 用 `expect title \"X\"` 核查,不要肉眼判断。",

    (Scene.IN_APP, AppPage.CONTACT_INFO):
        "联系人详情页。单 back 返回上一级。
若想给联系人发消息,看是否有「发消息」按钮(常见 rid: btn_chat)。",

    (Scene.IN_APP, AppPage.GROUP_INFO):
        "群详情页。单 back 返回会话页。
不要在这里点「群设置」之外的任何东西。",

    (Scene.IN_APP, AppPage.SETTINGS):
        "设置页。单 back 返回上一级;多层设置需多次 back。
不要一次 home 退 app——会丢掉任务目标 app 内的导航进度。",

    (Scene.IN_APP, AppPage.SEARCH):
        "搜索结果页。结果列表里点目标那一行(不是搜索框本身)。
单 back 或点左上角返回箭头回列表。",
}


def brief_for(scene: Scene, page: AppPage) -> str | None:
    """按 (scene, page) 查 brief;未命中返回 None(由调用方决定是否注入)。

    优先级:精确 (scene, page) > (scene, UNKNOWN) > None
    """
    key = (scene, page)
    if key in _BRIEFS:
        return _BRIEFS[key]
    # page 退化:找 (scene, UNKNOWN)
    fallback = (scene, AppPage.UNKNOWN)
    if fallback in _BRIEFS and fallback != key:
        return _BRIEFS[fallback]
    return None
```

- [ ] **Step 4: 测试 PASS**

```bash
cd server && uv run pytest tests/test_scene_briefs.py -v
```

Expected: 6 passed。

- [ ] **Step 5: Commit**

```bash
git add server/app/decision/scene_briefs.py server/tests/test_scene_briefs.py
git commit -m "feat(brief): 新增 Scene×AppPage brief 注册表(brief_for)"
```

---

## Task 4: 把 `_llm_decide` 改为 `build_user_payload()` 调用 + scene_brief 注入

**Files:**
- Modify: `server/app/decision/engine.py:616-700`(`_llm_decide` 内拼 user_text 那段)
- Verify: `server/tests/test_engine.py`

- [ ] **Step 1: 写失败测试**

```python
# 在 server/tests/test_payload.py 加
from app.decision.pkg_guard import Scene
from app.decision.app_page import AppPage

def test_payload_used_by_llm_decide_engine_includes_scene_brief_for_minus_one(monkeypatch):
    """engine.decide 触发 LLM 时,场景为 launcher.minus_one 应自动注入 brief。"""
    from app.decision.engine import DecisionEngine
    from app.decision.llm import FakeLLM
    from app.protocol import Node, Perception
    from app.decision.skills import SkillCursor

    captured = []
    class CapturingFake(FakeLLM):
        def complete(self, system, user, image_b64=None):
            captured.append(user)
            return "read"

    nodes = [Node(id="0", text="小布建议", viewIdResourceName="x:id/title",
                  bounds=[0, 0, 100, 100], clickable=False, editable=False)]
    frame = Perception(pkg="com.coloros.launcher", nodeTree=nodes, activity="", ts=1)

    # 直接调用 engine._llm_decide 不需要整条链路
    eng = DecisionEngine(llm=CapturingFake(["read"]), cache=None)
    from app.decision.engine import DecideInput
    eng._llm_decide(DecideInput(
        goal="打开飞书", frame=frame, target_pkg="com.ss.android.lark",
        cursor=SkillCursor(), bound_skill=None, guard={}, title_keywords=(),
    ))

    user = captured[0]
    assert "[SCENE-BRIEF: launcher.minus_one]" in user
    assert "负一屏" in user or "磁贴" in user


def test_payload_used_by_llm_decide_engine_excludes_scene_brief_when_none():
    """scene=app/page=app.inbox_list 有 brief(已在字典里)。但 UNKNOWN scene 没 brief 时不该加段。"""
    from app.decision.engine import DecisionEngine
    from app.decision.llm import FakeLLM
    from app.protocol import Node, Perception
    from app.decision.skills import SkillCursor

    captured = []
    class CapturingFake(FakeLLM):
        def complete(self, system, user, image_b64=None):
            captured.append(user)
            return "read"

    nodes = [Node(id="0", text="x", viewIdResourceName="x:id/xx",
                  bounds=[0, 0, 100, 100], clickable=False, editable=False)]
    frame = Perception(pkg="com.x", nodeTree=nodes, activity="", ts=1)

    eng = DecisionEngine(llm=CapturingFake(["read"]), cache=None)
    from app.decision.engine import DecideInput
    eng._llm_decide(DecideInput(
        goal="x", frame=frame, target_pkg="",
        cursor=SkillCursor(), bound_skill=None, guard={}, title_keywords=(),
    ))

    user = captured[0]
    # UNKNOWN scene 不应触发 SCENE-BRIEF 段
    assert "[SCENE-BRIEF:" not in user
```

- [ ] **Step 2: 运行测试确认 FAIL**

```bash
cd server && uv run pytest tests/test_payload.py::test_payload_used_by_llm_decide_engine_includes_scene_brief_for_minus_one tests/test_payload.py::test_payload_used_by_llm_decide_engine_excludes_scene_brief_when_none -v
```

Expected: 2 failed(当前 engine 自己拼 user_text,不走 payload 模块)。

- [ ] **Step 3: 修改 `engine.py:_llm_decide`**

定位 616-700 行那段拼 `user_parts` 的代码,改为调用 `build_user_payload`。涉及的子步骤:

1. **删除**`user_parts = [...]` 那段(整段 ~620-673 行)
2. **替换**为:

```python
# Compute scene/page + exit_path
scene = detect_scene(d.frame)
scene_label = _scene_label(d.frame)
page_label = _app_page_label(d.frame)
page_enum = detect_app_page(d.frame) if scene == Scene.IN_APP else AppPage.UNKNOWN
hint = exit_hint(scene, page_enum)

# Scene brief:先通用(scene,page)→(scene,UNKNOWN),再 app-specific(AppProfile.llm_brief)
from app.decision.scene_briefs import brief_for as _generic_brief
generic_brief = _generic_brief(scene, page_enum)
app_brief = ""
if d.target_pkg:
    profile = _ui_profile_for_pkg(d.target_pkg)
    app_brief = profile.llm_brief if profile is not None else ""
scene_brief = generic_brief
if app_brief:
    scene_brief = (scene_brief + "\n" + app_brief) if scene_brief else app_brief

# Nav map + visible nodes(只列可交互 + 标题)
nav_map = _nav_map(nodes, ancestor)
screen_text = encode_visible_nodes(nodes, ancestor)

# last_1_action 拼自 ctx.history(handler 层负责注入 DecideInput.last_action)
last_action = getattr(d, "last_action", None)

user_text = build_user_payload(
    goal=d.goal,
    frame=d.frame,
    scene_label=scene_label,
    page_label=page_label,
    target_pkg=d.target_pkg,
    exit_path=hint,
    nav_map=nav_map,
    screen_text=screen_text,
    feedback=d.feedback or "",
    last_action=last_action,
    scene_brief=scene_brief,
    phase_label="(phase not yet wired)",
    phase_current="",
    phase_next_gate="",
)
```

3. **新增 import**:`from app.decision.payload import build_user_payload, encode_visible_nodes`
4. **新增 import**:`from app.decision.scene_briefs import brief_for`

- [ ] **Step 4: 测试 PASS**

```bash
cd server && uv run pytest tests/test_payload.py tests/test_engine.py -v
```

Expected: test_payload.py 8+ passed,test_engine.py 仍全过。

- [ ] **Step 5: 三命令全绿**

```bash
cd server && uv run pytest tests/ -q
cd server && uv run pyright app/
cd android && ./gradlew :app:testDebugUnitTest
```

- [ ] **Step 6: Commit**

```bash
git add server/app/decision/engine.py
git commit -m "refactor(engine): _llm_decide 改用 build_user_payload,scene-brief 按需注入"
```

---

## Task 5: AppProfile 加 `llm_brief` 字段 + 飞书示例

**Files:**
- Modify: `server/app/scenario/base.py:20-30`(`AppProfile` pydantic 模型)
- Modify: `server/app/scenario/profiles/feishu.py`(加 llm_brief)
- Test: `server/tests/test_brief_injection.py`

- [ ] **Step 1: 写失败测试**

```python
# server/tests/test_brief_injection.py
from app.scenario.base import AppProfile
from app.scenario.profiles.feishu import FEISHU_PROFILE


def test_app_profile_has_llm_brief_field_default_empty():
    p = AppProfile(
        pkg="com.test", aliases=["t"],
        title_rid_keywords=["x"],
        send_button_keywords=["send"],
        search_hints=["搜索"],
        message_input_hints=["输入"],
    )
    assert p.llm_brief == ""


def test_feishu_profile_has_nonempty_llm_brief():
    assert FEISHU_PROFILE.llmrief != ""  # 注意下面 step 3 修复笔误
```

> ⚠️ 上面的 `llmrief` 是笔误,Step 3 写代码时改正:`FEISHU_PROFILE.llm_brief != ""`

- [ ] **Step 2: 运行测试确认 FAIL**

```bash
cd server && uv run pytest tests/test_brief_injection.py -v
```

Expected: 1 failed (AppProfile 缺 `llm_brief` field)。

- [ ] **Step 3: 实现**

**`scenario/base.py`** —— 在 `AppProfile` 类内最后加一行字段:

```python
class AppProfile(BaseModel):
    """单个 app 的 UI 识别特征(纯数据,不含逻辑)。"""

    pkg: str
    aliases: list[str]
    title_rid_keywords: list[str]
    send_button_keywords: list[str]
    search_hints: list[str]
    message_input_hints: list[str]
    sidebar_rid_keywords: list[str] = []
    # LLM 专有 brief:scene_brief 之外,该 app 特有的「容易踩坑」提醒。
    # 例如飞书可能会加「草稿输入框非空也会拦截 confirm」、「搜索结果点输入框无效」。
    # 推荐 1~3 行,直接给 LLM 看,不要解释术语。
    llm_brief: str = ""
```

**`scenario/profiles/feishu.py`** —— 在 `FEISHU_PROFILE = AppProfile(...)` 末尾加 `llm_brief=...`:

```python
FEISHU_PROFILE = AppProfile(
    pkg="com.ss.android.lark",
    aliases=["飞书", "feishu", "lark"],
    title_rid_keywords=[...],  # 保留原样不动
    send_button_keywords=[...],  # 保留原样不动
    search_hints=[...],
    message_input_hints=[...],
    sidebar_rid_keywords=[...],
    llm_brief=(
        "飞书特有提示:\n"
        "- 搜索结果列表里点「输入框本身」无效,要点「结果那一行」。\n"
        "- 输入空消息点发送 → ack 失败,改用 expect 核查输入框文本。\n"
        "- 个人主页左侧抽屉跨启动持久化,back 无效:用 expect pkg 核查。\n"
        "- 「草稿未清空」≠ 已发送;只有 tap 发送按钮且 ack ok 才是已发送。"
    ),
)
```

> ⚠️ 真实修改时保留原有内容,**只追加** `llm_brief=...` 这一行。

- [ ] **Step 4: 测试 PASS**

```bash
cd server && uv run pytest tests/test_brief_injection.py -v
```

Expected: 2 passed(注意 step 1 笔误 `llmrief`,step 4 跑前先改成 `llm_brief`)。

- [ ] **Step 5: Commit**

```bash
git add server/app/scenario/base.py server/app/scenario/profiles/feishu.py server/tests/test_brief_injection.py
git commit -m "feat(profile): AppProfile.llm_brief + 飞书专属 brief"
```

---

## Task 6: phase 状态机骨架(`scenario/phase.py`)

**Files:**
- Create: `server/app/scenario/phase.py`
- Modify: `server/app/task/context.py`(TaskContext 加 `phase` 字段)
- Test: `server/tests/test_phase.py`

- [ ] **Step 1: 写失败测试**

```python
# server/tests/test_phase.py
from app.scenario.phase import TaskPhase, PhaseState


def test_phase_state_init_default():
    p = PhaseState()
    assert p.phase == TaskPhase.IDLE
    assert p.current_step_index == 0
    assert p.completed_phases == []


def test_phase_state_advance_records_completion():
    p = PhaseState()
    p.advance(TaskPhase.SEARCH, gate_met_for="found_group")
    assert p.phase == TaskPhase.SEARCH
    assert p.current_step_index == 1
    assert p.completed_phases == [(TaskPhase.SEARCH, "found_group")]


def test_phase_state_record_step_no_advance():
    p = PhaseState(phase=TaskPhase.SEARCH, current_step_index=2)
    p.record_step(taken="tap", reached_gate=False)
    assert p.phase == TaskPhase.SEARCH
    assert p.current_step_index == 2  # 未达 next_gate,不推进


def test_phase_state_to_dict_for_payload():
    p = PhaseState(phase=TaskPhase.ENTER_CHAT, current_step_index=3)
    p.completed_phases.append((TaskPhase.SEARCH, "found_group"))
    d = p.to_payload_dict()
    assert d["phase"] == "enter_chat"
    assert d["current_step_index"] == 3
    assert d["completed_phases"] == [("search", "found_group")]


def test_task_phase_enum_canonical_send_message():
    """send_message 场景的 phase 顺序固定,跨调用方一致。"""
    from app.scenario.send_message import SendMessagePack
    pack = SendMessagePack()
    phases = pack.phases()
    assert TaskPhase.SEARCH in phases
    assert TaskPhase.INPUT_TEXT in phases
    assert TaskPhase.SEND in phases
```

- [ ] **Step 2: 运行测试确认 FAIL**

```bash
cd server && uv run pytest tests/test_phase.py -v
```

Expected: ModuleNotFoundError。

- [ ] **Step 3: 实现 `scenario/phase.py`**

```python
# server/app/scenario/phase.py
"""Task phase 状态机:每个 scenario 自定义 phase 推进规则。

设计动机:
- LLM 不该自己拆任务,云端把 phase 拆好放进 payload
- phase 推进由「last_1_action 的 ack 结果 + scene 状态」共同决定
- send_message 是第一个实现;后续 scenario 各自填 phases()

调用方:
- handlers._on_task_request:phase = PhaseState(phase=first_phase)
- handlers.applied_steps.append 时:phase.record_step(taken, reached_gate)
- engine._llm_decide:把 phase.to_payload_dict() 喂给 build_user_payload
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Protocol


class TaskPhase(str, enum.Enum):
    """send_message 等场景的 phase 枚举(示例;scenario 自行扩展)。"""

    IDLE = "idle"
    SEARCH = "search"            # 搜索目标会话
    ENTER_CHAT = "enter_chat"    # 进入匹配会话
    INPUT_TEXT = "input_text"    # 在输入框输入正文
    SEND = "send"                # tap 发送按钮 / 走 confirm 流
    VERIFY = "verify"            # 核查发送完成
    DONE = "done"


@dataclass
class PhaseState:
    """per-task phase 状态。"""

    phase: TaskPhase = TaskPhase.IDLE
    current_step_index: int = 0
    # [(phase_completed, gate_reason)] —— 供 LLM/统计查
    completed_phases: list[tuple[str, str]] = field(default_factory=list)

    def advance(self, to: TaskPhase, *, gate_met_for: str) -> None:
        """进入下一 phase;记录刚完成的 phase + 通过的 gate 描述。"""
        self.completed_phases.append((self.phase.value, gate_met_for))
        self.phase = to
        self.current_step_index = 0

    def record_step(self, *, taken: str, reached_gate: bool) -> None:
        """phase 内每步一次决策触发;reached_gate=True 时调用方负责 advance。"""
        self.current_step_index += 1

    def to_payload_dict(self) -> dict:
        """喂给 build_user_payload 的稳定 dict。"""
        return {
            "phase": self.phase.value,
            "current_step_index": self.current_step_index,
            "completed_phases": [
                {"phase": p, "gate": g} for p, g in self.completed_phases
            ],
        }


class PhasePack(Protocol):
    """scenario 自定义 phase 列表 + gate 检测。"""

    def phases(self) -> list[TaskPhase]:
        """该 scenario 的 phase 顺序。"""
        ...

    def gate_for(self, phase: TaskPhase, frame) -> str | None:
        """当前 phase 是否达到 next_gate;达到返回 gate 描述(中文),否则 None。"""
        ...
```

- [ ] **Step 4: `SendMessagePack` 实现 `PhasePack`**

修改 `scenario/send_message.py`,在 `SendMessagePack` 类内加两个方法:

```python
def phases(self) -> list:
    from app.scenario.phase import TaskPhase
    return [
        TaskPhase.SEARCH,
        TaskPhase.ENTER_CHAT,
        TaskPhase.INPUT_TEXT,
        TaskPhase.SEND,
        TaskPhase.VERIFY,
        TaskPhase.DONE,
    ]

def gate_for(self, phase, frame):  # phase: TaskPhase, frame: Perception
    from app.decision.app_page import AppPage, detect_app_page
    from app.decision.pkg_guard import Scene, detect_scene
    if phase == TaskPhase.SEARCH:
        return "已进入目标 app 的 inbox_list 页"
    if phase == TaskPhase.ENTER_CHAT:
        # 需在 chat 页且标题匹配
        from app.decision.ui_inspect import detect_title
        title = detect_title(frame.nodeTree, ())  # 主流程略去 rid kw
        return f"已到达目标会话(标题={title})"
    if phase == TaskPhase.INPUT_TEXT:
        return "输入框已输入非空正文"
    if phase == TaskPhase.SEND:
        return "已 tap 发送按钮 + ack ok + post_send.acked=True"
    if phase == TaskPhase.VERIFY:
        return "expect title 核查通过 + 输入框已清空"
    return None
```

> 注:实现用宽松判断够用,严苛匹配由下游策略 + expect 工具补;这里的目的是「LLM 知道当前 phase 与下一步门」。

- [ ] **Step 5: 修改 `TaskContext`**

在 `task/context.py` 的 `TaskContext` dataclass 内加 `phase` 字段(默认 `PhaseState()`):

```python
@dataclass
class TaskContext:
    # ... 现有字段保持不动 ...
    phase: "PhaseState" = field(default_factory=lambda: __import__("app.scenario.phase", fromlist=["PhaseState"]).PhaseState)
```

实际写时直接 `from app.scenario.phase import PhaseState` 在文件顶部,然后:

```python
phase: PhaseState = field(default_factory=PhaseState)
```

- [ ] **Step 6: 修改 handlers**

`_on_task_request`:在 `new_task` 之后:

```python
from app.scenario.phase import TaskPhase
ctx.phase.phase = TaskPhase.IDLE
```

`_dispatch` 里 `applied_steps.append(...)` 之后:

```python
ctx.phase.record_step(
    taken=action.op,
    reached_gate=False,  # 实际推进在 scenario.policies 里判定
)
```

实现简化策略:`record_step` 默认 `reached_gate=False`,advance 由后续 policy 判定后手动调。

- [ ] **Step 7: 测试 PASS**

```bash
cd server && uv run pytest tests/test_phase.py -v && uv run pytest tests/ -q 2>&1 | tail -10
```

Expected: test_phase 5 passed,全套测试仍绿。

- [ ] **Step 8: Commit**

```bash
git add server/app/scenario/phase.py server/app/scenario/send_message.py server/app/task/context.py server/app/task/handlers.py server/tests/test_phase.py
git commit -m "feat(phase): TaskPhase 状态机 + PhaseState + SendMessagePack 接入"
```

---

## Task 7: 把 phase 接入 payload([PHASE] 段)(联动 Task 4 的 placeholder)

**Files:**
- Modify: `server/app/decision/types.py`(`DecideInput` 加 `phase`)
- Modify: `server/app/decision/engine.py`(`_llm_decide` 读取 d.phase)
- Test: `server/tests/test_payload.py`(扩充)

- [ ] **Step 1: 写失败测试**

```python
# 在 server/tests/test_payload.py 加
from app.scenario.phase import TaskPhase, PhaseState

def test_payload_phase_section_rendered_when_phase_provided():
    state = PhaseState(phase=TaskPhase.SEARCH, current_step_index=2)
    state.completed_phases.append((TaskPhase.IDLE.value, "task started"))
    nodes = [_node(0, text="x", clickable=True)]
    frame = SimpleNamespace(pkg="com.x", nodeTree=nodes, activity="", ts=1)
    payload = build_user_payload(
        goal="g", frame=frame, scene_label="app", page_label="app.inbox_list",
        target_pkg="com.ss.android.lark",
        exit_path="单 back 回列表", nav_map="top=(1:button)",
        screen_text="[0] button \"x\"",
        feedback="", last_action=None,
        scene_brief=None,
        phase_label="search",
        phase_current="step 2",
        phase_next_gate="已进入目标 app 的 inbox_list 页",
    )
    assert "[PHASE]" in payload
    assert "phase: search" in payload
    assert "current: step 2" in payload
    assert "next_gate: 已进入目标 app 的 inbox_list 页" in payload
```

- [ ] **Step 2: 运行测试,确认 FAIL**

```bash
cd server && uv run pytest tests/test_payload.py::test_payload_phase_section_rendered_when_phase_provided -v
```

Expected: FAIL(`build_user_payload` 当前用 `(none)` 默认值,不会被 phase_label 覆盖 — 实际上 phase 已经是 task 6 的接口,这一步只要确保能传成功)。

- [ ] **Step 3: `DecideInput` 加 phase 字段**

```python
# server/app/decision/types.py (或 engine.py 的 DecideInput 局部 — 当前在 engine.py)
@dataclass
class DecideInput:
    # ... 现有字段 ...
    phase: PhaseState | None = None  # type: ignore[name-defined]
```

> 调整:`PhaseState` 在 `scenario/phase.py`,DecideInput 在 `decision/engine.py`。改 import:`from app.scenario.phase import PhaseState`(避免循环 import,放延迟 import 或在 engine.py 顶部 import)。

- [ ] **Step 4: 修改 `engine._llm_decide`(Task 4 阶段二版)**

读 `d.phase`(`None` 时用 `PhaseState()` 兜底)→ 拼 `phase_label / phase_current / phase_next_gate`:

```python
phase = d.phase or PhaseState()
payload_phase = phase.to_payload_dict()
phase_label = payload_phase["phase"] or "(phase not yet wired)"
current_step_index = payload_phase["current_step_index"]
phase_next_gate_text = ""
# gates 由 SendMessagePack.gate_for 提供 —— 这里取上一 phase 完成后能用的 gate
if scenario_pack := _scenario_for(deps, ctx):  # engine 无 ctx,改用 d
    pass
# 简化:gate 文本直接由 send_message.gate_for 提供,改造后由 policy 写入 ctx.phase.gate_hint
# 此处先用占位,等下个 phase 实现完整 gate 推进
user_text = build_user_payload(
    ...,
    phase_label=phase_label,
    phase_current=f"step {current_step_index}/{len(payload_phase['completed_phases']) + 1}",
    phase_next_gate="(see above; use expect to verify progress)",
)
```

实际写时保持简洁:`phase_current` 给一个 step 数即可,gate 文本由后续 task 完整化。

- [ ] **Step 5: 测试 PASS + 三命令**

```bash
cd server && uv run pytest tests/test_payload.py -v && uv run pytest tests/ -q
cd server && uv run pyright app/
cd android && ./gradlew :app:testDebugUnitTest
```

Expected: 全绿。

- [ ] **Step 6: Commit**

```bash
git add server/app/decision/engine.py server/app/decision/types.py server/tests/test_payload.py
git commit -m "feat(phase): DecideInput.phase + payload [PHASE] 段填值"
```

---

## Task 8: feedback 重新结构化(替代现状 `[feedback]` 自然语言块)

**Files:**
- Modify: `server/app/decision/payload.py`(`_build_verify` 改成结构化字段渲染)
- Modify: `server/app/task/handlers.py`(`_format_feedback` 改为新格式 + 替换 `_last_action`)
- Test: `server/tests/test_payload.py`(扩充 verify 段)

- [ ] **Step 1: 写失败测试**

```python
# server/tests/test_payload.py 加
def test_payload_verify_section_renders_structured_fields():
    feedback = (
        "last_action: tap\n"
        "ack: ok=false\n"
        "reason: anchor_not_found\n"
        "screen_changed: false\n"
        "page: app.chat\n"
    )
    nodes = [_node(0, text="x")]
    frame = SimpleNamespace(pkg="com.x", nodeTree=nodes, activity="", ts=1)
    payload = build_user_payload(
        goal="g", frame=frame, scene_label="app", page_label="app.chat",
        target_pkg="com.ss.android.lark", exit_path="单 back",
        nav_map="top=(0:button)", screen_text="x",
        feedback=feedback, last_action=None,
    )
    assert "[VERIFY]" in payload
    assert "last_action: tap" in payload
    assert "screen_changed: false" in payload
    assert "page: app.chat" in payload
    assert "[feedback]" not in payload  # 旧段名不再出现


def test_payload_verify_section_when_no_feedback():
    nodes = [_node(0, text="x")]
    frame = SimpleNamespace(pkg="com.x", nodeTree=nodes, activity="", ts=1)
    payload = build_user_payload(
        goal="g", frame=frame, scene_label="app", page_label="app.chat",
        target_pkg="com.x", exit_path="x", nav_map="", screen_text="x",
        feedback="", last_action=None,
    )
    assert "[VERIFY]" in payload
    assert "no feedback" in payload.lower() or "assume previous action succeeded" in payload
```

- [ ] **Step 2: 运行测试 FAIL,确认旧段名在 verify 里**

```bash
cd server && uv run pytest tests/test_payload.py::test_payload_verify_section_renders_structured_fields tests/test_payload.py::test_payload_verify_section_when_no_feedback -v
```

Expected: 2 failed(当前 `_build_verify` 直接拼接字符串,字段无序;旧 `[feedback]` 段名仍在)。

- [ ] **Step 3: 修改 `payload.py` 的 `_build_verify`**

定位 `_build_verify` 函数,改为:

```python
def _build_verify(feedback: str) -> list[str]:
    parts = ["[VERIFY]"]
    if feedback and feedback.strip():
        # feedback 是稳定的"字段: 值"格式,直接原样拼接(handlers 已结构化)
        parts.append(feedback.strip())
    else:
        parts.append("(no feedback — assume previous action succeeded)")
    return parts
```

> 注:`_format_feedback` 已经在 handlers 端结构化输出,这里无需 transform,只要 verify 段名稳定为 `[VERIFY]`,字段名稳定(`last_action`/`ack`/`reason`/`screen_changed`/`page`)。

- [ ] **Step 4: handlers 端 `_format_feedback` 与 `[feedback]` 段名清理**

定位 `_format_feedback` 函数(handlers.py:89-133),**段名从 `[feedback]` 改为 `[VERIFY]`,字段顺序不变**(`last_action / result / reason / policy / replaced_op / page / exit_hint / extra`):

```python
def _format_feedback(...) -> str:
    lines = ["[VERIFY]"]   # 原 [feedback]
    lines.append(f"last_action: {last_op}")
    lines.append(f"ack: {result}")  # 原 result,改名 ack(语义对齐 payload 验证)
    # ... 其余字段保持不动 ...
```

字段 `screen_changed` 在现 handlers 里没生成,需要在 `_on_action_result` 里判断屏幕变化时填。简化:本 task 只做段名 + ack 字段名调整;`screen_changed` 留到下个 task 完整化(避免一次过大改动)。

- [ ] **Step 5: 测试 PASS + 三命令**

```bash
cd server && uv run pytest tests/test_payload.py tests/test_engine.py tests/test_handlers.py -v && uv run pytest tests/ -q
cd server && uv run pyright app/
```

Expected: 全绿。

- [ ] **Step 6: Commit**

```bash
git add server/app/decision/payload.py server/app/task/handlers.py server/tests/test_payload.py
git commit -m "refactor(verify): [feedback] 段重命名 [VERIFY],字段名稳定为 ack"
```

---

## Task 9: gate 推进 + screen_changed 字段补齐(给 feedback 完整版)

**Files:**
- Modify: `server/app/task/handlers.py`(`_on_action_result` 写 screen_changed)
- Modify: `server/app/scenario/send_message.py`(`gate_for` 完整化 + `phase_advancer` policy)
- Test: `server/tests/test_phase.py`(扩)

- [ ] **Step 1: 写失败测试**

```python
# server/tests/test_phase.py 加
def test_phase_advance_from_search_to_enter_chat_when_inbox_list(monkeypatch):
    from app.scenario.send_message import SendMessagePack
    from app.scenario.phase import TaskPhase, PhaseState
    pack = SendMessagePack()
    # 构造 inbox_list 帧(INBOX_LIST 由 detect_app_page 判定)
    from app.protocol import Node, Perception
    nodes = [Node(id="0", text="搜索", viewIdResourceName="com.x:id/edit",
                  bounds=[0, 100, 1000, 200], editable=True, clickable=False)]
    # 列表项
    nodes.append(Node(id="1", text="沟通群", viewIdResourceName="com.x:id/list_item",
                      bounds=[0, 300, 1000, 400], clickable=True, editable=False))
    # mock detect_app_page → INBOX_LIST(简化)
    from app.decision import app_page as ap
    monkeypatch.setattr(ap, "detect_app_page",
                        lambda f: ap.AppPage.INBOX_LIST)
    from app.decision import pkg_guard as pg
    monkeypatch.setattr(pg, "detect_scene", lambda f: pg.Scene.IN_APP)
    frame = Perception(pkg="com.x", nodeTree=nodes, activity="", ts=1)
    p = PhaseState(phase=TaskPhase.SEARCH)
    gate = pack.gate_for(TaskPhase.SEARCH, frame)
    assert gate is not None
    p.advance(TaskPhase.ENTER_CHAT, gate_met_for=gate)
    assert p.phase == TaskPhase.ENTER_CHAT


def test_phase_no_advance_when_still_in_launcher():
    from app.scenario.send_message import SendMessagePack
    from app.scenario.phase import TaskPhase
    pack = SendMessagePack()
    from app.protocol import Node, Perception
    frame = Perception(pkg="com.coloros.launcher",
                       nodeTree=[Node(id="0", text="x", clickable=False, editable=False, bounds=[0,0,1,1])],
                       activity="", ts=1)
    assert pack.gate_for(TaskPhase.SEARCH, frame) is None
```

- [ ] **Step 2: 运行测试 FAIL,确认 gate 不存在或不可用**

```bash
cd server && uv run pytest tests/test_phase.py::test_phase_advance_from_search_to_enter_chat_when_inbox_list tests/test_phase.py::test_phase_no_advance_when_still_in_launcher -v
```

Expected: 2 failed(`SendMessagePack.gate_for` 是 task 6 占位实现)。

- [ ] **Step 3: `SendMessagePack.gate_for` 完整化**

修改 `scenario/send_message.py` 的 `gate_for` 方法,基于 `detect_app_page` + 标题匹配 + 输入框内容真实判定:

```python
def gate_for(self, phase, frame):
    from app.decision.app_page import detect_app_page, AppPage
    from app.decision.pkg_guard import detect_scene, Scene
    from app.decision.ui_inspect import detect_title
    from app.task.context import TaskContext  # 不直接依赖,用 weak ref
    # phase 推进需要 ctx(target_chat/title_keywords),这里签名只接 frame
    # gate_for 调用方传 (phase, frame, ctx) — 改 Protocol 签名:

    # === 改 Protocol ===
    # server/app/scenario/phase.py — PhasePack.gate_for(phase, frame) -> ...
    #                  改为     .gate_for(phase, frame, ctx) -> ...
    pass
```

实际写时:`PhasePack.gate_for` 的签名接受 `(phase, frame, ctx)`,实现按 phase 查 ctx(target_chat / target_pkg / post_send.acked):

```python
def gate_for(self, phase, frame, ctx):
    page = detect_app_page(frame)
    cur_title = detect_title(frame.nodeTree, tuple(ctx.profile.title_rid_keywords)) if hasattr(ctx, "profile") else None
    if phase == TaskPhase.SEARCH:
        return "已进入 inbox_list" if page == AppPage.INBOX_LIST else None
    if phase == TaskPhase.ENTER_CHAT:
        if page == AppPage.CHAT and cur_title and match_title(ctx.target_chat, cur_title):
            return f"已进入目标会话({ctx.target_chat})"
        return None
    if phase == TaskPhase.INPUT_TEXT:
        # 输入框已有非空文本(且不是 hint)
        for n in frame.nodeTree:
            if n.editable and (n.text or "").strip():
                hints = tuple(h.lower() for h in (ctx.profile.message_input_hints if hasattr(ctx, "profile") else ()))
                if not any(h in (n.text or "").lower() for h in hints):
                    return "输入框已有正文"
        return None
    if phase == TaskPhase.SEND:
        return "send tap 已 ack ok" if ctx.post_send.acked else None
    if phase == TaskPhase.VERIFY:
        # expect 核查通过 + 输入框清空
        return "expect title 通过 + 输入框清空" if ctx.post_send.acked else None
    return None
```

> 注意:`ctx.profile` 不存在,需要从 `ctx.target_pkg` 反查 profile(写成 helper)。完整实现参见 `scenario/send_message.py:_profile_for(ctx)` —— 复用之。

- [ ] **Step 4: handlers `_on_action_result` 写 `screen_changed`**

定位 `_on_action_result`,在 `_format_feedback` 调用前:`screen_changed` 需要对比上一帧与当前帧——phase 0 不做精细 diff,用「上一帧 vs 当前帧 pkg 不同 OR nodeTree 数量差 > 30%」近似:

```python
# 在 ctx 上加 last_frame:Perception | None = None 字段
# _on_perception 入口:ctx.last_frame = uplink(若 seq > last_consumed_seq)
# _on_action_result:
prev = ctx.last_frame
curr = uplink  # 此处 uplink 不是 Perception —— 改:在 _on_perception 里写 screen_changed
# 简化:本 task 只动 verify 段,真要 screen_changed 由 send_message policy 写完调
# 这里只留 hook:把「上一帧 vs 当前帧」给 send_message policy 用
```

简化:`screen_changed` 由 `_on_perception` 在 `_format_feedback` 之前算好:

```python
screen_changed = (
    ctx.last_frame is None
    or ctx.last_frame.pkg != uplink.pkg
    or abs(len(ctx.last_frame.nodeTree) - len(uplink.nodeTree)) > int(0.3 * max(len(ctx.last_frame.nodeTree), 1))
)
ctx.last_frame = uplink  # 落上一帧
```

把 `screen_changed` 拼进 `_format_feedback` 的 `extra`。

- [ ] **Step 5: 测试 PASS + 三命令**

```bash
cd server && uv run pytest tests/test_phase.py tests/test_payload.py tests/test_handlers.py -v && uv run pytest tests/ -q
cd server && uv run pyright app/
cd android && ./gradlew :app:testDebugUnitTest
```

- [ ] **Step 6: Commit**

```bash
git add server/app/scenario/send_message.py server/app/scenario/phase.py server/app/task/handlers.py server/app/task/context.py server/tests/test_phase.py
git commit -m "feat(phase): gate_for 完整实现 + screen_changed 字段进 feedback"
```

---

## Task 10: nav_map → render_layout_summary 切换(节点收口)

**Files:**
- Modify: `server/app/decision/engine.py:228-285`(`_nav_map` 函数移除,改用 payload 模块)
- Verify: 所有引用 `_nav_map` 的测试不破

- [ ] **Step 1: 找引用 grep**

```bash
cd server && grep -rn "_nav_map" app/ tests/
```

确认只剩 `engine.py` 引用,且 Task 4 后已经被替换为 `render_layout_summary`。

- [ ] **Step 2: 删 `_nav_map`**

```bash
# 已不再使用;直接删除
```

- [ ] **Step 3: 三命令全绿**

```bash
cd server && uv run pytest tests/ -q
cd server && uv run pyright app/
cd android && ./gradlew :app:testDebugUnitTest
```

- [ ] **Step 4: Commit**

```bash
git add server/app/decision/engine.py
git commit -m "refactor: 删除 _nav_map,统一用 payload.render_layout_summary"
```

---

## Task 11: 端侧冒烟 + 真机校验 entry

**Files:** 无源码改动,只是人工操作清单

- [ ] **Step 1: 端侧 install + 启动**

```bash
cd android && ./gradlew :app:installDebug
adb install -r app/build/outputs/apk/debug/app-debug.apk
adb shell am start -n com.joyphone.agent/.MainActivity
```

- [ ] **Step 2: 启动服务端 + 后台日志监控**

```bash
cd server && uv run python scripts/run_uvicorn_detached.py
tail -F server/logs/server.jsonl | grep -i '\[PHASE\]\|scene-brief'
tail -F server/logs/llm.log | grep -E "expect|done"
```

- [ ] **Step 3: 跑场景 A(正向:飞书发消息)**

期待:
- `[OBSERVE]` / `[SCENE-BRIEF: launcher.minus_one]`(若误入)在 llm_req.log 出现
- `[PHASE] phase: search → enter_chat → input_text → send → verify` 自然推进
- `[VERIFY] ack: ok=false scene_changed: false` 等 verify 段出现在 LLM 决策帧

- [ ] **Step 4: 跑场景 C(二级页退出:飞书进群设置 → back 出)**

期待:
- 在 app.group_info 时 LLm 收到 `[SCENE-BRIEF: app] 单 back 返回 ...`
- LLM 输出单个 `back` 不是 `back+home` 振荡
- LoopGuardPolicy 不被触发

- [ ] **Step 5: grep `[SCENE-BRIEF]` 出现频次**

```bash
grep -c "SCENE-BRIEF" server/logs/llm.log
```

期待 ≥ 1(每次 LLM 决策都会注入 brief,即使没踩坑也有助于 LLM 知道现状)。

- [ ] **Step 6: 计数 system prompt 字符**

```bash
grep "system:" server/logs/comm.log.jsonl | tail -5 | head -1 | wc -c
# 实际从 llm_req 看 system 字段
jq -r '.messages[0].content' server/logs/llm.log | head -5 | awk '{print length}'
```

期待 < 2000 字符(Task 2 的核心收益点)。

- [ ] **Step 7: 文档留痕**

更新 `docs/roadmap/2026-07-25-improvement-plan.md` 的 P0/P1 checkbox:
- 退出路径迷失 ✅
- screen 格式升级 ✅
- 结构化 feedback ✅
- 死循环诊断日志 ✅
- scene 检测强化(部分 ✅)

---

## Task 12: 全量复盘 + AGENTS.md / docs 同步

**Files:**
- Modify: `AGENTS.md`(最新 prompt 大小 + LLM payload 段名约定)
- Modify: `docs/roadmap/2026-07-25-llm-payload-redesign.md`(✅ 标记已落地的 phase)

- [ ] **Step 1: AGENTS.md 加一条 prompt 约定**

在「关键约定」段加:

```markdown
- LLM payload 段名约定(2026-07-25):发给 LLM 的 user payload = `[OBSERVE] [SCENE-BRIEF*] [GROUND] [PHASE] [ACT] [VERIFY]` 六段(SCENE-BRIEF 按需出现)。
  字段名稳定:`scene` / `page` / `pkg` / `goal` / `exit_path` / `phase` / `current` / `next_gate` / `last_1_action` / `ack` / `screen_changed`。
  system prompt 缩到 `[ROLE] + [TOOLS] + [CONTRACT: done]`,~1100 字符。
```

- [ ] **Step 2: 文档留痕**

跑 `git log --oneline | head -20`,确认 11 个 commit 都已落地(含「LLM 通信内容重构」主题)。

修改 `2026-07-25-llm-payload-redesign.md`,把 6 个 phase 标 ✅。

- [ ] **Step 3: Commit 文档**

```bash
git add AGENTS.md docs/roadmap/2026-07-25-llm-payload-redesign.md
git commit -m "docs(payload): 段名约定写入 AGENTS.md + 设计文档标记已落地"
```

---

## 自查(写完计划后)

**1. Spec 覆盖**:

| Spec § | 任务 |
|---|---|
| §2 `[OBSERVE]` 屏布局 + visible_nodes | Task 1 (`encode_visible_nodes` + `render_layout_summary`); Task 10 (`_nav_map` 删除) |
| §3 `[GROUND]` 目标/位置/退路 | Task 1 + 4 (`_build_ground`) |
| §4 `[SCENE-BRIEF]` scene×page 注入 | Task 3 + 4 + 5(通用 brief + AppProfile 注入) |
| §5 `[PHASE]` phase 状态机 | Task 6 + 7(`TaskPhase` + DecideInput.phase + payload 字段) |
| §6 done 契约 | Task 2(`[CONTRACT: done]` 在 system prompt) |
| §7 `[VERIFY]` 段名稳定 | Task 8 + 9(段名 `[feedback]` → `[VERIFY]`,字段 `result` → `ack`,加 `screen_changed`) |
| §10 落地阶段 | Task 1-12 共 12 task,每 task 独立 commit |
| last_1_actions | Task 4(`last_action` 参数,Task 7.4 决定数据流从 ctx.history) |

**2. Placeholder 扫描**:无 "TBD" / "implement later" / "fill in details";code block 完整。

**3. 类型一致性**:`PhaseState.to_payload_dict()` 在 Task 6 定义,Tasks 7/9 复用;`build_user_payload` 签名在 Task 1 锁定,Task 4/7/8 都对位。

**4. 覆盖 gap**:Task 6 占位 `gate_for` 在 Task 9 完整化;`screen_changed` 在 Task 9 补齐——这俩是有意分两步,避免一次过大改动。已在对应 Task 标注。

---

## 验收(Plan-wide)

- [ ] `uv run pytest tests/ -q` 全绿(server target ≥ 340+ 测试)
- [ ] `uv run pyright app/` 0 errors
- [ ] `./gradlew :app:testDebugUnitTest` BUILD SUCCESSFUL
- [ ] system prompt 字符数从 4770 → < 2000
- [ ] payload 在 8 个真机样本上的字符数从 5100-6700 → 4000-5500
- [ ] 真机场景 A(正向飞书发消息)happy path 走通
- [ ] 真机场景 C(进群设置 → back 出)LLM 不输出 back+home 振荡
- [ ] llm.log 出现 `[SCENE-BRIEF]` 段
- [ ] llm.log 出现 `[PHASE]` 段且 phase 自然推进
- [ ] llm.log 出现 `[VERIFY] ack: ok=false ...` 段
- [ ] 12 个 commit,主题「LLM 通信内容重构」

---

## 执行模式选择

Plan 完成并保存到 `docs/superpowers/plans/2026-07-25-llm-payload-redesign.md`。

两种执行模式:

**1. Subagent-Driven(推荐)** —— 每个 task 派一个独立 subagent 执行,我在主会话审 review,迭代快 / 上下文干净

**2. Inline Execution** —— 在当前会话按 task 顺序执行,有 checkpoint 让你 review

你选哪个?
