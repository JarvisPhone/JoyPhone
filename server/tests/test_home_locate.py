# server/tests/test_home_locate.py
from __future__ import annotations

from app.decision.home_locate import _screen_icon_fingerprint, find_icon, home_locate_action
from app.protocol import Node, Perception


# ---------- 帧工厂 ----------

def _home(nodes: list[Node]) -> Perception:
    # launcher workspace 全屏 bounds=[0,0,...] → detect_scene 判 HOME
    ws = Node(id="ws", viewIdResourceName="com.coloros.launcher:id/workspace", bounds=(0, 0, 1080, 2400))
    return Perception(pkg="com.coloros.launcher", nodeTree=[ws, *nodes])


def _minus_one(nodes: list[Node] | None = None) -> Perception:
    # workspace 内缩(left/top>0) → detect_scene 判 MINUS_ONE
    ws = Node(id="ws", viewIdResourceName="com.coloros.launcher:id/workspace", bounds=(40, 60, 1040, 2340))
    return Perception(pkg="com.coloros.launcher", nodeTree=[ws, *(nodes or [])])


# ---------- 纯工具:fingerprint / find_icon ----------

def test_fingerprint_ignores_order_and_dedup():
    a = [Node(id="1", text="飞书"), Node(id="2", text="微信")]
    b = [Node(id="3", text="微信"), Node(id="4", text="飞书"), Node(id="5", text="")]
    assert _screen_icon_fingerprint(a) == _screen_icon_fingerprint(b)


def test_fingerprint_differs_when_icon_added():
    a = [Node(id="1", text="飞书")]
    b = [Node(id="1", text="飞书"), Node(id="2", text="微信")]
    assert _screen_icon_fingerprint(a) != _screen_icon_fingerprint(b)


def test_find_icon_hit_exact():
    nodes = [Node(id="1", text="微信"), Node(id="2", text="飞书")]
    hit = find_icon(nodes, ["飞书", "feishu", "lark"])
    assert hit is not None and hit.text == "飞书"


def test_find_icon_hit_by_desc_case_insensitive():
    nodes = [Node(id="1", desc="Lark")]
    hit = find_icon(nodes, ["飞书", "feishu", "lark"])
    assert hit is not None


def test_find_icon_miss_returns_none():
    nodes = [Node(id="1", text="微信"), Node(id="2", text="王者荣耀")]
    assert find_icon(nodes, ["飞书", "feishu", "lark"]) is None


# ---------- 早退分支 ----------

def test_fallback_empty_aliases_returns_none():
    frame = _home([Node(id="1", text="微信")])
    assert home_locate_action(frame, "com.ss.android.lark", [], {}) is None


def test_not_home_returns_none():
    frame = Perception(pkg="com.ss.android.lark", nodeTree=[])
    assert home_locate_action(frame, "com.ss.android.lark", ["飞书"], {}) is None


def test_already_in_target_returns_none():
    ws = Node(id="ws", viewIdResourceName="com.coloros.launcher:id/workspace", bounds=(0, 0, 1080, 2400))
    frame = Perception(pkg="com.ss.android.lark", nodeTree=[ws])
    assert home_locate_action(frame, "com.ss.android.lark", ["飞书"], {}) is None


# ---------- 命中 tap ----------

def test_home_hit_icon_returns_tap():
    frame = _home([Node(id="1", text="飞书")])
    acts = home_locate_action(frame, "com.ss.android.lark", ["飞书", "lark"], {})
    assert acts and acts[0].op == "tap" and acts[0].params["match_text"] == "飞书"


def test_home_hit_icon_clears_state():
    guard: dict = {"home_locate": {"direction": "right", "last_fp": frozenset(["x"]), "exhausted": {"left"}, "swipe_count": 5}}
    frame = _home([Node(id="1", text="飞书")])
    acts = home_locate_action(frame, "com.ss.android.lark", ["飞书"], guard)
    assert acts and acts[0].op == "tap"
    # tap 后状态清空,避免命中同一 app 再次进入时残留
    assert "home_locate" not in guard


# ---------- MINUS_ONE:跳过 find_icon(核心回归)----------

def test_minus_one_notification_card_not_matched():
    """回归 2026-07-28 真机 bug:负一屏「飞书 有4条通知」不能被 tap。

    -1 屏上有含 alias 的通知卡片文本,但 clickable=False 且不是应用图标入口。
    home_locate 在 MINUS_ONE 场景必须跳过 find_icon,只走 swipe 逻辑。
    """
    notif = Node(id="n", text="飞书 有4条通知", clickable=False)
    guard: dict = {}
    acts = home_locate_action(_minus_one([notif]), "com.ss.android.lark", ["飞书", "lark"], guard)
    assert acts is not None
    # 不能 tap,应该 swipe
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
    frame = _home([Node(id="1", text="微信")])
    guard: dict = {}
    acts = home_locate_action(frame, "com.ss.android.lark", ["飞书"], guard)
    assert acts and acts[0].op == "swipe" and acts[0].params["direction"] == "left"
    assert guard["home_locate"]["direction"] == "left"


