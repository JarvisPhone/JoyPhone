# server/tests/test_home_locate.py
from __future__ import annotations

from app.decision.home_locate import _screen_icon_fingerprint, find_icon, home_locate_action
from app.protocol import Node, Perception


# ---------- Node 工厂 ----------

def _icon(text: str | None = None, desc: str | None = None, *, x: int = 100, y: int = 400) -> Node:
    """一枚典型的 launcher app 图标节点:clickable + 240×240 bounds。"""
    label = text if text is not None else desc
    return Node(
        id=f"icon-{label or 'x'}",
        text=text,
        desc=desc,
        clickable=True,
        bounds=(x, y, x + 240, y + 240),
    )


def _offscreen_icon(text: str) -> Node:
    """离屏页的 TextView(bounds 退化 26px 宽),不应被 find_icon 命中。

    这是 ColorOS 真机 Frame A 的现象:飞书图标在另一 home 页,accessibility 树
    也报告出来,但 bounds 退化到几十像素。
    """
    return Node(id=f"off-{text}", text=text, desc=text, clickable=True, bounds=(0, 1528, 26, 1785))


def _smart_card(text: str) -> Node:
    """负一屏「小布卡片」通知磁贴:clickable=False + com.nearme.instant.card resid。"""
    return Node(
        id=f"card-{text}",
        text=text,
        desc=text,
        clickable=False,
        bounds=(46, 1200, 1034, 1300),
        viewIdResourceName="com.nearme.instant.card:id/ref_56",
    )


def _clickable_smart_card(text: str) -> Node:
    """极端情况:即便 smart-card 是 clickable + 大 bounds,resid 前缀也要剔除。"""
    return Node(
        id=f"card-c-{text}",
        text=text,
        desc=text,
        clickable=True,
        bounds=(46, 1200, 1034, 1400),
        viewIdResourceName="com.oplus.seedling.cardgroup.pluginapp:id/card_root",
    )


def _home(nodes: list[Node]) -> Perception:
    # launcher workspace 全屏 bounds=[0,0,...] → detect_scene 判 HOME
    ws = Node(id="ws", viewIdResourceName="com.coloros.launcher:id/workspace", bounds=(0, 0, 1080, 2400))
    return Perception(pkg="com.coloros.launcher", nodeTree=[ws, *nodes])


def _minus_one(nodes: list[Node] | None = None) -> Perception:
    # workspace 内缩(left/top>0) → detect_scene 判 MINUS_ONE
    ws = Node(id="ws", viewIdResourceName="com.coloros.launcher:id/workspace", bounds=(40, 60, 1040, 2340))
    return Perception(pkg="com.coloros.launcher", nodeTree=[ws, *(nodes or [])])


# ---------- 图标过滤:find_icon 的核心新契约 ----------

def test_find_icon_ignores_non_clickable():
    """非 clickable 的文本节点(如通知磁贴装饰性文字)不作为图标入口。"""
    nodes = [
        Node(id="txt", text="飞书", clickable=False, bounds=(100, 400, 340, 640)),
        _icon(text="微信"),
    ]
    hit = find_icon(nodes, ["飞书", "feishu"])
    assert hit is None


def test_find_icon_ignores_offscreen_narrow_bounds():
    """回归 2026-07-28 真机 bug:离屏页(bounds 宽 26px)的 TextView 不能被命中。

    此帧 workspace 只显示 A 页,B 页图标出现在 tree 里但 bounds 退化。
    """
    nodes = [_offscreen_icon("飞书"), _icon(text="微信")]
    hit = find_icon(nodes, ["飞书", "feishu"])
    assert hit is None


def test_find_icon_ignores_smart_card_by_resid_even_if_clickable_and_big():
    """回归:小布卡片 resource-id 前缀 instant.card/seedling 直接剔除,即使 bounds 够大。"""
    nodes = [_clickable_smart_card("飞书"), _icon(text="微信")]
    hit = find_icon(nodes, ["飞书", "feishu"])
    assert hit is None


def test_find_icon_hits_valid_launcher_icon_only():
    """离屏 + smart-card 都在 tree 里,但只有正常图标被命中。"""
    nodes = [
        _offscreen_icon("飞书"),          # 应剔除
        _smart_card("飞书"),              # 应剔除
        _icon(text="飞书", x=540, y=500), # 应命中
        _icon(text="微信", x=100, y=500),
    ]
    hit = find_icon(nodes, ["飞书", "feishu", "lark"])
    assert hit is not None
    assert hit.text == "飞书"
    assert hit.bounds == (540, 500, 780, 740)


def test_find_icon_hit_by_desc_case_insensitive():
    nodes = [_icon(desc="Lark")]
    hit = find_icon(nodes, ["飞书", "feishu", "lark"])
    assert hit is not None


def test_find_icon_miss_returns_none():
    nodes = [_icon(text="微信"), _icon(text="王者荣耀", x=400)]
    assert find_icon(nodes, ["飞书", "feishu", "lark"]) is None


