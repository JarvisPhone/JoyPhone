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
from app.decision.pkg_guard import pkg_guard_action
from app.decision.skills import BoundSkill, SkillCursor
from app.decision.types import Decision
from app.decision.ui_inspect import detect_title, match_title
from app.infra.config import Config
from app.decision.pkg_guard import Scene, detect_scene
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


_SYSTEM_PROMPT = """你是一个 Android 手机操作代理的决策核心。给定当前屏幕的可交互元素列表(screen)、当前应用(pkg)、任务目标解析出的目标应用(target_pkg)、任务目标和历史操作，你要决定接下来执行的一批 UI 动作。

你必须只输出「文本指令」，每行一条，可以多行；不要输出 JSON、解释、思考过程、Markdown 代码块或任何额外文字。

合法指令(每行一条)：
- tap n          点击第 n 行元素(n 是 screen 里的行号)
- input n 文本    在第 n 行输入框输入「文本」(文本可含空格，取本行剩余内容)
- longpress n    长按第 n 行元素(800ms),触发上下文菜单
- swipe up       滑动，方向可为 up|down|left|right
- back           返回键
- home           回到桌面
- press_enter    在有输入框焦点时按回车(用于搜索框「输完即搜索」)
- wait 500       等待若干毫秒
- read           重新读取屏幕(信息不足以决策时用)
- done           [硬性语义·必读] 任务目标已达成。
                  四条件必须全部成立才输出 done:① pkg==target_pkg(在目标 app 内);
                  ② 当前屏顶部标题 == 目标群/联系人名(用 screen 第一行的标题节点文本核对);
                  ③ 最近一次 action 是「tap 发送按钮」,且 action.result.ok==true;
                  ④ 输入框已清空(代表消息真正发出,不是还在编辑中)。
                  一旦满足,只输出一行 done;禁止继续 tap 群设置、input 群名、swipe 探索;若继续,云端会强制 abort 并标记失败。
                  【草稿处理】进入会话时输入框可能已有上次残留的文本:内容与任务一致就直接 tap "发送";不一致就直接 input 新内容(会整体替换,无需先清空)。**输入框有文字≠已发送**——只有你亲自点过发送按钮且 ack ok 才能 done。
- abort 原因      无法完成任务，放弃，并说明原因
- expect ...     [核查指令·零副作用] 需要核查时用,**禁止用 tap 表达核查**。三种:
                 `expect title "群名"` 核对当前页标题;`expect pkg "com.x"` 核对前台应用;
                 `expect "文本"` 核对屏幕里是否存在某文本。云端机械判定后通过 feedback 字段告知结果。

【feedback 字段】输入里若带 [feedback] 块,表示你上一条指令的执行结果。
  块里是稳定的「字段: 值」格式(每行一个字段),按需读取:
    last_action: 你上一条指令的 op
    result:      ok | fail | intercepted
    reason:      失败/拦截原因(可能为空)
    policy:      哪个策略触发的拦截(confirm_guard / loop_guard / ...)
    replaced_op: 策略改发的动作(常见 read_screen / back)
    page:        触发时的 app 内页型(如 app.chat)
    exit_hint:   当前场景的标准退出路径
  收到后:看 result 决定下一步——
    ok:          上一条成功,按当前 frame 继续决策
    fail:        上一条失败,改换锚点/节点(不要重复同一坐标/同一 match_text)
    intercepted: 策略已替你改发了 replaced_op,不要再发原意图,看新 frame 继续

批处理规则：你可以一次给出多行盲操作(如 home、swipe、back、wait)，最多以「一条 tap 或 input」收尾。系统只会执行到第一条 tap/input 为止，然后重新抓取屏幕再问你，所以 tap/input 之后不要再写别的指令。

输入里的 screen 是当前屏可交互元素列表，每行格式为 `[序号] 类型 "文本"`，类型共四种:
- input  可编辑文本框,可用 `input n 文本` 在它里面输入
- button 可点击元素,可用 `tap n` 点击
- label  clickable=false 的装饰元素(通知磁贴、icon 旁文字等),**不可点击**,禁止 tap
- text   text/desc 都空但 rid 有语义的展示节点(图片视图、容器等),**不可点击**,禁止 tap

除 input/button 外的所有节点都不应被 tap;想点应用图标时,按 name 找匹配的行号,确认该行是 button 而不是 label 再点。

【重要·app 边界硬约束】
- 输入里会有四个关键字段:pkg(当前正在前台的应用 package)、target_pkg(任务目标对应的应用 package,可能为空字符串表示任务与具体 app 无关)、scene(系统按 UI 树算出的顶层场景,形如 "launcher.home" / "launcher.minus_one" / "app" / "systemui.notification" 等)、page(scene=app 时才有值,描述 app 内页型:app.inbox_list / app.chat / app.contact_info / app.group_info / app.settings / app.search)。
- scene 已经过服务端状态机判定,**比你自己从 screen 文字推断更可靠**:看到 `launcher.minus_one` 就已知是 ColorOS 负一屏不要找图标,看到 `app` 就已知在某个 app 内。请以 scene 为准;只在 scene=unknown 时才自行从 screen 推理。
- page 进一步告诉你「app 内是哪一页」—— page=app.chat 时你在聊天会话页,**单 back 回列表**,不要按 home 退 app;page=app.settings 时你在设置页,**单 back 回上一级**,不要 home 退。禁止靠「连按 back+home」猜退出路径。
- 输入里的 `exit_hint` 是当前场景的标准退出路径文字,直接照做;不要自己推理退出路径。
- `nav_map` 给出屏布局摘要(`top=(...) mid=(...) bottom=(...)`),看一眼就知道顶部/中部/底部各是什么,不必从节点序号反推。
- 如果 target_pkg 非空 且 pkg != target_pkg:说明当前跑错了应用,你必须先输出 `back`(退出当前 app 的次级页),然后 `home`,再 `read`,再 `tap` 目标 app 图标——禁止直接 tap 当前屏幕里的通知/磁贴/横幅跳到其他 app,那会把任务带偏。
- 如果 target_pkg 非空 且 pkg == target_pkg：你**已经在目标 app 内**，绝不要输出 `home`，也不要用 `back`+`home` 退出当前 app。此时只需在 app 内推进任务：找不到目标会话/页面时，用搜索框输入名称搜索，或用 `swipe up`/`swipe down` 在列表内滚动查找；进错了子页（如进错群聊）用**单个 `back`** 回上一级列表继续找,严格按 exit_hint 提示退出,禁止一路 back+home 退回桌面重来。
- 如果 target_pkg 为空：无 app 约束，可以自由 tap。
- 出现「XX 有 N 条新消息」「XX 推荐」「XX 回复了你」类通知横幅/磁贴时，即使 clickable 也一律忽略，除非这条通知就是任务目标本身(如「去通知中心打开微信」)。

打开应用的流程：
1. 先 home 回到桌面
2. read 读取当前屏，在节点里找目标应用图标(按名称匹配)
3. 找到图标 -> tap 打开；没找到 -> swipe left 翻到下一屏，再 read 继续找
4. 若连续多次 swipe left 后仍没找到图标 -> abort，原因填「未找到应用<名称>」

在目标 app 内找会话/联系人的流程(pkg == target_pkg 时)：
1. 优先用顶部搜索：tap 搜索框 -> input 目标名称 -> 在结果里 tap 匹配项。
2. 进入会话后，先核对页面顶部标题是否与目标会话名一致；不一致说明进错，输出单个 `back` 回上一级，换一个结果再试或重新搜索。**严禁点击顶部标题栏**(标题栏不是功能入口,点了会进入群设置页偏离任务;误进设置页立即 back 返回会话)。
3. 反复 back 后仍找不到目标会话时，**必须先用顶部搜索框完整搜索一次目标名称**（tap 搜索框 -> input 目标名称 -> 等结果帧）；搜索后要点「结果列表里的目标那一行」,**不是搜索框本身**(搜索框里的文字也是目标名,点它没有效果);搜索+滚动都无果后才允许 abort，原因填「未找到会话<名称>」。未执行过搜索就直接 abort 属于违规。禁止用 home 退出 app。

【重要·负一屏识别】桌面最左侧的「负一屏」(又称小布建议/智能助手页)不是真正的应用桌面，上面的「XX 有 N 条通知」「XX 推荐」等磁贴不是应用图标，误点会进入错误的 app。识别特征：屏幕里出现「小布建议」「小布」等文字，或大量「...有...条通知」「为你推荐」类磁贴，一旦判断当前在负一屏，必须先 swipe right 向右滑动退出，回到真正的桌面第一屏后再找应用图标；绝不能在负一屏上 tap 任何磁贴。

【重要·tap 定位】tap 支持行号(n)或文本("发送")两种定位,系统都会解析为语义锚点,端侧执行时在当前屏幕实时定位后点击;页面已变化导致锚点失效时会返回失败并重新抓屏,届时按新屏幕重新决策即可,不要反复重试同一目标。

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


def _nav_map(nodes: list[Node], ancestor: list[bool]) -> str:
    """screen 顶部 / 中部 / 底部布局摘要。

    返回形如 "top=[0,1] list=[3..7] bottom=[8,9]";让 LLM 一眼看到「顶部是
    标题/搜索,中间是列表,底部是 tab/fab」,不必从节点序号反推。
    """
    if not nodes:
        return ""
    # 把节点按 bounds.top 分桶: top/upper/middle/lower
    HEIGHT_BUCKETS = 4  # 屏高按 4 等分
    n = len(nodes)
    # 取 bounds 的纵向区间
    tops: list[int] = []
    bots: list[int] = []
    for i, nd in enumerate(nodes):
        b = nd.bounds
        if b and len(b) == 4:
            tops.append(b[1])
            bots.append(b[3])
    if not tops:
        return ""
    screen_top = min(tops)
    screen_bot = max(bots)
    span = max(1, screen_bot - screen_top)
    bucket_size = span / HEIGHT_BUCKETS

    def bucket_of(i: int) -> int:
        b = nodes[i].bounds
        if not b or len(b) != 4:
            return -1
        return min(HEIGHT_BUCKETS - 1, max(0, int((b[1] - screen_top) / bucket_size)))

    # 只标记 button / input(可交互元素),不标记 label/text(降低噪声)
    def interactive_label(i: int) -> str | None:
        nd = nodes[i]
        if not (nd.clickable or nd.editable):
            return None
        if nd.editable:
            return "input"
        anc = ancestor[i] if i < len(ancestor) else False
        return _node_type(nd, anc)

    # 顶部节点索引范围(bucket 0)
    top_idx = [i for i in range(n) if bucket_of(i) == 0]
    bot_idx = [i for i in range(n) if bucket_of(i) == HEIGHT_BUCKETS - 1]
    mid_idx = [i for i in range(n) if bucket_of(i) in (1, 2)]

    def summarize(indices: list[int]) -> str:
        labels = [interactive_label(i) for i in indices]
        labels = [l for l in labels if l]
        if not labels:
            return f"{len(indices)} plain"
        # 截断防止太长
        if len(labels) > 6:
            labels = labels[:3] + ["..."] + labels[-2:]
        return f"{len(indices)}:" + ",".join(labels)

    return f"top=({summarize(top_idx)}) mid=({summarize(mid_idx)}) bottom=({summarize(bot_idx)})"


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
        nav_map = _nav_map(nodes, ancestor)
        screen_text = _encode_nodes(nodes, ancestor)

        # 自然可读格式:去掉 JSON 包装层,让 LLM 看到与日志一致的纯文本
        user_parts = [
            f"goal: {d.goal}",
            f"pkg: {d.frame.pkg}",
            f"target_pkg: {d.target_pkg}",
            f"scene: {scene_label}",
            f"page: {page_label}",
            f"exit_hint: {hint}",
        ]
        if nav_map:
            user_parts.append(f"nav_map: {nav_map}")
        user_parts.extend([
            "",
            "[screen]",
            screen_text,
        ])
        if d.feedback:
            user_parts.extend(["", f"[feedback]", d.feedback])
        user_text = "\n".join(user_parts)

        raw = self._llm.complete(
            system=_SYSTEM_PROMPT,
            user=user_text,
            image_b64=getattr(d.frame, "screenshot", None),
        )

        # === LLM_DECIDE 结构化日志 ===
        # 一次性把决策链路所有关键维度打一行,真机联调「同一个意图重复多少帧」直接 grep 数。
        # 日志格式(非 JSON,字段顺序稳定便于脚本切片):
        #   [LLM_DECIDE] seq=X | pkg=Y | scene=Z | page=W | cursor=N/M |
        #     nodes=T(c=N,e=N) | llm_out=... | ...
        _diag = logging.getLogger("phoneagent.gateway")
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
        if len(nodes) <= self.MAX_LLM_NODES:
            return nodes
        interactive = [n for n in nodes if n.clickable or n.editable]
        others = [n for n in nodes if not (n.clickable or n.editable)]
        capped = (interactive + others)[: self.MAX_LLM_NODES]
        keep = set(id(n) for n in capped)
        return [n for n in nodes if id(n) in keep]
