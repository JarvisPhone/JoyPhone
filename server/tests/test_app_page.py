# server/tests/test_app_page.py
"""AppPage detector 与 exit_hint 模板单元测试。

AppPage 是 Scene 的细化:scene=app 时进一步告诉 LLM 是 inbox/chat/settings。
exit_hint 给出每种页型的标准退出路径。这两个是「进了二级页面就出不来」
根因修补的核心,测试覆盖典型场景。
"""
from __future__ import annotations

from app.decision.app_page import AppPage, detect_app_page
from app.decision.exit_hint import exit_hint
from app.decision.pkg_guard import Scene
from app.protocol import Node, Perception


def _p(pkg: str, nodes: list[Node]) -> Perception:
    return Perception(pkg=pkg, nodeTree=nodes)


def test_chat_page_requires_input_send_and_bubbles():
    # 输入框 + 发送按钮 + 消息气泡容器 → chat
    nodes = [
        Node(id="i", editable=True, viewIdResourceName="com.x:id/edit_text"),
        Node(id="b", clickable=True, viewIdResourceName="com.x:id/send_button"),
        Node(id="m", viewIdResourceName="com.x:id/chat_message_list_view"),
    ]
    assert detect_app_page(_p("com.ss.android.lark", nodes)) == AppPage.CHAT


def test_inbox_list_has_input_no_send_no_bubbles():
    nodes = [
        Node(id="i", editable=True, viewIdResourceName="com.x:id/search_bar"),
        Node(id="i2", text="张三", clickable=True),
        Node(id="i3", text="李四", clickable=True),
    ]
    assert detect_app_page(_p("com.ss.android.lark", nodes)) == AppPage.INBOX_LIST


def test_search_page_has_input_with_text_and_no_send():
    nodes = [
        Node(id="i", editable=True, text="阿强", viewIdResourceName="com.x:id/search_bar"),
        Node(id="r1", text="阿强强", clickable=True),
        Node(id="r2", text="阿强说", clickable=True),
    ]
    assert detect_app_page(_p("com.ss.android.lark", nodes)) == AppPage.SEARCH


def test_contact_info_page_has_send_message_button():
    nodes = [
        Node(id="b", clickable=True, viewIdResourceName="com.x:id/btn_send_message"),
        Node(id="t", text="阿强"),
    ]
    assert detect_app_page(_p("com.ss.android.lark", nodes)) == AppPage.CONTACT_INFO


def test_group_info_page_has_group_keywords():
    nodes = [Node(id="t", text="群成员 12")]
    assert detect_app_page(_p("com.ss.android.lark", nodes)) == AppPage.GROUP_INFO


def test_settings_page_recognized_via_keyword():
    nodes = [
        Node(id="t1", text="消息通知"),
        Node(id="t2", text="通用设置"),
        Node(id="t3", text="关于"),
    ]
    assert detect_app_page(_p("com.ss.android.lark", nodes)) == AppPage.SETTINGS


def test_outside_in_app_returns_unknown():
    nodes = [Node(id="i", editable=True, text="搜索框")]
    # pkg 是 launcher → detect_app_page 直接返回 UNKNOWN(只对 IN_APP 起作用)
    assert detect_app_page(_p("com.coloros.launcher", nodes)) == AppPage.UNKNOWN


def test_empty_tree_in_app_returns_unknown():
    assert detect_app_page(_p("com.ss.android.lark", [])) == AppPage.UNKNOWN


# ---- exit_hint 模板 ----


def test_exit_hint_for_launcher_home_is_no_exit_needed():
    h = exit_hint(Scene.HOME, AppPage.UNKNOWN)
    assert "无需退出" in h or "tap" in h.lower()


def test_exit_hint_for_app_chat_says_single_back():
    h = exit_hint(Scene.IN_APP, AppPage.CHAT)
    assert "back" in h.lower()
    assert "home" in h  # 明确禁止 home 退出


def test_exit_hint_for_app_settings_says_multiple_back():
    h = exit_hint(Scene.IN_APP, AppPage.SETTINGS)
    assert "back" in h.lower()
    assert "home" in h  # 明确禁止 home


def test_exit_hint_for_minus_one_says_swipe_right():
    h = exit_hint(Scene.MINUS_ONE, AppPage.UNKNOWN)
    assert "swipe" in h.lower() or "home" in h.lower()


def test_exit_hint_for_app_unknown_falls_back_to_scene_hint():
    h = exit_hint(Scene.IN_APP, AppPage.UNKNOWN)
    # page=UNKNOWN 时只返回 scene 通用提示
    assert "在 App 内" in h or "back" in h.lower()