def test_find_icon_empty_aliases_returns_none():
    assert find_icon([_icon(text="飞书")], []) is None


def test_find_icon_prefers_exact_over_contains():
    """同帧内既有含子串又有完全相等 alias,exact 优先。"""
    nodes = [_icon(text="飞书宠物", x=100), _icon(text="飞书", x=400)]
    hit = find_icon(nodes, ["飞书"])
    assert hit is not None and hit.text == "飞书"


# ---------- 指纹:只统计 icon-like ----------

def test_fingerprint_ignores_non_icon_nodes():
    """小布卡片 loading 状态文本变化(「一键加速」→「一键加速可释放 445MB」)不改指纹。"""
    a = [_icon(text="微信"), _smart_card("一键加速")]
    b = [_icon(text="微信"), _smart_card("一键加速可释放 445MB")]
    assert _screen_icon_fingerprint(a) == _screen_icon_fingerprint(b)


def test_fingerprint_ignores_order_and_dedup():
    a = [_icon(text="飞书"), _icon(text="微信", x=400)]
    b = [_icon(text="微信"), _icon(text="飞书", x=400), _icon(text="", x=800)]
    assert _screen_icon_fingerprint(a) == _screen_icon_fingerprint(b)


def test_fingerprint_differs_when_visible_icon_added():
    a = [_icon(text="飞书")]
    b = [_icon(text="飞书"), _icon(text="微信", x=400)]
    assert _screen_icon_fingerprint(a) != _screen_icon_fingerprint(b)


# ---------- 早退分支 ----------

def test_fallback_empty_aliases_returns_none():
    frame = _home([_icon(text="微信")])
    assert home_locate_action(frame, "com.ss.android.lark", [], {}) is None


def test_not_launcher_returns_none():
    frame = Perception(pkg="com.ss.android.lark", nodeTree=[])
    assert home_locate_action(frame, "com.ss.android.lark", ["飞书"], {}) is None


def test_already_in_target_returns_none():
    ws = Node(id="ws", viewIdResourceName="com.coloros.launcher:id/workspace", bounds=(0, 0, 1080, 2400))
    frame = Perception(pkg="com.ss.android.lark", nodeTree=[ws])
    assert home_locate_action(frame, "com.ss.android.lark", ["飞书"], {}) is None


# ---------- 命中 tap ----------

def test_home_hit_icon_returns_tap():
    frame = _home([_icon(text="飞书")])
    acts = home_locate_action(frame, "com.ss.android.lark", ["飞书", "lark"], {})
    assert acts and acts[0].op == "tap" and acts[0].params["match_text"] == "飞书"


def test_home_hit_icon_clears_state():
    guard: dict = {"home_locate": {"direction": "right", "last_fp": frozenset(["x"]), "exhausted": {"left"}, "swipe_count": 5}}
    frame = _home([_icon(text="飞书")])
    acts = home_locate_action(frame, "com.ss.android.lark", ["飞书"], guard)
    assert acts and acts[0].op == "tap"
    # tap 后状态清空,避免命中同一 app 再次进入时残留
    assert "home_locate" not in guard


def test_minus_one_scene_still_tries_find_icon():
    """回归 2026-07-28 ColorOS bug:detect_scene 因 workspace inset 误判 HOME 为 MINUS_ONE,
    home_locate 不能因此跳过 find_icon;icon-like 过滤足以剔除通知卡片。
    """
    frame = _minus_one([_icon(text="飞书", x=540, y=500), _smart_card("飞书 有4条通知")])
    acts = home_locate_action(frame, "com.ss.android.lark", ["飞书", "lark"], {})
    assert acts and acts[0].op == "tap" and acts[0].params["match_text"] == "飞书"


def test_minus_one_notification_card_not_matched():
    """回归 2026-07-28 真机 bug 早期版本:仅通知卡片、无正常图标时,不应 tap 通知磁贴。"""
    guard: dict = {}
    acts = home_locate_action(_minus_one([_smart_card("飞书 有4条通知")]), "com.ss.android.lark", ["飞书", "lark"], guard)
    assert acts is not None
    assert acts[0].op == "swipe"


def test_minus_one_swipes_current_direction_from_fresh_state():
    guard: dict = {}
    acts = home_locate_action(_minus_one(), "com.ss.android.lark", ["飞书"], guard)
    assert acts and acts[0].op == "swipe" and acts[0].params["direction"] == "left"
    # 首帧仅记录 fp,未耗尽任何方向
    assert guard["home_locate"]["exhausted"] == set()
    assert guard["home_locate"]["last_fp"] is not None
    assert guard["home_locate"]["swipe_count"] == 1


# ---------- HOME 未命中:朝当前方向滑 ----------

def test_home_miss_swipes_current_direction_default_left():
    frame = _home([_icon(text="微信")])
    guard: dict = {}
    acts = home_locate_action(frame, "com.ss.android.lark", ["飞书"], guard)
    assert acts and acts[0].op == "swipe" and acts[0].params["direction"] == "left"
    assert guard["home_locate"]["direction"] == "left"


