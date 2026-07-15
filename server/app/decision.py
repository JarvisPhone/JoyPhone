import json
import logging
import uuid

from app.llm import LLM
from app.protocol import Action, Node, Perception
from app.skill_cache import SkillCache
from app.skills import SkillLibrary


_SYSTEM_PROMPT = """你是一个 Android 手机操作代理的决策核心。给定当前屏幕的可交互元素列表(screen)、当前应用(pkg)、任务目标解析出的目标应用(target_pkg)、任务目标和历史操作，你要决定接下来执行的一批 UI 动作。

你必须只输出「文本指令」，每行一条，可以多行；不要输出 JSON、解释、思考过程、Markdown 代码块或任何额外文字。

合法指令(每行一条)：
- tap n          点击第 n 行元素(n 是 screen 里的行号)
- input n 文本    在第 n 行输入框输入「文本」(文本可含空格，取本行剩余内容)
- swipe up       滑动，方向可为 up|down|left|right
- back           返回键
- home           回到桌面
- home_first     回到桌面并归位到最左第一屏(打开应用前必先执行)
- next_page      在桌面向后翻一屏找应用图标
- wait 500       等待若干毫秒
- read           重新读取屏幕(信息不足以决策时用)
- done           任务已完成
- abort 原因      无法完成任务，放弃，并说明原因

批处理规则：你可以一次给出多行盲操作(如 home_first、next_page、swipe、back、wait)，最多以「一条 tap 或 input」收尾。系统只会执行到第一条 tap/input 为止，然后重新抓取屏幕再问你，所以 tap/input 之后不要再写别的指令。

输入里的 screen 是当前屏可交互元素列表，每行格式为 `[序号] 类型 "文本"`，类型为 input(输入框)/button(可点击)/text(纯文本)。tap/input 用行号 n 定位元素。

【重要·app 边界硬约束】
- 输入里会有两个关键字段：pkg(当前正在前台的应用 package)和 target_pkg(任务目标对应的应用 package，可能为空字符串表示任务与具体 app 无关)。
- 如果 target_pkg 非空 且 pkg != target_pkg：说明当前跑错了应用，你必须先输出 `back`(退出当前 app 的次级页)，然后 `home_first`，再 `read`，再 `tap` 目标 app 图标——禁止直接 tap 当前屏幕里的通知/磁贴/横幅跳到其他 app，那会把任务带偏。
- 如果 target_pkg 非空 且 pkg == target_pkg：正常推进任务。
- 如果 target_pkg 为空：无 app 约束，可以自由 tap。
- 出现「XX 有 N 条新消息」「XX 推荐」「XX 回复了你」类通知横幅/磁贴时，即使 clickable 也一律忽略，除非这条通知就是任务目标本身(如「去通知中心打开微信」)。

打开应用的流程：
1. 先 home_first 回到桌面第一屏
2. read 读取当前屏，在节点里找目标应用图标(按名称匹配)
3. 找到图标 -> tap 打开；没找到 -> next_page 翻到下一屏，再 read 继续找
4. 若某次 next_page 后历史记录里 atEnd 为 true 且仍没找到图标 -> abort，原因填「未找到应用<名称>」

【重要·负一屏识别】桌面最左侧的「负一屏」(又称小布建议/智能助手页)不是真正的应用桌面，上面的「XX 有 N 条通知」「XX 推荐」等磁贴不是应用图标，误点会进入错误的 app。识别特征：屏幕里出现「小布建议」「小布」等文字，或大量「...有...条通知」「为你推荐」类磁贴，一旦判断当前在负一屏，必须先 swipe right 向右滑动退出，回到真正的桌面第一屏后再找应用图标；绝不能在负一屏上 tap 任何磁贴。

【重要·tap 定位】tap n 用行号定位，系统会自动把该行节点解析为精确坐标点击，比文字匹配更可靠(避免误命中同名文字)。

示例(多行批处理)：
home_first
read

示例(收尾 tap)：
tap 5

示例(输入)：
input 3 张三

示例(跑错应用,回桌面重开目标 app)：
back
home_first
read
tap 12

信息不足时：
read"""


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

    id 是 _encode_nodes 的列表下标(对 capped nodes 而言),是唯一的节点引用键。
    raw_id 为空 / 非 int / 越界时返回 None。
    """
    raw_id = params.get("id")
    if raw_id is not None and str(raw_id).strip() != "":
        try:
            idx = int(str(raw_id).strip())
        except (ValueError, TypeError):
            idx = -1
        if 0 <= idx < len(nodes):
            return nodes[idx]
    return None


def _bounds_center(bounds) -> tuple[int, int] | None:
    if not bounds or len(bounds) != 4:
        return None
    left, top, right, bottom = bounds
    return (left + right) // 2, (top + bottom) // 2


_NOARG_OPS = {
    "back": "back",
    "home": "home",
    "home_first": "home_first_page",
    "next_page": "next_page",
    "read": "read_screen",
    "done": "done",
}


def parse_actions(text: str) -> list[dict]:
    """把 LLM 返回的纯文本指令(多行,每行一条)解析成结构化 spec 列表。

    纯函数,无副作用。语法按首个空格切「动词 + 参数」。
    空行 / 无法识别的动词 -> 跳过。返回的每个 dict 里所有值都是 str。
    """
    specs: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        verb, _, rest = line.partition(" ")
        rest = rest.strip()
        if verb == "tap":
            specs.append({"op": "tap", "id": rest.partition(" ")[0]})
        elif verb == "input":
            idx, _, txt = rest.partition(" ")
            specs.append({"op": "input", "id": idx.strip(), "text": txt.strip()})
        elif verb == "swipe":
            specs.append({"op": "swipe", "direction": rest.partition(" ")[0]})
        elif verb == "wait":
            specs.append({"op": "wait", "ms": rest.partition(" ")[0]})
        elif verb == "abort":
            specs.append({"op": "abort", "reason": rest})
        elif verb in _NOARG_OPS:
            specs.append({"op": _NOARG_OPS[verb]})
    return specs


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

    def _select_skill(self, goal: str, pkg: str) -> str | None:
        if self._skills is None:
            return None
        return self._skills.select(goal, pkg)

    def decide(
        self,
        goal: str,
        perception: Perception,
        skill_name: str | None,
        cursor: int,
        history: list[dict],
        target_pkg: str = "",
    ) -> list[Action]:
        step = self._cache_step(goal, perception, cursor)
        if step is not None:
            return [
                Action(actionId=str(uuid.uuid4()), op=step["op"], params=step.get("params", {}))
            ]

        if skill_name is None:
            skill_name = self._select_skill(goal, perception.pkg)

        if skill_name:
            step = self._skills.next_step(skill_name, perception.nodeTree, cursor)
            if step is not None:
                params = {k: str(v) for k, v in step.items() if k != "op"}
                return [Action(actionId=str(uuid.uuid4()), op=step["op"], params=params)]

        # pkg guard：若目标 app 已解析且与当前 pkg 不一致,直接强制回桌面重开,
        # 跳过 LLM(避免 LLM 看到通知/磁贴就 tap,跑飞)。
        if target_pkg and perception.pkg and perception.pkg != target_pkg:
            _diag = logging.getLogger("phoneagent.gateway")
            _diag.info(
                "[PKG_GUARD] current_pkg=%s target_pkg=%s -> forced home_first_page",
                perception.pkg, target_pkg,
            )
            return [Action(actionId=str(uuid.uuid4()), op="home_first_page", params={})]

        nodes = self._cap_nodes(perception.nodeTree)
        payload = {
            "goal": goal,
            "pkg": perception.pkg,
            "target_pkg": target_pkg,
            "screen": _encode_nodes(nodes),
            "history": history,
        }
        raw = self._llm.complete(
            system=_SYSTEM_PROMPT,
            user=json.dumps(payload, ensure_ascii=False),
        )
        _diag = logging.getLogger("phoneagent.gateway")
        _diag.info(
            "[FRAME] pkg=%s target_pkg=%s total_nodes=%d capped=%d cursor=%d goal=%s skill=%s",
            perception.pkg, target_pkg, len(perception.nodeTree), len(nodes), cursor, goal, skill_name,
        )

        specs = parse_actions(raw)
        if not specs:
            return [Action(actionId=str(uuid.uuid4()), op="read_screen", params={})]

        actions: list[Action] = []
        for spec in specs:
            op = spec["op"]
            params = {k: str(v) for k, v in spec.items() if k != "op"}
            if op in ("tap", "input"):
                target = _resolve_tap_node(params, nodes)
                if target is not None:
                    center = _bounds_center(target.bounds)
                    if center is not None:
                        params["x"] = str(center[0])
                        params["y"] = str(center[1])
                actions.append(Action(actionId=str(uuid.uuid4()), op=op, params=params))
                break  # 批处理截断：遇首个 tap/input 收尾，本批结束重抓帧
            actions.append(Action(actionId=str(uuid.uuid4()), op=op, params=params))
        return actions

    def _cap_nodes(self, nodes: list[Node]) -> list[Node]:
        if len(nodes) <= self.MAX_LLM_NODES:
            return nodes
        interactive = [n for n in nodes if n.clickable or n.editable]
        others = [n for n in nodes if not (n.clickable or n.editable)]
        capped = (interactive + others)[: self.MAX_LLM_NODES]
        keep = set(id(n) for n in capped)
        return [n for n in nodes if id(n) in keep]
