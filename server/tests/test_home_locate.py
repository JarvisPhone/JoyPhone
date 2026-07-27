# server/tests/test_home_locate.py
from __future__ import annotations

from app.decision.home_locate import _screen_icon_fingerprint, find_icon, home_locate_action
from app.protocol import Node, Perception


def _home(nodes: list[Node]) -> Perception:
    # launcher workspace 全屏 bounds=[0,0,...] → detect_scene 判 HOME
    ws = Node(id="ws", viewIdResourceName="com.coloros.launcher:id/workspace", bounds=(0, 0, 1080, 2400))
    return Perception(pkg="com.coloros.launcher", nodeTree=[ws, *nodes])


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


def _minus_one() -> Perception:
    ws = Node(id="ws", viewIdResourceName="com.coloros.launcher:id/workspace", bounds=(40, 60, 1040, 2340))
    return Perception(pkg="com.coloros.launcher", nodeTree=[ws])


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


def test_home_hit_icon_returns_tap():
    frame = _home([Node(id="1", text="飞书")])
    acts = home_locate_action(frame, "com.ss.android.lark", ["飞书", "lark"], {})
    assert acts and acts[0].op == "tap" and acts[0].params["match_text"] == "飞书"


def test_home_miss_homing_swipes_right():
    frame = _home([Node(id="1", text="微信")])
    guard: dict = {}
    acts = home_locate_action(frame, "com.ss.android.lark", ["飞书"], guard)
    assert acts and acts[0].op == "swipe" and acts[0].params["direction"] == "right"
    assert guard["home_locate"]["phase"] == "homing"


def test_minus_one_switches_to_scanning_swipe_left():
    guard = {"home_locate": {"phase": "homing", "last_fingerprint": [], "swipe_count": 1}}
    acts = home_locate_action(_minus_one(), "com.ss.android.lark", ["飞书"], guard)
    assert acts and acts[0].op == "swipe" and acts[0].params["direction"] == "left"
    assert guard["home_locate"]["phase"] == "scanning"


def test_scanning_fingerprint_same_aborts():
    fp = sorted(["微信", "王者荣耀"])
    guard = {"home_locate": {"phase": "scanning", "last_fingerprint": fp, "swipe_count": 3}}
    frame = _home([Node(id="1", text="微信"), Node(id="2", text="王者荣耀")])
    acts = home_locate_action(frame, "com.ss.android.lark", ["飞书"], guard)
    assert acts and acts[0].op == "abort"
    assert acts[0].params["reason"].startswith("app_not_found")


def test_scanning_new_screen_swipes_left():
    guard = {"home_locate": {"phase": "scanning", "last_fingerprint": ["微信"], "swipe_count": 2}}
    frame = _home([Node(id="1", text="王者荣耀")])
    acts = home_locate_action(frame, "com.ss.android.lark", ["飞书"], guard)
    assert acts and acts[0].op == "swipe" and acts[0].params["direction"] == "left"


def test_swipe_count_over_limit_aborts():
    guard = {"home_locate": {"phase": "scanning", "last_fingerprint": ["x"], "swipe_count": 99}}
    frame = _home([Node(id="1", text="王者荣耀")])
    acts = home_locate_action(frame, "com.ss.android.lark", ["飞书"], guard)
    assert acts and acts[0].op == "abort"