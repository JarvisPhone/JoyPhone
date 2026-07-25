"""AppProfile.llm_brief 字段单测 + 飞书专属 brief 注入引擎路径测试。

覆盖:
- AppProfile 默认 llm_brief == ""(新字段,Task 5 引入)
- FEISHU_PROFILE.llm_brief 非空(飞书有专项提示)
- engine._llm_decide 在 target_pkg=com.ss.android.lark 时把
  飞书专属 brief 拼到 scene_brief 后,user payload 里能 grep 到
"""
from app.scenario.base import AppProfile
from app.scenario.profiles.feishu import FEISHU_PROFILE


def test_app_profile_has_llm_brief_field_default_empty():
    p = AppProfile(
        pkg="com.test", aliases=["t"],
        title_rid_keywords=["x"],
        send_button_keywords=["send"],
        search_hints=["搜索"],
        message_input_hints=["输入"],
    )
    assert p.llm_brief == ""


def test_feishu_profile_has_nonempty_llm_brief():
    assert FEISHU_PROFILE.llm_brief != ""


def test_engine_llm_decide_app_profile_brief_concatenates_with_generic():
    """app-specific AppProfile.llm_brief 应拼到通用 brief 之后,两者都出现。"""
    from app.decision.engine import DecisionEngine, DecideInput
    from app.decision.llm import FakeLLM
    from app.protocol import Node, Perception
    from app.decision.skills import SkillCursor

    captured = []

    class CapturingFake(FakeLLM):
        def complete(self, system, user, image_b64=None):
            captured.append(user)
            return "read"

    # 构造一个 CHAT 页帧 — 飞书快捷场景
    nodes = [
        Node(id="0", text="发送", clickable=True, editable=False,
             viewIdResourceName="com.ss.android.lark:id/btn_send",
             bounds=[900, 2100, 1080, 2280]),
        Node(id="1", text="说点什么", clickable=False, editable=True,
             viewIdResourceName="com.ss.android.lark:id/et_message",
             bounds=[0, 2000, 880, 2200]),
    ]
    frame = Perception(pkg="com.ss.android.lark", nodeTree=nodes, activity="", ts=1)

    eng = DecisionEngine(llm=CapturingFake(["read"]), cache=None)
    eng._llm_decide(DecideInput(
        goal="给 Android AI 开发组发消息",
        frame=frame,
        target_pkg="com.ss.android.lark",
        cursor=SkillCursor(), bound_skill=None, guard={}, title_keywords=(),
    ))

    user = captured[0]
    # 应同时存在 [SCENE-BRIEF: app] 段(因为 CHAT 在 app.chat 表)
    # 和飞书专属 brief 的内容
    assert "[SCENE-BRIEF" in user
    # 飞书专属 brief 关键词(选一个稳定的)
    assert "飞书" in user  # 飞书 brief 里含「飞书特有提示」
