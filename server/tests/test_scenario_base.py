"""scenario 基础层测试:ScenarioPack 选择、AppProfile 数据、resolve_pkg。"""
from app.scenario.base import AppProfile, ScenarioPack, select_scenario
from app.scenario.profiles.feishu import FEISHU_PROFILE
from app.scenario.profiles.wechat import WECHAT_PROFILE
from app.scenario.ui import resolve_pkg


class _Pack:
    """最小 ScenarioPack 实现(仅 name + matches)。"""

    name = "p"

    def __init__(self, score: float):
        self._score = score

    def matches(self, goal: str) -> float:
        return self._score


def test_select_scenario_picks_highest_score():
    assert select_scenario([_Pack(0.1), _Pack(0.9)], "g").name == "p"
    assert select_scenario([_Pack(0.0)], "g") is None
    assert select_scenario([], "g") is None


def test_select_scenario_returns_the_highest_scoring_pack():
    low, high = _Pack(0.2), _Pack(0.8)
    assert select_scenario([low, high], "g") is high


def test_resolve_pkg_from_profile_aliases():
    assert resolve_pkg("给飞书群发消息", [FEISHU_PROFILE]) == "com.ss.android.lark"
    assert resolve_pkg("open lark and send hi", [FEISHU_PROFILE]) == "com.ss.android.lark"
    assert resolve_pkg("在微信里找张三", [FEISHU_PROFILE, WECHAT_PROFILE]) == "com.tencent.mm"


def test_resolve_pkg_unknown_returns_none():
    assert resolve_pkg("打开计算器", [FEISHU_PROFILE, WECHAT_PROFILE]) is None
    assert resolve_pkg("", [FEISHU_PROFILE]) is None


def test_app_profile_fields():
    p = FEISHU_PROFILE
    assert p.pkg == "com.ss.android.lark"
    assert "飞书" in p.aliases
    assert "title" in p.title_rid_keywords
    assert "btn_send" in p.send_button_keywords
    assert "搜索" in p.search_hints
    assert "发消息" in p.message_input_hints
    assert WECHAT_PROFILE.pkg == "com.tencent.mm"


def test_scenario_pack_protocol_structural():
    """Protocol 仅做结构约束,不强制 isinstance。"""

    class Full:
        name = "full"

        def matches(self, goal):
            return 1.0

        def resolve_target(self, goal):
            return None

        def skills(self):
            return []

        def pre_policies(self):
            return []

        def post_policies(self):
            return []

        def ui_profile(self, pkg):
            return FEISHU_PROFILE

    pack: ScenarioPack = Full()
    assert select_scenario([pack], "g") is pack


def test_app_profile_is_pydantic_model():
    p = AppProfile(
        pkg="com.x",
        aliases=["x"],
        title_rid_keywords=[],
        send_button_keywords=[],
        search_hints=[],
        message_input_hints=[],
    )
    assert p.pkg == "com.x"
