"""决策引擎。

decide 永不返回 None:任何路径都无决策时回落 `Decision([read_screen], "llm")`。
决策顺序: cache.lookup -> bound_skill(cursor.state != "failed")next_step
-> pkg_guard -> LLM。

cursor 语义: cache/skill 命中下发的动作经端侧 ack ok 后由 handler 调
`cursor.advance()`(Task 11);verify_title FAIL 时 engine 内部 `cursor.fail()`
并同帧回落 LLM。
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass

from app.decision.cache import SkillCache
from app.decision.llm import LLM
from app.decision.pkg_guard import pkg_guard_action
from app.decision.skills import BoundSkill, SkillCursor
from app.decision.types import Decision
from app.decision.ui_inspect import detect_title, match_title
from app.protocol import Action, Node, Perception

_logger = logging.getLogger("phoneagent.decision")


@dataclass
class DecideInput:
    goal: str
    frame: Perception
    target_pkg: str
    cursor: SkillCursor
    bound_skill: BoundSkill | None
    guard: dict
    title_keywords: tuple[str, ...]


_SYSTEM_PROMPT = """你是一个 Android 手机操作代理的决策核心。给定当前屏幕的可交互元素列表(screen)、当前应用(pkg)、任务目标解析出的目标应用(target_pkg)、任务目标和历史操作，你要决定接下来执行的一批 UI 动作。

你必须只输出「文本指令」，每行一条，可以多行；不要输出 JSON、解释、思考过程、Markdown 代码块或任何额外文字。

合法指令(每行一条)：
- tap n          点击第 n 行元素(n 是 screen 里的行号)
- input n 文本    在第 n 行输入框输入「文本」(文本可含空格，取本行剩余内容)
- swipe up       滑动，方向可为 up|down|left|right
- back           返回键
- home           回到桌面
- wait 500       等待若干毫秒
- read           重新读取屏幕(信息不足以决策时用)
- done           [硬性语义·必读] 任务目标已达成。
                  四条件必须全部成立才输出 done:① pkg==target_pkg(在目标 app 内);
                  ② 当前屏顶部标题 == 目标群/联系人名(用 screen 第一行的标题节点文本核对);
                  ③ 最近一次 action 是「tap 发送按钮」,且 action.result.ok==true;
                  ④ 输入框已清空(代表消息真正发出,不是还在编辑中)。
                  一旦满足,只输出一行 done;禁止继续 tap 群设置、input 群名、swipe 探索;若继续,云端会强制 abort 并标记失败。
- abort 原因      无法完成任务，放弃，并说明原因

批处理规则：你可以一次给出多行盲操作(如 home、swipe、back、wait)，最多以「一条 tap 或 input」收尾。系统只会执行到第一条 tap/input 为止，然后重新抓取屏幕再问你，所以 tap/input 之后不要再写别的指令。

输入里的 screen 是当前屏可交互元素列表，每行格式为 `[序号] 类型 "文本"`，类型为 input(输入框)/button(可点击)/text(纯文本)。tap/input 用行号 n 定位元素。

【重要·app 边界硬约束】
- 输入里会有两个关键字段：pkg(当前正在前台的应用 package)和 target_pkg(任务目标对应的应用 package，可能为空字符串表示任务与具体 app 无关)。
- 如果 target_pkg 非空 且 pkg != target_pkg：说明当前跑错了应用，你必须先输出 `back`(退出当前 app 的次级页)，然后 `home`，再 `read`，再 `tap` 目标 app 图标——禁止直接 tap 当前屏幕里的通知/磁贴/横幅跳到其他 app，那会把任务带偏。
- 如果 target_pkg 非空 且 pkg == target_pkg：你**已经在目标 app 内**，绝不要输出 `home`，也不要用 `back`+`home` 退出当前 app。此时只需在 app 内推进任务：找不到目标会话/页面时，用搜索框输入名称搜索，或用 `swipe up`/`swipe down` 在列表内滚动查找；进错了子页（如进错群聊）用**单个 `back`** 回上一级列表继续找，禁止一路 back+home 退回桌面重来。
- 如果 target_pkg 为空：无 app 约束，可以自由 tap。
- 出现「XX 有 N 条新消息」「XX 推荐」「XX 回复了你」类通知横幅/磁贴时，即使 clickable 也一律忽略，除非这条通知就是任务目标本身(如「去通知中心打开微信」)。

打开应用的流程：
1. 先 home 回到桌面
2. read 读取当前屏，在节点里找目标应用图标(按名称匹配)
3. 找到图标 -> tap 打开；没找到 -> swipe left 翻到下一屏，再 read 继续找
4. 若连续多次 swipe left 后仍没找到图标 -> abort，原因填「未找到应用<名称>」

在目标 app 内找会话/联系人的流程(pkg == target_pkg 时)：
1. 优先用顶部搜索：tap 搜索框 -> input 目标名称 -> 在结果里 tap 匹配项。
2. 进入会话后，先核对页面顶部标题是否与目标会话名一致；不一致说明进错，输出单个 `back` 回上一级，换一个结果再试或重新搜索。
3. 反复 back 后仍找不到目标会话时，**必须先用顶部搜索框完整搜索一次目标名称**（tap 搜索框 -> input 目标名称 -> 等结果帧）；搜索+滚动都无果后才允许 abort，原因填「未找到会话<名称>」。未执行过搜索就直接 abort 属于违规。禁止用 home 退出 app。