def test_new_frame_continues_current_direction_without_boundary():
    """last_fp 与当前帧 fp 不同 → 未到边界,朝原方向继续。"""
    prev_fp = frozenset(["A", "B"])
    guard: dict = {"home_locate": {"direction": "right", "last_fp": prev_fp, "exhausted": set(), "swipe_count": 3}}
    frame = _home([_icon(text="王者荣耀")])
    acts = home_locate_action(frame, "com.ss.android.lark", ["飞书"], guard)
    assert acts and acts[0].op == "swipe" and acts[0].params["direction"] == "right"
    # last_fp 已更新为当前帧
    assert guard["home_locate"]["last_fp"] == _screen_icon_fingerprint(frame.nodeTree)


# ---------- 边界:切方向,不 abort ----------

def test_boundary_hit_switches_direction_not_abort():
    """当前方向 fp 相同 → 切另一方向,不 abort。"""
    frame = _home([_icon(text="微信"), _icon(text="王者荣耀", x=400)])
    fp = _screen_icon_fingerprint(frame.nodeTree)
    guard: dict = {"home_locate": {"direction": "left", "last_fp": fp, "exhausted": set(), "swipe_count": 3}}
    acts = home_locate_action(frame, "com.ss.android.lark", ["飞书"], guard)
    assert acts and acts[0].op == "swipe"
    assert acts[0].params["direction"] == "right"  # 已切向
    st = guard["home_locate"]
    assert st["direction"] == "right"
    assert st["exhausted"] == {"left"}
    assert st["last_fp"] is None  # 新方向起点,清 fp


def test_direction_switch_next_frame_no_false_boundary():
    """切方向后,新方向首帧 fp 与旧 fp 相等也不应误判边界(last_fp=None 保护)。"""
    frame = _home([_icon(text="微信")])
    guard: dict = {"home_locate": {"direction": "right", "last_fp": None, "exhausted": {"left"}, "swipe_count": 5}}
    acts = home_locate_action(frame, "com.ss.android.lark", ["飞书"], guard)
    assert acts and acts[0].op == "swipe" and acts[0].params["direction"] == "right"
    # 未 abort,继续扫描
    assert guard["home_locate"]["exhausted"] == {"left"}


# ---------- 双向皆达边界 → abort ----------

def test_both_directions_exhausted_aborts():
    """一向已耗尽,另一向也遇 fp 相同 → 真正 abort。"""
    frame = _home([_icon(text="微信"), _icon(text="王者荣耀", x=400)])
    fp = _screen_icon_fingerprint(frame.nodeTree)
    guard: dict = {"home_locate": {"direction": "right", "last_fp": fp, "exhausted": {"left"}, "swipe_count": 10}}
    acts = home_locate_action(frame, "com.ss.android.lark", ["飞书"], guard)
    assert acts and acts[0].op == "abort"
    assert acts[0].params["reason"].startswith("app_not_found")


# ---------- 端到端:多帧扫描序列 ----------

def test_end_to_end_bidirectional_scan_finds_icon_after_switch():
    """场景:从中间某页起扫,先向 left 达边界后切 right,在某页找到飞书。"""
    guard: dict = {}
    target_pkg = "com.ss.android.lark"
    aliases = ["飞书", "feishu", "lark"]

    # 帧 1:HOME 中间页,无飞书 → 记 fp,swipe left
    f1 = _home([_icon(text="微信"), _icon(text="支付宝", x=400)])
    a1 = home_locate_action(f1, target_pkg, aliases, guard)
    assert a1 and a1[0].op == "swipe" and a1[0].params["direction"] == "left"

    # 帧 2:仍无飞书,但内容相同(fp 相同,翻不动)→ 切 direction=right
    f2 = _home([_icon(text="微信"), _icon(text="支付宝", x=400)])
    a2 = home_locate_action(f2, target_pkg, aliases, guard)
    assert a2 and a2[0].op == "swipe" and a2[0].params["direction"] == "right"
    assert guard["home_locate"]["direction"] == "right"
    assert guard["home_locate"]["exhausted"] == {"left"}

    # 帧 3:向 right 滑到含飞书的页 → tap
    f3 = _home([_icon(text="飞书")])
    a3 = home_locate_action(f3, target_pkg, aliases, guard)
    assert a3 and a3[0].op == "tap" and a3[0].params["match_text"] == "飞书"


# ---------- 安全兜底 ----------

def test_swipe_count_over_limit_aborts():
    guard: dict = {"home_locate": {"direction": "left", "last_fp": frozenset(["x"]), "exhausted": set(), "swipe_count": 99}}
    frame = _home([_icon(text="王者荣耀")])
    acts = home_locate_action(frame, "com.ss.android.lark", ["飞书"], guard)
    assert acts and acts[0].op == "abort"
