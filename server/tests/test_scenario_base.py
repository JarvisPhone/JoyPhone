"""scenario 基础层测试:ScenarioPack 选择、AppProfile 数据、resolve_pkg。"""
from app.scenario.base import AppProfile, ScenarioPack, select_scenario
from app.scenario.profiles import ALL_PROFILES
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


def test_all_profiles_cover_legacy_aliases():
    """旧 app_goal_resolver 18 个别名条目全部归位(回归:别名覆盖不得缩窄)。"""
    assert resolve_pkg("打开设置", ALL_PROFILES) == "com.android.settings"
    assert resolve_pkg("给QQ好友发消息", ALL_PROFILES) == "com.tencent.mobileqq"
    assert resolve_pkg("打开钉钉打卡", ALL_PROFILES) == "com.alibaba.android.rimet"
    assert resolve_pkg("淘宝上搜一下", ALL_PROFILES) == "com.taobao.taobao"
    assert resolve_pkg("打开京东", ALL_PROFILES) == "com.jingdong.app.mall"
    assert resolve_pkg("美团点个外卖", ALL_PROFILES) == "com.sankuai.meituan"
    assert resolve_pkg("刷小红书", ALL_PROFILES) == "com.xingin.xhs"
    assert resolve_pkg("打开抖音", ALL_PROFILES) == "com.ss.android.ugc.aweme"
    assert resolve_pkg("知乎上搜一下", ALL_PROFILES) == "com.zhihu.android"
    assert resolve_pkg("用高德导航", ALL_PROFILES) == "com.autonavi.minimap"
    assert resolve_pkg("打开百度地图", ALL_PROFILES) == "com.baidu.BaiduMap"
    assert resolve_pkg("打开腾讯地图", ALL_PROFILES) == "com.tencent.map"
    assert resolve_pkg("打电话", ALL_PROFILES) == "com.android.dialer"
    assert resolve_pkg("打开通讯录", ALL_PROFILES) == "com.android.contacts"
    assert resolve_pkg("打开相机", ALL_PROFILES) == "com.android.camera"
    assert resolve_pkg("发条短信", ALL_PROFILES) == "com.google.android.apps.messaging"
    assert resolve_pkg("打开计算器", ALL_PROFILES) is None


def test_all_profiles_order_matches_legacy():
    """ALL_PROFILES 顺序与旧别名表一致(飞书/微信在前,保证首个匹配语义)。"""
    assert [p.pkg for p in ALL_PROFILES[:2]] == [
        "com.ss.android.lark",
        "com.tencent.mm",
    ]
    assert len(ALL_PROFILES) == 18


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
