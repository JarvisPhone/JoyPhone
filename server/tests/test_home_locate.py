# server/tests/test_home_locate.py
from __future__ import annotations

from app.decision.home_locate import _screen_icon_fingerprint, find_icon
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