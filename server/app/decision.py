import json
import logging
import os
import time
import uuid

from app.llm import LLM
from app.protocol import Action, Node, Perception
from app.skill_cache import SkillCache
from app.skills import SkillLibrary


_SYSTEM_PROMPT = """你是一个 Android 手机操作代理的决策核心。给定当前屏幕的可交互元素列表(screen)、任务目标和历史操作，你必须决定「下一步」执行的单个 UI 动作。

你必须只输出一个 JSON 对象，不要输出任何解释、思考过程、Markdown 代码块或额外文字。

JSON 格式：{"op": "<操作类型>", "params": {<参数键值对，值必须为字符串>}}

合法的 op 取值及其含义：
- tap: 点击某个节点。params: {"match_text": "节点文本"} 或 {"id": "节点id"}
- input: 在输入框输入文本。params: {"text": "要输入的内容", "match_text": "输入框附近文本(可选)"}
- swipe: 滑动。params: {"direction": "up|down|left|right"}
- back: 返回键。params: {}
- home: 回到桌面。params: {}
- home_first_page: 回到桌面并归位到最左第一屏(打开应用前必先执行)。params: {}
- next_page: 在桌面向后翻一屏找应用图标。params: {}
- wait: 等待。params: {"ms": "毫秒数"}
- read_screen: 重新读取屏幕(当信息不足以决策时用)。params: {}
- done: 任务已完成。params: {}
- abort: 无法完成任务，放弃。params: {"reason": "原因"}

输入里的 screen 是当前屏可交互元素列表，每行格式为 `[序号] 类型 "文本"`，类型为 input(输入框)/button(可点击)/text(纯文本)。tap/input 的 match_text 填元素文本，也可用 {"id": "序号"} 指定行号。

打开应用的流程：
1. 先 home_first_page 回到桌面第一屏
2. read_screen 读取当前屏，在节点里找目标应用图标(按名称匹配)
3. 找到图标 -> tap 打开；没找到 -> next_page 翻到下一屏，再 read_screen 继续找
4. 若某次 next_page 后返回的历史记录里 atEnd 为 true 且仍没找到图标 -> abort，reason 填「未找到应用<名称>」

【重要·负一屏识别】桌面最左侧的「负一屏」(又称小布建议/智能助手页)不是真正的应用桌面，上面的「XX 有 N 条通知」「XX 推荐」等磁贴不是应用图标，误点会进入错误的 app。识别特征：屏幕里出现「小布建议」「小布」等文字，或大量「...有...条通知」「为你推荐」类磁贴。一旦判断当前在负一屏，必须先 swipe direction=right 向右滑动退出，回到真正的桌面第一屏后再找应用图标；绝不能在负一屏上 tap 任何磁贴。

【重要·tap 定位】优先用 {"id": "序号"} 指定要点击的行号，系统会自动把该节点解析为精确坐标点击，比 match_text 子串匹配更可靠(避免误命中同名文字)。

示例：
看到搜索框 -> {"op": "input", "params": {"text": "张三", "match_text": "搜索"}}
信息不足 -> {"op": "read_screen", "params": {}}"""


def _node_type(node: Node) -> str:
    if node.editable:
        return "input"
    if node.clickable:
        return "button"
    return "text"


def _encode_nodes(nodes: list[Node]) -> str:
    lines = []
    for i, n in enumerate(nodes):
        label = (n.text or n.desc or "").strip()
        lines.append(f'[{i}] {_node_type(n)} "{label}"')
    return "\n".join(lines)


def _resolve_tap_node(params: dict, nodes: list[Node]) -> Node | None:
    """把 LLM 的 tap 参数还原为被选中的 Node。

    id 是 _encode_nodes 的列表下标(对 capped nodes 而言)；
    match_text 匹配节点 text 或 desc 的子串。找不到返回 None。
    """
    raw_id = params.get("id")
    if raw_id is not None and str(raw_id).strip() != "":
        try:
            idx = int(str(raw_id).strip())
        except (ValueError, TypeError):
            idx = -1
        if 0 <= idx < len(nodes):
            return nodes[idx]
    match_text = str(params.get("match_text", "")).strip()
    if match_text:
        for n in nodes:
            if match_text in (n.text or "") or match_text in (n.desc or ""):
                return n
    return None


def _bounds_center(bounds) -> tuple[int, int] | None:
    if not bounds or len(bounds) != 4:
        return None
    left, top, right, bottom = bounds
    return (left + right) // 2, (top + bottom) // 2


def encode_nodes_debug(nodes: list[Node]) -> str:
    """诊断用：完整打印每帧屏节点明细(行号/类型/text/desc/clickable/bounds/端侧id)。"""
    lines = []
    for i, n in enumerate(nodes):
        lines.append(
            f'[{i}] {_node_type(n)} text={n.text!r} desc={n.desc!r} '
            f'clickable={n.clickable} bounds={n.bounds} nid={n.id!r}'
        )
    return "\n".join(lines) if lines else "(empty)"


