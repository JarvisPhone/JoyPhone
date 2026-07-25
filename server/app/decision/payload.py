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
        anc = ancestor_clickable[i] if i < len(ancestor_clickable) else False
        return bool(text and anc)

    out = []
    for i, n in enumerate(nodes):
        if not kept(i):
            continue
        if n.editable:
            t = "input"
        elif n.clickable:
            t = "button"
        else:
            anc = ancestor_clickable[i] if i < len(ancestor_clickable) else False
            t = "button" if anc else "label"
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