def test_new_frame_continues_current_direction_without_boundary():
    """last_fp 与当前帧 fp 不同 → 未到边界,朝原方向继续。"""
    prev_fp = frozenset(["A", "B"])
    guard: dict = {"home_locate": {"direction": "right", "last_fp": prev_fp, "exhausted": set(), "swipe_count": 3}}
    frame = _home([Node(id="1", text="王者荣耀")])
    acts = home_locate_action(frame, "com.ss.android.lark", ["飞书"], guard)
    assert acts and acts[0].op == "swipe" and acts[0].params["direction"] == "right"
    # last_fp 已更新为当前帧
    assert guard["home_locate"]["last_fp"] == _screen_icon_fingerprint(frame.nodeTree)


# ---------- 边界:切方向,不 abort ----------

def test_boundary_hit_switches_direction_not_abort():
    """当前方向 fp 相同 → 切另一方向,不 abort。"""
    frame = _home([Node(id="1", text="微信"), Node(id="2", text="王者荣耀")])
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
    frame = _home([Node(id="1", text="微信")])
    guard: dict = {"home_locate": {"direction": "right", "last_fp": None, "exhausted": {"left"}, "swipe_count": 5}}
    acts = home_locate_action(frame, "com.ss.android.lark", ["飞书"], guard)
    assert acts and acts[0].op == "swipe" and acts[0].params["direction"] == "right"
    # 未 abort,继续扫描
    assert guard["home_locate"]["exhausted"] == {"left"}


# ---------- 双向皆达边界 → abort ----------

def test_both_directions_exhausted_aborts():
    """一向已耗尽,另一向也遇 fp 相同 → 真正 abort。"""
    frame = _home([Node(id="1", text="微信"), Node(id="2", text="王者荣耀")])
    fp = _screen_icon_fingerprint(frame.nodeTree)
    guard: dict = {"home_locate": {"direction": "right", "last_fp": fp, "exhausted": {"left"}, "swipe_count": 10}}
    acts = home_locate_action(frame, "com.ss.android.lark", ["飞书"], guard)
    assert acts and acts[0].op == "abort"
    assert acts[0].params["reason"].startswith("app_not_found")


# ---------- 端到端:多帧扫描序列 ----------

def test_end_to_end_bidirectional_scan_finds_icon_after_switch():
    """场景:从中间某页起扫,先向 right(左向) 达边界后切 left(右向),在某页找到飞书。"""
    guard: dict = {}
    target_pkg = "com.ss.android.lark"
    aliases = ["飞书", "feishu", "lark"]

    # 帧 1:HOME 中间页,无飞书 → 记 fp,swipe left
    f1 = _home([Node(id=f"n{i}", text=t) for i, t in enumerate(["微信", "支付宝"])])
    a1 = home_locate_action(f1, target_pkg, aliases, guard)
    assert a1 and a1[0].op == "swipe" and a1[0].params["direction"] == "left"

    # 帧 2:仍无飞书,但内容相同(fp 相同,翻不动)→ 切 direction=right
    f2 = _home([Node(id=f"n{i}", text=t) for i, t in enumerate(["微信", "支付宝"])])
    a2 = home_locate_action(f2, target_pkg, aliases, guard)
    assert a2 and a2[0].op == "swipe" and a2[0].params["direction"] == "right"
    assert guard["home_locate"]["direction"] == "right"
    assert guard["home_locate"]["exhausted"] == {"left"}

    # 帧 3:向 right 滑到含飞书的页 → tap
    f3 = _home([Node(id="fs", text="飞书")])
    a3 = home_locate_action(f3, target_pkg, aliases, guard)
    assert a3 and a3[0].op == "tap" and a3[0].params["match_text"] == "飞书"


# ---------- 安全兜底 ----------

def test_swipe_count_over_limit_aborts():
    guard: dict = {"home_locate": {"direction": "left", "last_fp": frozenset(["x"]), "exhausted": set(), "swipe_count": 99}}
    frame = _home([Node(id="1", text="王者荣耀")])
    acts = home_locate_action(frame, "com.ss.android.lark", ["飞书"], guard)
    assert acts and acts[0].op == "abort"
