from app.decision.app_page import AppPage
from app.decision.pkg_guard import Scene
from app.decision.scene_briefs import brief_for


def test_brief_for_minus_one_warns_widget_is_not_icon():
    text = brief_for(Scene.MINUS_ONE, AppPage.UNKNOWN)
    assert text is not None
    assert "负一屏" in text or "磁贴" in text


def test_brief_for_inbox_list_search_hint():
    text = brief_for(Scene.IN_APP, AppPage.INBOX_LIST)
    assert text is not None
    assert "搜索" in text


def test_brief_for_chat_warns_no_title_tap():
    text = brief_for(Scene.IN_APP, AppPage.CHAT)
    assert text is not None
    assert "标题" in text and "back" in text


def test_brief_for_unknown_page_returns_none():
    """UNKNOWN page 时不重复 scene-level brief(scene hint 已表达)。"""
    text = brief_for(Scene.IN_APP, AppPage.UNKNOWN)
    assert text is None


def test_brief_for_unknown_scene_returns_none():
    text = brief_for(Scene.UNKNOWN, AppPage.UNKNOWN)
    assert text is None


def test_brief_under_5_lines():
    """每个 brief 最多 5 行,严控 token。"""
    for s in Scene:
        for p in AppPage:
            text = brief_for(s, p)
            if text is None:
                continue
            # 5 行内 = 内容紧凑,真机可读
            assert text.count("\n") + 1 <= 5, f"{s}/{p} brief too long: {text!r}"