class DecisionEngine:
    MAX_LLM_NODES = 80

    def __init__(self, llm: LLM, skills: SkillLibrary, cache: SkillCache | None = None):
        self._llm = llm
        self._skills = skills
        self._cache = cache

    def _cache_step(self, goal: str, perception: Perception, cursor: int) -> dict | None:
        if self._cache is None:
            return None
        entry = self._cache.get(goal, perception.pkg)
        if entry is None or cursor >= len(entry["steps"]):
            return None
        step = entry["steps"][cursor]
        match_text = step.get("params", {}).get("match_text", "")
        if match_text and not any(match_text in (n.text or "") for n in perception.nodeTree):
            return None  # 无法重定位 -> 回退
        return step

    def decide(
        self,
        goal: str,
        perception: Perception,
        skill_name: str | None,
        cursor: int,
        history: list[dict],
    ) -> Action:
        step = self._cache_step(goal, perception, cursor)
        if step is not None:
            return Action(actionId=str(uuid.uuid4()), op=step["op"], params=step.get("params", {}))

        if skill_name:
            step = self._skills.next_step(skill_name, perception.nodeTree, cursor)
            if step is not None:
                params = {k: v for k, v in step.items() if k != "op"}
                return Action(actionId=str(uuid.uuid4()), op=step["op"], params=params)

        nodes = self._cap_nodes(perception.nodeTree)
        payload = {
            "goal": goal,
            "screen": _encode_nodes(nodes),
            "history": history,
        }
        raw = self._llm.complete(
            system=_SYSTEM_PROMPT,
            user=json.dumps(payload, ensure_ascii=False),
        )
        _diag = logging.getLogger("phoneagent.gateway")
        _diag.info(
            "[FRAME] pkg=%s total_nodes=%d capped=%d cursor=%d goal=%s",
            perception.pkg, len(perception.nodeTree), len(nodes), cursor, goal,
        )
        for _i, _n in enumerate(nodes):
            _diag.info(
                "[NODE] idx=%d endId=%s type=%s text=%r desc=%r clickable=%s bounds=%s",
                _i, _n.id, _node_type(_n), _n.text, _n.desc, _n.clickable, _n.bounds,
            )
        _diag.info("[LLM-SCREEN-SENT]\n%s", payload["screen"])
        _diag.info("[LLM-RAW-RETURN] %r", raw)
        # 【调试插桩】把这一帧的全部原始数据 dump 到独立文件，供人工完整审阅。
        try:
            _dump = {
                "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                "goal": goal,
                "pkg": perception.pkg,
                "activity": perception.activity,
                "cursor": cursor,
                "total_nodes": len(perception.nodeTree),
                "capped_nodes": len(nodes),
                "history": history,
                # ① 端侧识别到的完整节点（含端侧稳定 id / bounds 绝对坐标 / 全部字段）
                "nodes_raw": [
                    {
                        "idx": i,
                        "endId": n.id,
                        "type": _node_type(n),
                        "text": n.text,
                        "desc": n.desc,
                        "className": getattr(n, "className", None),
                        "clickable": n.clickable,
                        "editable": n.editable,
                        "bounds": n.bounds,
                    }
                    for i, n in enumerate(nodes)
                ],
                # ② 发送给 LLM 的完整内容（system + user payload 原文）
                "llm_request": {
                    "system": _SYSTEM_PROMPT,
                    "user": json.dumps(payload, ensure_ascii=False),
                    "screen_encoded": payload["screen"],
                },
                # ③ LLM 的原始回复
                "llm_raw_return": raw,
            }
            _dump_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
            os.makedirs(_dump_dir, exist_ok=True)
            _dump_path = os.path.join(_dump_dir, "frame_dump.json")
            with open(_dump_path, "a", encoding="utf-8") as _fp:
                _fp.write(json.dumps(_dump, ensure_ascii=False, indent=2))
                _fp.write("\n\n===== FRAME END =====\n\n")
            _diag.info("[FRAME-DUMP] 已写入 %s", _dump_path)
        except Exception as _e:  # 调试插桩不应影响主流程
            _diag.warning("[FRAME-DUMP] 写入失败: %s", _e)
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return Action(actionId=str(uuid.uuid4()), op="read_screen", params={})
        if not isinstance(data, dict) or "op" not in data:
            return Action(actionId=str(uuid.uuid4()), op="read_screen", params={})
        op = data["op"]
        params = dict(data.get("params", {}))
        if op == "tap":
            target = _resolve_tap_node(params, nodes)
            if target is not None:
                idx = next((i for i, n in enumerate(nodes) if n is target), -1)
                center = _bounds_center(target.bounds)
                _diag.info(
                    "[TAP-RESOLVE] llm_params=%s -> picked idx=%d endId=%s "
                    "text=%r desc=%r bounds=%s center=%s",
                    dict(data.get("params", {})), idx, target.id,
                    target.text, target.desc, target.bounds, center,
                )
                if center is not None:
                    params["x"] = str(center[0])
                    params["y"] = str(center[1])
            else:
                _diag.info(
                    "[TAP-RESOLVE] llm_params=%s -> picked=NONE (端侧回退match_text)",
                    dict(data.get("params", {})),
                )
        _diag.info("[ACTION] op=%s final_params=%s", op, params)
        return Action(actionId=str(uuid.uuid4()), op=op, params=params)

    def _cap_nodes(self, nodes: list[Node]) -> list[Node]:
        if len(nodes) <= self.MAX_LLM_NODES:
            return nodes
        interactive = [n for n in nodes if n.clickable or n.editable]
        others = [n for n in nodes if not (n.clickable or n.editable)]
        capped = (interactive + others)[: self.MAX_LLM_NODES]
        keep = set(id(n) for n in capped)
        return [n for n in nodes if id(n) in keep]