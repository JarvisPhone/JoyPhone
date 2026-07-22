"""AppProfile.feishu 关键词覆盖测试。

回归:2026-07-23 真机根因 — 飞书群聊页群名节点 rid 是
default_center_view_container,未列入 profile.title_rid_keywords 时
detect_title 会退化命中 chat_message_list_view="Ra" 残留节点,
导致 INPUT_GUARD 误判还在错的群、错群 input 命令被全帧拦截。

此测试守护 profile 端——若有人误删 default_center_view_container,
测试直接失败,提示他们去看 2026-07-23 真机任务 task-a39e5229 comm.log。
"""
from app.scenario.profiles.feishu import FEISHU_PROFILE


# 必含关键词(2026-07-23 真机节点)
_REQUIRED_TITLE_RID_KEYWORDS = (
    "title",
    "chat_name",
    "conversation_name",
    "tv_title",
    "tv_chat_name",
    "toolbar_title",
    "action_bar",
    "tv_conversation",
    "title_zone",
    "chat_info_view",
    "default_center_view_container",
    "chat_info_view_redesign",
)


def test_feishu_profile_metadata():
    assert FEISHU_PROFILE.pkg == "com.ss.android.lark"
    assert "飞书" in FEISHU_PROFILE.aliases
    assert "feishu" in FEISHU_PROFILE.aliases
    assert "lark" in FEISHU_PROFILE.aliases


def test_feishu_profile_contains_default_center_view_container():
    """回归 2026-07-23 task-a39e5229 真机根因:
    群聊页群名节点 rid 含 default_center_view_container,
    该关键词必须保留在 title_rid_keywords 里。"""
    assert "default_center_view_container" in FEISHU_PROFILE.title_rid_keywords


def test_feishu_profile_contains_chat_info_view_redesign():
    """群信息页群名节点 rid 含 chat_info_view_redesign。"""
    assert "chat_info_view_redesign" in FEISHU_PROFILE.title_rid_keywords


def test_feishu_profile_all_required_title_rid_keywords():
    """所有历史关键词 + 2026-07-23 新发现的两个关键词都在。"""
    for kw in _REQUIRED_TITLE_RID_KEYWORDS:
        assert kw in FEISHU_PROFILE.title_rid_keywords, (
            f"飞书 title_rid_keywords 缺 {kw!r};参考 2026-07-23 真机 task-a39e5229"
        )


def test_feishu_send_button_has_btn_send():
    """btn_send rid 关键词必含(protocol 端发送按钮 id=73 即此 rid)。"""
    assert "btn_send" in FEISHU_PROFILE.send_button_keywords


def test_feishu_message_input_has_give_to_chinese():
    """「发送给」必须是 message_input_hints(飞书输入框 hint 文案)。"""
    assert "发送给" in FEISHU_PROFILE.message_input_hints


def test_feishu_search_hints_present():
    """搜索类提示词必须在 search_hints(搜群名时不能误判为 message_input)。"""
    for kw in ("搜索", "查找", "search"):
        assert kw in FEISHU_PROFILE.search_hints