【重要·负一屏识别】桌面最左侧的「负一屏」(又称小布建议/智能助手页)不是真正的应用桌面，上面的「XX 有 N 条通知」「XX 推荐」等磁贴不是应用图标，误点会进入错误的 app。识别特征：屏幕里出现「小布建议」「小布」等文字，或大量「...有...条通知」「为你推荐」类磁贴，一旦判断当前在负一屏，必须先 swipe right 向右滑动退出，回到真正的桌面第一屏后再找应用图标；绝不能在负一屏上 tap 任何磁贴。

【重要·tap 定位】tap n 用行号定位，系统会自动把该行节点解析为精确坐标点击，比文字匹配更可靠(避免误命中同名文字)。

示例(多行批处理)：
home
read

示例(收尾 tap)：
tap 5

示例(输入)：
input 3 张三

示例(仅当 pkg != target_pkg 即跑错应用时,回桌面重开目标 app)：
back
home
read
tap 12

信息不足时：
read

【idle 行为约束】当 target_pkg 为空字符串(说明还没收到用户的 task.request)时,任务尚未开始,这一阶段你只能输出 `wait 1000` 或 `read`,**禁止**输出 `done` / `abort` / 任何 tap / home,否则会立即结束会话。等待用户下发任务后再行动。
"""


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


def _read_screen_action() -> Action:
    return Action(actionId=str(uuid.uuid4()), op="read_screen", params={})


class DecisionEngine:
    MAX_LLM_NODES = 80

    def __init__(self, llm: LLM, cache: SkillCache | None = None,
                 escape_llm: LLM | None = None):
        self._llm = llm
        self._cache = cache
        self._escape_llm = escape_llm if escape_llm is not None else llm

    @property
    def cache(self) -> SkillCache | None:
        """只读暴露技能缓存,供任务层在任务完成时 learn(T11)。"""
        return self._cache

    def decide(self, d: DecideInput) -> Decision:
        cached = self._cache_step(d)
        if cached is not None:
            return Decision(actions=[cached], source="cache")

        if d.bound_skill is not None and d.cursor.state != "failed":
            skilled = self._skill_step(d)
            if skilled is not None:
                return skilled

        guarded = pkg_guard_action(d.frame, d.target_pkg, d.guard, self._escape_llm)
        if guarded is not None:
            return Decision(actions=guarded, source="pkg_guard")

        return self._llm_decide(d)

    def _cache_step(self, d: DecideInput) -> Action | None:
        if self._cache is None:
            return None
        entry = self._cache.get(d.goal, d.frame.pkg)
        if entry is None or d.cursor.index >= len(entry["steps"]):
            return None
        step = entry["steps"][d.cursor.index]
        match_text = step.get("params", {}).get("match_text", "")
        if match_text and not any(match_text in (n.text or "") for n in d.frame.nodeTree):
            return None  # 无法重定位 -> 回退
        return Action(
            actionId=str(uuid.uuid4()),
            op=step["op"],
            params=step.get("params", {}),
        )

    def _skill_step(self, d: DecideInput) -> Decision | None:
        skill = d.bound_skill
        if skill is None:
            return None
        step = skill.next_step(d.frame.nodeTree, d.cursor.index)
        if step is None:
            return None

        # verify_title 步:仅做标题校验。PASS 下发无副作用 read_screen 占位让
        # 端侧重抓帧(cursor 由 handler 在 ack ok 后推进);FAIL 标记 cursor
        # 失败并继续下行(本帧回落 LLM,下一帧跳过整条技能)。
        if step.get("op") == "verify_title":
            expected = step.get("expected_title") or ""
            current_title = detect_title(d.frame.nodeTree, d.title_keywords)
            if current_title and match_title(expected, current_title):
                _logger.info(
                    "[VERIFY_TITLE_PASS] skill=%s expected=%r current=%r",
                    skill.name, expected, current_title,
                )
                return Decision(actions=[_read_screen_action()], source="skill")
            _logger.warning(
                "[VERIFY_TITLE_FAIL] skill=%s expected=%r current=%r 回退 LLM 决策",
                skill.name, expected, current_title,
            )
            d.cursor.fail()
            return None

        params = {k: str(v) for k, v in step.items() if k != "op"}
        return Decision(
            actions=[Action(actionId=str(uuid.uuid4()), op=step["op"], params=params)],
            source="skill",
        )

    def _llm_decide(self, d: DecideInput) -> Decision:
        nodes = self._cap_nodes(d.frame.nodeTree)
        payload = {
            "goal": d.goal,
            "pkg": d.frame.pkg,
            "target_pkg": d.target_pkg,
            "screen": _encode_nodes(nodes),
        }
        raw = self._llm.complete(
            system=_SYSTEM_PROMPT,
            user=json.dumps(payload, ensure_ascii=False),
        )
        _diag = logging.getLogger("phoneagent.gateway")
        _diag.info(
            "[FRAME] pkg=%s target_pkg=%s total_nodes=%d capped=%d cursor=%d goal=%s skill=%s",
            d.frame.pkg, d.target_pkg, len(d.frame.nodeTree), len(nodes),
            d.cursor.index, d.goal,
            d.bound_skill.name if d.bound_skill is not None else None,
        )

        specs = parse_actions(raw)
        if not specs:
            return Decision(actions=[_read_screen_action()], source="llm")

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
        return Decision(actions=actions, source="llm")

    def _cap_nodes(self, nodes: list[Node]) -> list[Node]:
        if len(nodes) <= self.MAX_LLM_NODES:
            return nodes
        interactive = [n for n in nodes if n.clickable or n.editable]
        others = [n for n in nodes if not (n.clickable or n.editable)]
        capped = (interactive + others)[: self.MAX_LLM_NODES]
        keep = set(id(n) for n in capped)
        return [n for n in nodes if id(n) in keep]
