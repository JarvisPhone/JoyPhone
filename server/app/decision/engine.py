"""决策引擎。

decide 永不返回 None:任何路径都无决策时回落 `Decision([read_screen], "llm")`。
决策顺序: cache.lookup -> bound_skill(cursor.state != "failed")next_step
-> pkg_guard -> LLM。

cursor 语义: cache/skill 命中下发的动作经端侧 ack ok 后由 handler 调
`cursor.advance()`(Task 11);verify_title FAIL 时 engine 内部 `cursor.fail()`
并同帧回落 LLM。
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from app.decision.cache import SkillCache, bind_params
from app.decision.exit_hint import exit_hint
from app.decision.app_page import AppPage, detect_app_page
from app.decision.llm import LLM
from app.decision.payload import build_system_prompt, build_user_payload, encode_visible_nodes, render_layout_summary
from app.decision.pkg_guard import pkg_guard_action
from app.decision.skills import BoundSkill, SkillCursor
from app.decision.types import Decision
from app.decision.ui_inspect import detect_title, match_title
from app.infra.config import Config
from app.decision.pkg_guard import Scene, detect_scene
from app.protocol import Action, Node, Perception
from app.scenario.phase import PhaseState

_logger = logging.getLogger("phoneagent.decision")


def _ui_profile_for_pkg(pkg: str) -> "AppProfile | None":
    """按 pkg 查 L2 AppProfile;未注册返回 None。

    profile 注册表 scenario/profiles.py 持有 ALL_PROFILES,
    内部已 import。Task 5 引入,避免每次 _llm_decide 重新 loop。
    """
    from app.scenario.profiles import ALL_PROFILES
    if not pkg:
        return None
    for profile in ALL_PROFILES:
        if profile.pkg == pkg:
            return profile
    return None


# 仅为类型提示:避免 forward reference 字符串在 pyright 下报「未定义」错误。
from app.scenario.base import AppProfile  # noqa: E402


@dataclass
class DecideInput:
    goal: str
    frame: Perception
    target_pkg: str
    cursor: SkillCursor
    bound_skill: BoundSkill | None
    guard: dict
    title_keywords: tuple[str, ...]
    # 场景参数绑定(如 {"contact": "张三"}),回放 cache 步骤时绑定 {placeholder}
    bindings: dict | None = None
    # cache 查询上下文:入口状态分类后由任务层给出(如 "pkg|target_chat"),
    # 缺省回落 frame.pkg;仅在目标 app 内才有值
    cache_context: str = ""
    # 回放熔断后本场禁用 cache(同一步连续 ack 失败)
    cache_disabled: bool = False
    # LLM 反馈通道(一次性):上一条指令的执行失败/策略拦截/expect 判定结果;
    # 非空才进 payload,空表示上一条成功
    feedback: str = ""
    # 任务阶段状态(Task 7 接入):None 表示无 phase(下层会用占位符兜底),
    # 设置时 _llm_decide 把 phase 内容填到 [PHASE] 段。
    phase: PhaseState | None = None


_NOTIF_SUBTILE_RE = __import__("re").compile(r"有\s*\d+\s*条\s*(?:通知|消息|推荐|新动态|未读)")


def _node_type(node: Node, ancestor_clickable: bool = False) -> str:
    """返回 LLM 视角的节点类型(4 态)。

    - input: 可编辑输入框
    - button: 可点击
    - label: clickable=false 的非编辑装饰元素(通知磁贴/icon 旁文字等),
      LLM 不应 tap 这些节点
    - text: 不可交互的纯展示文本(text/desc 都空但 rid 有语义)

    例外(launcher widget 子入口判别):
    ColorOS 的小布建议/负一屏卡片常把"飞书/微信/淘宝"等子项做成
    clickable=false 的 ViewGroup(ViewGroup className、含 "XX 有 N 条通知" 文案),
    但祖先是 clickable=true 的卡片容器,点坐标落到卡片内即可触发子项入口。
    原生规则会把它标成 label,LLM 因名字含"飞书"误以为是图标去 tap;
    显式标 button 让 LLM 知道「这是可点的,放心 tap」。
    """
    if node.editable:
        return "input"
    if node.clickable:
        return "button"
    text = (node.text or node.desc or "").strip()
    if text and ancestor_clickable and _NOTIF_SUBTILE_RE.search(text):
        return "button"
    if text:
        return "label"
    return "text"


_SCENE_LABELS: dict[Scene, str] = {
    Scene.HOME: "launcher.home",
    Scene.MINUS_ONE: "launcher.minus_one",
    Scene.NOTIFICATION: "systemui.notification",
    Scene.CONTROL_CENTER: "systemui.control_center",
    Scene.IN_APP: "app",
    Scene.LOCK_SCREEN: "lock_screen",
    Scene.RECENT_APPS: "recent_apps",
    Scene.UNKNOWN: "unknown",
}

_APP_PAGE_LABELS: dict[AppPage, str] = {
    AppPage.INBOX_LIST: "app.inbox_list",
    AppPage.CHAT: "app.chat",
    AppPage.CONTACT_INFO: "app.contact_info",
    AppPage.GROUP_INFO: "app.group_info",
    AppPage.SETTINGS: "app.settings",
    AppPage.SEARCH: "app.search",
    AppPage.UNKNOWN: "app.unknown",
}


def _scene_label(frame: Perception) -> str:
    """Scene 枚举 → LLM 可读标签。

    标签形如 "主类.子类":主类指明这是哪一类系统界面(launcher/systemui/app),
    子类说明它的状态。LLM 据此直接判断当前位置,不用从节点文字反推。
    """
    return _SCENE_LABELS.get(detect_scene(frame), "unknown")


def _app_page_label(frame: Perception) -> str:
    """App 内页型标签(scene=app 时才有值,其它场景返回 "n/a")。

    配合 _scene_label 一起给 LLM:scene 回答「顶层在哪」,page 回答「app 内是
    列表/聊天/设置等」。这是「进了二级页面出不来」的根因修补——
    LLM 拿到 page=app.chat 就知道现在在聊天页,需要 back 回列表,
    而不是 back+home 退回桌面。
    """
    scene = detect_scene(frame)
    if scene != Scene.IN_APP:
        return "n/a"
    return _APP_PAGE_LABELS.get(detect_app_page(frame), _APP_PAGE_LABELS[AppPage.UNKNOWN])


def _rid_tail(rid: str | None) -> str:
    """rid 末段(锚点匹配用,保留原始下划线):com.x:id/btn_send -> "btn_send"。"""
    if not rid:
        return ""
    return rid.rsplit("/", 1)[-1].strip()


def _rid_label(rid: str | None) -> str:
    """rid 末段转可读标签。

    com.ss.android.lark:id/iv_download_image -> "iv download image"
    大量节点(图片查看器/图标按钮)text/desc 全空但 rid 自带语义,
    丢掉等于把 LLM 的眼睛蒙上。
    """
    if not rid:
        return ""
    return rid.rsplit("/", 1)[-1].replace("_", " ").strip()


def _build_ancestor_clickable(nodes: list[Node]) -> dict[int, bool]:
    """返回 {节点索引 -> 其祖先链(含自身)中是否有 clickable=true}。

    用于 launcher widget 子入口判别("XX 有 N 条通知" 且祖先有可点容器
    ⇒ 改标 button,否则 LLM 误以为「fly book 是 label 不可 tap」)。
    按 bounds 父子关系构建(Android dumpsys 含完整唯一 id,bounds 嵌套天然
    形成树)。
    """
    if not nodes:
        return {}

    def area(b: tuple[int, int, int, int] | None) -> int:
        if not b or len(b) != 4:
            return -1
        _, _, r, bot = b
        return max(0, r) * max(0, bot)

    ordered = sorted(range(len(nodes)), key=lambda i: area(nodes[i].bounds), reverse=True)
    parent: dict[int, int] = {}
    for i in ordered:
        b = nodes[i].bounds
        if not b or len(b) != 4:
            continue
        l, t, r, bot = b
        for j in ordered:
            if i == j:
                continue
            pb = nodes[j].bounds
            if not pb or len(pb) != 4:
                continue
            pl, pt, pr, pbot = pb
            if pl <= l and pt <= t and pr >= r and pbot >= bot and (pr - pl) * (pbot - pt) > (r - l) * (bot - t):
                parent[i] = j
                break
    anc: dict[int, bool] = {}
    for i in range(len(nodes)):
        seen = {i}
        cur = i
        val = nodes[i].clickable
        while parent.get(cur) is not None and parent[cur] not in seen:
            cur = parent[cur]
            seen.add(cur)
            if nodes[cur].clickable:
                val = True
                break
        anc[i] = val
    return anc


def _encode_nodes(nodes: list[Node], ancestor_clickable: list[bool] | None = None) -> str:
    lines = []
    anc = ancestor_clickable if ancestor_clickable is not None else [False] * len(nodes)
    for i, n in enumerate(nodes):
        label = (n.text or n.desc or "").strip() or _rid_label(n.viewIdResourceName)
        lines.append(f'[{i}] {_node_type(n, anc[i] if i < len(anc) else False)} "{label}"')
    return "\n".join(lines)


def _anchor_occurrence(target: Node, nodes: list[Node]) -> int | None:
    """同名锚点在可交互节点中出现多次时,返回 target 的 0 基序号;唯一则 None。

    与端侧 rid 一致性约束同步:只统计「标签相同且 rid 尾段一致」的节点,
    保证 occurrence 双端语义对齐(同名不同 rid 是另一个节点,不计入)。
    """
    label = (target.text or target.desc or "").strip()
    if not label:
        return None
    rid_tail = _rid_tail(target.viewIdResourceName)
    same = [n for n in nodes if (n.clickable or n.editable)
            and (n.text or n.desc or "").strip() == label
            and (not rid_tail or _rid_tail(n.viewIdResourceName) == rid_tail)]
    if len(same) <= 1:
        return None
    for i, n in enumerate(same):
        if n is target:
            return i
    return None


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


def _encoded_label(n: Node) -> str:
    """与 _encode_nodes 一致的节点标签(text/desc -> rid 可读标签兑底)。"""
    return (n.text or n.desc or "").strip() or _rid_label(n.viewIdResourceName)


def _resolve_text_node(label: str, nodes: list[Node]) -> Node | None:
    """按 LLM 的文本锚点还原 Node:与编码标签精确相等且唯一才返回。

    LLM 看到的是编码标签(如 rid 兑底的 "btn send"),直接透传给端侧会
    与原始 rid(btn_send)空格/下划线不符;先在这里还原成真实节点,
    才能补全 match_rid 等端侧可用的锚点。多命中返回 None(端侧判 ambiguous)。
    """
    matches = [n for n in nodes if _encoded_label(n) == label]
    return matches[0] if len(matches) == 1 else None


_NOARG_OPS = {
    "back": "back",
    "home": "home",
    "read": "read_screen",
    "done": "done",
    "press_enter": "press_enter",
    "open_notifications": "open_notifications",
    "open_quick_settings": "open_quick_settings",
}


def parse_actions(text: str) -> list[dict]:
    """把 LLM 返回的纯文本指令(多行,每行一条)解析成结构化 spec 列表。

    纯函数,无副作用。语法按首个空格切「动词 + 参数」。
    tap 支持两种定位:`tap 5`(行号)或 `tap "发送"`(文本锚点,引号可省——
    首参数非纯数字即视为文本)。文本锚点没有序号转录错误面(真机事故:
    LLM 把 tap 66 写成 tap 46 点进群设置),语义清晰的元素应优先用文本。
    longpress 沿用 tap 的两种定位方式。
    空行 / 无法识别的动词 -> 跳过。返回的每个 dict 里所有值都是 str。
    """
    specs: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        verb, _, rest = line.partition(" ")
        rest = rest.strip()
        if verb in ("tap", "longpress"):
            if rest[:1] in ('"', "'"):
                quote = rest[0]
                end = rest.find(quote, 1)
                target = rest[1:end] if end > 0 else rest[1:]
            else:
                target = rest.partition(" ")[0]
            target = target.strip()
            if not target:
                continue
            spec_op = verb  # "tap" 或 "longpress"
            if target.isdigit():
                specs.append({"op": spec_op, "id": target})
            else:
                specs.append({"op": spec_op, "match_text": target})
        elif verb == "expect":
            # 断言指令:`expect title "X"` / `expect pkg "com.x"` / `expect "文本"`
            # (首参数非 title/pkg 则整体为文本)。云端机械求值,不下发设备。
            if rest[:1] in ('"', "'"):
                quote = rest[0]
                end = rest.find(quote, 1)
                value = rest[1:end] if end > 0 else rest[1:]
                specs.append({"op": "expect", "kind": "text", "value": value})
            else:
                head, _, tail = rest.partition(" ")
                if head in ("title", "pkg"):
                    specs.append({"op": "expect", "kind": head,
                                  "value": tail.strip().strip('"\'')})
                else:
                    specs.append({"op": "expect", "kind": "text",
                                  "value": rest.strip('"\'')})
        elif verb == "input":
            idx, _, txt = rest.partition(" ")
            specs.append({"op": "input", "id": idx.strip(), "text": txt.strip()})
        elif verb == "swipe":
            specs.append({"op": "swipe", "direction": rest.partition(" ")[0]})
        elif verb == "scroll_to":
            # scroll_to top|bottom —— 端侧 SwipeHelper 反复 swipe 直到屏不再变或次数上限
            direction = rest.partition(" ")[0].strip().lower()
            if direction in ("top", "bottom"):
                specs.append({"op": "scroll_to", "direction": direction})
        elif verb == "wait":
            specs.append({"op": "wait", "ms": rest.partition(" ")[0]})
        elif verb == "abort":
            specs.append({"op": "abort", "reason": rest})
        elif verb in _NOARG_OPS:
            specs.append({"op": _NOARG_OPS[verb]})
    return specs


def _evaluate_expect(spec: dict, d: DecideInput) -> str:
    """云端机械求值 expect 断言,返回单行中文判定(进 meta["feedback"])。

    expect 从不下发设备:核查是认知操作,云端有帧有 detect_title,
    零副作用给出确定性答案——LLM 不该用 tap 表达核查(真机五轮事故)。
    """
    kind = spec.get("kind", "text")
    value = spec.get("value", "")
    if kind == "title":
        current = detect_title(d.frame.nodeTree, d.title_keywords)
        if current is None:
            return 'expect 判定 FAIL:当前页无法识别标题'
        if match_title(value, current):
            return 'expect 判定 PASS:title=="%s"' % current
        return 'expect 判定 FAIL:标题实际是 "%s"' % current
    if kind == "pkg":
        if d.frame.pkg == value:
            return 'expect 判定 PASS:pkg=="%s"' % value
        return 'expect 判定 FAIL:当前 pkg=%s' % d.frame.pkg
    hit = any(value in _encoded_label(n) for n in d.frame.nodeTree)
    if hit:
        return 'expect 判定 PASS:存在 "%s"' % value
    return 'expect 判定 FAIL:不存在 "%s"' % value


def _read_screen_action() -> Action:
    return Action(actionId=str(uuid.uuid4()), op="read_screen", params={})


class DecisionEngine:
    MAX_LLM_NODES = 80

    def __init__(self, llm: LLM, cache: SkillCache | None = None,
                 escape_llm: LLM | None = None, replay_enabled: bool = True):
        self._llm = llm
        self._cache = cache
        self._escape_llm = escape_llm if escape_llm is not None else llm
        # 记忆回放(cache/skill)总开关:LLM 链路未稳定前由 Config.REPLAY_ENABLED 关闭
        self._replay_enabled = replay_enabled

    @property
    def cache(self) -> SkillCache | None:
        """只读暴露技能缓存,供任务层在任务完成时 learn(T11)。"""
        return self._cache

    def decide(self, d: DecideInput) -> Decision:
        if self._replay_enabled:
            cached = self._cache_step(d)
            if cached is not None:
                return Decision(actions=[cached], source="cache")

            if d.bound_skill is not None and d.cursor.state != "failed" \
                    and d.cursor.misses < Config.SKILL_MAX_MISSES:
                skilled = self._skill_step(d)
                if skilled is not None:
                    return skilled

        guarded = pkg_guard_action(d.frame, d.target_pkg, d.guard, self._escape_llm)
        if guarded is not None:
            return Decision(actions=guarded, source="pkg_guard")

        return self._llm_decide(d)

    def _cache_step(self, d: DecideInput) -> Action | None:
        if self._cache is None or d.cache_disabled:
            return None
        entry = self._cache.get(d.goal, d.cache_context or d.frame.pkg)
        if entry is None or d.cursor.index >= len(entry["steps"]):
            return None
        step = entry["steps"][d.cursor.index]
        params = bind_params(step.get("params", {}), d.bindings or {})
        if params is None:
            _logger.info("[CACHE_UNBOUND] 占位符无法绑定,放弃本次回放")
            return None
        anchor = params.get("match_text", "")
        if anchor and not any(
            anchor in (n.text or "") or anchor in (n.desc or "")
            for n in d.frame.nodeTree
        ):
            return None  # 无法重定位 -> 回退
        return Action(
            actionId=str(uuid.uuid4()),
            op=step["op"],
            params=params,
        )

    def _skill_step(self, d: DecideInput) -> Decision | None:
        skill = d.bound_skill
        if skill is None:
            return None
        step = skill.next_step(d.frame.nodeTree, d.cursor.index)
        if step is None:
            d.cursor.misses += 1
            if d.cursor.misses >= Config.SKILL_MAX_MISSES:
                _logger.warning(
                    "[SKILL_DISABLED] skill=%s 连续 %d 帧无节点匹配,本场禁用",
                    skill.name, d.cursor.misses,
                )
            return None
        d.cursor.misses = 0

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
        anc_map = _build_ancestor_clickable(d.frame.nodeTree)
        ancestor = [anc_map.get(id(n), False) for n in nodes]

        scene = detect_scene(d.frame)
        scene_label = _scene_label(d.frame)
        page_label = _app_page_label(d.frame)  # "n/a" outside IN_APP
        page_enum = detect_app_page(d.frame) if scene == Scene.IN_APP else AppPage.UNKNOWN
        hint = exit_hint(scene, page_enum)
        nav_map = render_layout_summary(nodes)
        screen_text = _encode_nodes(nodes, ancestor)

        # === [NODE_TREE] 节点树分布打点 ===
        # 每帧决策时打一行,展示 cap 后节点的价值分布,供真机联调时对比:
        # - total/original:cap 后/前节点数
        # - score3/2/1/0: 各评分档节点数
        # - capped: 原始超过上限则为 yes
        # 联调时 grep "NODE_TREE" 快速评估过滤效果。
        _diag = logging.getLogger("phoneagent.gateway")
        total_orig = len(d.frame.nodeTree)
        capped = total_orig > self.MAX_LLM_NODES
        s3 = s2 = s1 = s0 = 0
        for n in nodes:
            has_text = bool((n.text or "").strip() or (n.desc or "").strip())
            interactive = n.clickable or n.editable
            if interactive and has_text:
                s3 += 1
            elif not interactive and has_text:
                s2 += 1
            elif interactive:
                s1 += 1
            else:
                s0 += 1
        _diag.info(
            "[NODE_TREE] total=%d cap=%d capped=%s s3=%d(交互+文字) s2=%d(文字) s1=%d(交互) s0=%d(装饰)",
            total_orig, len(nodes), capped, s3, s2, s1, s0,
        )

        # 6 段 payload:[OBSERVE] [SCENE-BRIEF*] [GROUND] [PHASE] [ACT] [VERIFY]
        # scene_brief 按 (scene, page) 注入,AppProfile.llm_brief 由 Task 5 注入。
        from app.decision.scene_briefs import brief_for as _generic_brief
        generic_brief = _generic_brief(scene, page_enum)
        # AppProfile.llm_brief:飞书等 app 专属 brief,与通用 brief 拼接。
        app_brief = ""
        if d.target_pkg:
            profile = _ui_profile_for_pkg(d.target_pkg)
            app_brief = profile.llm_brief if profile is not None else ""
        if generic_brief and app_brief:
            scene_brief = generic_brief + "\n" + app_brief
        elif app_brief:
            scene_brief = app_brief
        else:
            scene_brief = generic_brief
        screen_text = encode_visible_nodes(nodes, ancestor)

        # last_1_action 由 handlers 层写入(暂用空)
        last_action = getattr(d, "last_action", None)

        # phase:t7 接入:从 d.phase 读 PhaseState,填到 payload 字段。
        # d.phase 为 None 时(尚未接入任务层)用 "(phase not yet wired)" 占位,
        # 否则从 PhaseState.to_payload_dict() 取稳定字段。
        if d.phase is not None:
            phase_dict = d.phase.to_payload_dict()
            phase_label = phase_dict["phase"]
            phase_current = f"step {phase_dict['current_step_index']}"
        else:
            phase_label = "(phase not yet wired)"
            phase_current = ""
        # next_gate:t9 由 SendMessagePack.gate_for(phase, frame, ctx) 完整给出,t7 placeholder
        phase_next_gate = "(see scene hints above; use expect to verify progress)"
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
            phase_label=phase_label,
            phase_current=phase_current,
            phase_next_gate=phase_next_gate,
        )

        raw = self._llm.complete(system=build_system_prompt(), user=user_text)

        # === LLM_DECIDE 结构化日志 ===
        # 一次性把决策链路所有关键维度打一行,真机联调「同一个意图重复多少帧」直接 grep 数。
        # 日志格式(非 JSON,字段顺序稳定便于脚本切片):
        #   [LLM_DECIDE] seq=X | pkg=Y | scene=Z | page=W | cursor=N/M |
        #     nodes=T(c=N,e=N) | llm_out=... | ...
        clickable = sum(1 for n in nodes if n.clickable)
        editable = sum(1 for n in nodes if n.editable)
        cursor_step = getattr(d.cursor, "index", 0)
        llm_out = raw.replace("\n", " ⏎ ")[:200]
        _diag.info(
            "[LLM_DECIDE] pkg=%s scene=%s page=%s "
            "nodes=%d(c=%d,e=%d) cursor=%d "
            "feedback=%s llm_out=%s",
            d.frame.pkg, scene_label, page_label,
            len(nodes), clickable, editable,
            cursor_step,
            "yes" if d.feedback else "no",
            llm_out,
        )
        _diag.info(
            "[FRAME] pkg=%s target_pkg=%s total_nodes=%d capped=%d cursor=%d goal=%s skill=%s",
            d.frame.pkg, d.target_pkg, len(d.frame.nodeTree), len(nodes),
            cursor_step, d.goal,
            d.bound_skill.name if d.bound_skill is not None else None,
        )

        specs = parse_actions(raw)
        if not specs:
            return Decision(actions=[_read_screen_action()], source="llm")

        actions: list[Action] = []
        for spec in specs:
            op = spec["op"]
            if op == "expect":
                # 断言求值并终止批次:结果经 meta 反馈,随下一帧 payload 送达 LLM
                result = _evaluate_expect(spec, d)
                return Decision(actions=[_read_screen_action()], source="llm",
                                meta={"feedback": result})
            params = {k: str(v) for k, v in spec.items() if k != "op"}
            if op in ("tap", "input", "longpress"):
                target = _resolve_tap_node(params, nodes)
                if target is None and params.get("match_text"):
                    target = _resolve_text_node(params["match_text"], nodes)
                if target is not None:
                    anchor = (target.text or target.desc or "").strip()
                    rid_tail = _rid_tail(target.viewIdResourceName)
                    if not anchor and not rid_tail and op == "tap":
                        # 完全匿名节点(无 text/desc/rid):锚点无从谈起,走坐标
                        # 逃生舱(一帧旧可接受——匿名节点本就没有更好的定位方式)。
                        b = target.bounds
                        if b is not None and len(b) == 4:
                            cx, cy = (b[0] + b[2]) // 2, (b[1] + b[3]) // 2
                            actions.append(Action(
                                actionId=str(uuid.uuid4()), op="tap_at",
                                params={"x": str(cx), "y": str(cy)},
                            ))
                            break
                    # 语义锚点下行(不注入坐标):端侧执行时按锚点在实时树上
                    # 重新定位点击,fail-closed;坐标会随帧过期点歪(2026-07-22
                    # 错群事故根因),锚点不会。
                    if anchor:
                        params["match_text"] = anchor[:50]
                    if rid_tail:
                        params["match_rid"] = rid_tail
                    occ = _anchor_occurrence(target, nodes)
                    if occ is not None:
                        params["occurrence"] = str(occ)
                actions.append(Action(actionId=str(uuid.uuid4()), op=op, params=params))
                break  # 批处理截断：遇首个 tap/input 收尾，本批结束重抓帧
            actions.append(Action(actionId=str(uuid.uuid4()), op=op, params=params))
        return Decision(actions=actions, source="llm")

    def _cap_nodes(self, nodes: list[Node]) -> list[Node]:
        """智能节点树裁剪:按「对 LLM 理解页面的价值」评分后选 top-N。

        评分规则:
          score=3: 可交互 + 有文字(clickable/editable 且 text/desc 非空)
          score=2: 不可交互 + 有文字(标题、列表项文本、section header)
          score=1: 可交互 + 无文字(FAB、icon 按钮等,仍可点击)
          score=0: 不可交互 + 无文字(结构性容器、布局节点)

        策略:保留所有 score=3;其余按分数从高到低填满 MAX_LLM_NODES 槽位;
        同分节点按原始索引升序。最后返回按原始遍历索引升序排列的结果
        (保持树遍历顺序,便于 LLM 按节点序号操作)。

        这样即使有 200 个节点,所有带文字的按钮/输入框都保留;
        纯装饰节点只在还有余量时才进入。
        """
        if len(nodes) <= self.MAX_LLM_NODES:
            return nodes

        scored: list[tuple[int, int, Node]] = []
        for i, n in enumerate(nodes):
            has_text = bool((n.text or "").strip() or (n.desc or "").strip())
            interactive = n.clickable or n.editable
            if interactive and has_text:
                score = 3
            elif not interactive and has_text:
                score = 2
            elif interactive:
                score = 1
            else:
                score = 0
            scored.append((score, i, n))

        # score 降序,original_index 升序(保持遍历顺序)
        scored.sort(key=lambda x: (-x[0], x[1]))

        # 选 top MAX_LLM_NODES
        chosen_ids: set[int] = {id(s[2]) for s in scored[: self.MAX_LLM_NODES]}

        # 按原始顺序返回
        result = [n for n in nodes if id(n) in chosen_ids]
        return result
