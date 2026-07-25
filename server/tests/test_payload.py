from types import SimpleNamespace

from app.decision.payload import (
    build_system_prompt,
    build_user_payload,
    encode_visible_nodes,
    render_layout_summary,
)


def _node(i, text="", *, clickable=True, editable=False, rid="", cls="", bounds=None):
    """构造一个测试用的极简 Node,字段名与 protocol.Node 对齐。"""
    return SimpleNamespace(
        id=str(i), text=text, desc="", clickable=clickable, editable=editable,
        viewIdResourceName=rid or None, className=cls or None,
        bounds=bounds or [0, 0, 100, 100],
    )


def test_system_prompt_under_2000_chars_and_starts_with_role():
    sp = build_system_prompt()
    assert len(sp) < 2000, f"system prompt too long: {len(sp)} chars"
    assert sp.startswith("[ROLE]")


def test_user_payload_has_four_sections_in_order():
    nodes = [_node(0, text="搜索", clickable=False, editable=True, rid="x:id/edit")]
    frame = SimpleNamespace(pkg="com.x", nodeTree=nodes, activity="", ts=1)
    payload = build_user_payload(
        goal="打开飞书给 Android 发消息",
        frame=frame,
        scene_label="app",
        page_label="app.inbox_list",
        target_pkg="com.ss.android.lark",
        exit_path="单 back 回列表",
        nav_map="top=(0:input) mid=(0:plain) bottom=(0:plain)",
        screen_text="[0] input \"搜索\"",
        feedback="",
        last_action=None,
        scene_brief=None,
    )
    obs = payload.index("[OBSERVE]")
    grd = payload.index("[GROUND]")
    act = payload.index("[ACT]")
    vr = payload.index("[VERIFY]")
    assert obs >= 0 and grd > obs and act > grd and vr > act


def test_visible_nodes_only_includes_clickable_editable_or_titled_nodes():
    nodes = [
        _node(0, text="搜索框", editable=True),                 # 可交互,留
        _node(1, text="发送", clickable=True),                  # 可交互,留
        _node(2, text="装饰", clickable=False, editable=False), # 纯装饰,剔
        _node(3, text="", rid="com.x:id/btn_send", clickable=False, editable=False),  # rid 兜底,留
        _node(4, text="", clickable=False, editable=False),     # 无语义无交互,剔
    ]
    out = encode_visible_nodes(nodes, ancestor_clickable=[False]*len(nodes), screen_height=200)
    assert "[0]" in out  # editable
    assert "btn_send" in out or "btn send" in out  # rid 兜底
    assert "装饰" not in out  # 装饰节点剔除


def test_render_layout_summary_marks_top_middle_bottom():
    # screen_height=240,bucket_size=60
    nodes = [
        _node(0, text="top", bounds=[0, 0, 100, 30]),       # bucket 0(顶部)
        _node(1, text="mid", bounds=[0, 100, 100, 150]),     # bucket 2(中部)
        _node(2, text="bot", bounds=[0, 200, 100, 230]),     # bucket 3(底部)
    ]
    summary = render_layout_summary(nodes)
    assert "top=" in summary and "mid=" in summary and "bottom=" in summary


def test_user_payload_section_with_scene_brief_appears_after_observe():
    nodes = [_node(0, text="x", clickable=True)]
    frame = SimpleNamespace(pkg="com.coloros.launcher", nodeTree=nodes, activity="", ts=1)
    payload = build_user_payload(
        goal="x", frame=frame, scene_label="launcher.minus_one",
        page_label="n/a", target_pkg="com.ss.android.lark",
        exit_path="swipe right", nav_map="top=(1:button)",
        screen_text="[0] button \"小布建议\"",
        feedback="", last_action=None,
        scene_brief="你看到的「XX 有 N 条通知」是负一屏磁贴,**不是应用图标**。",
    )
    assert "[OBSERVE]" in payload
    assert "[SCENE-BRIEF" in payload
    assert "负一屏磁贴" in payload
    # scene-brief 必须在 OBSERVE 后,VERIFY 前
    assert payload.index("[OBSERVE]") < payload.index("[SCENE-BRIEF") < payload.index("[VERIFY]")
