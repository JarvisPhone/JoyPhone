"""send_message 场景包(SendMessagePack)装配与目标解析测试。"""
from app.scenario.profiles import FEISHU_PROFILE, WECHAT_PROFILE
from app.scenario.send_message import (
    ConfirmInterceptPolicy,
    PostSendForceDonePolicy,
    PostSendPatrolPolicy,
    PreSendRevertPolicy,
    SendGuardPolicy,
    SendMessagePack,
    SidebarDismissPolicy,
    TitleTapGuardPolicy,
    WrongChatInputPolicy,
)


def test_matches_feishu_send_goal():
    pack = SendMessagePack()
    assert pack.matches("给张三发个飞书消息") == 0.9
    assert pack.matches("用微信发送消息给李四") == 0.9
    assert pack.matches("feishu message to bob") == 0.9


def test_matches_no_app_alias():
    pack = SendMessagePack()
    assert pack.matches("给张三发条消息") == 0.0


def test_matches_no_send_intent():
    pack = SendMessagePack()
    assert pack.matches("打开飞书看一下") == 0.0


def test_resolve_target_with_chat():
    pack = SendMessagePack()
    t = pack.resolve_target("给「AI 产品交流群」发飞书消息")
    assert t.pkg == FEISHU_PROFILE.pkg
    assert t.chat == "AI 产品交流群"
    assert t.bindings == {"contact": "AI 产品交流群", "query": "AI 产品交流群"}


def test_resolve_target_wechat():
    pack = SendMessagePack()
    t = pack.resolve_target("用微信发消息给李四")
    assert t.pkg == WECHAT_PROFILE.pkg
    assert t.chat == "李四"
    assert t.bindings == {"contact": "李四", "query": "李四"}


def test_resolve_target_without_chat_bindings_empty():
    pack = SendMessagePack()
    t = pack.resolve_target("打开飞书")
    assert t.pkg == FEISHU_PROFILE.pkg
    assert t.chat is None
    assert t.bindings == {}


def test_skills_templates_ported():
    pack = SendMessagePack()
    templates = {tpl.name: tpl for tpl in pack.skills()}
    assert set(templates) == {"feishu_send_message", "feishu_search_contact"}

    send = templates["feishu_send_message"]
    assert send.params == ["contact"]
    assert send.app == FEISHU_PROFILE.pkg
    ops = [s.op for s in send.steps]
    assert ops == ["tap", "tap", "input", "verify_title", "tap"]
    assert send.steps[2].input_text == "{contact}"
    assert send.steps[3].match_text == "{contact}"

    search = templates["feishu_search_contact"]
    assert search.params == ["query"]
    assert search.app == FEISHU_PROFILE.pkg
    ops = [s.op for s in search.steps]
    assert ops == ["tap", "input"]
    assert search.steps[1].input_text == "{query}"


def test_policies_assembly():
    pack = SendMessagePack()
    pre = pack.pre_policies()
    post = pack.post_policies()
    assert [type(p) for p in pre] == [
        SidebarDismissPolicy,
        PreSendRevertPolicy,
        PostSendForceDonePolicy,
        PostSendPatrolPolicy,
    ]
    assert [type(p) for p in post] == [
        TitleTapGuardPolicy,
        SendGuardPolicy,
        ConfirmInterceptPolicy,
        WrongChatInputPolicy,
    ]


def test_ui_profile_by_pkg():
    pack = SendMessagePack()
    assert pack.ui_profile(FEISHU_PROFILE.pkg) is FEISHU_PROFILE
    assert pack.ui_profile(WECHAT_PROFILE.pkg) is WECHAT_PROFILE
    assert pack.ui_profile("com.unknown.app") is None
