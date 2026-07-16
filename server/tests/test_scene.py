"""屏幕场景状态机测试。用真机采样数据(tests/fixtures/scenes/*.json)作输入,
验证 detect_scene 能把每份采样正确归类到对应 Scene。

区分规则(与人工分析对齐):
- 非 launcher/systemui 包 -> IN_APP(目标App内)
- systemui + lock_icon_view/keyguard -> LOCK_SCREEN
- systemui + expandableNotificationRow -> NOTIFICATION
- systemui + qs 磁贴 -> CONTROL_CENTER
- launcher + overview_panel -> RECENT_APPS
- launcher + workspace 全屏[0,0,..] -> HOME
- launcher + workspace 内缩(left/top>0) -> MINUS_ONE(负一屏)
"""
import glob
import json
import os

import pytest

from app.protocol import Perception
from app.scene import Scene, detect_scene, next_action

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures", "scenes")

# 文件名前缀 -> 期望场景
_EXPECT = {
    "home_first": Scene.HOME,
    "home_other": Scene.HOME,
    "minus_one": Scene.MINUS_ONE,
    "notification": Scene.NOTIFICATION,
    "control_center": Scene.CONTROL_CENTER,
    "in_target_app_lark": Scene.IN_APP,
    "lock_screen": Scene.LOCK_SCREEN,
    "recent_apps": Scene.RECENT_APPS,
}


def _load(prefix: str) -> Perception:
    matches = glob.glob(os.path.join(_FIXTURE_DIR, f"{prefix}-*.json"))
    assert matches, f"fixture not found for {prefix}"
    data = json.load(open(matches[0], encoding="utf-8"))
    return Perception(
        nodeTree=data["nodeTree"],
        pkg=data.get("pkg", ""),
        activity=data.get("activity", ""),
        ts=data.get("ts", 0),
    )


@pytest.mark.parametrize("prefix,expected", list(_EXPECT.items()))
def test_detect_scene_from_real_samples(prefix: str, expected: Scene):
    perception = _load(prefix)
    assert detect_scene(perception) == expected


def test_home_first_and_other_both_home():
    """首屏/其他屏都归 HOME(workspace bounds 相同,无需也无法区分)。"""
    assert detect_scene(_load("home_first")) == Scene.HOME
    assert detect_scene(_load("home_other")) == Scene.HOME


def test_target_app_takes_priority():
    """飞书包名直接判 IN_APP,不受节点内容干扰。"""
    assert detect_scene(_load("in_target_app_lark")) == Scene.IN_APP


def test_empty_perception_is_unknown():
    """空感知(无 pkg 无节点)归 UNKNOWN,不崩溃。"""
    assert detect_scene(Perception(nodeTree=[], pkg="", activity="")) == Scene.UNKNOWN


# ==== 场景转移表: next_action(current, target) 返回朝 target 收敛的下一个动作 ====
# LLM 只报目标场景,本地转移表负责导航;外层逐帧重判 scene 直到到位。

def test_next_action_returns_none_when_already_at_target():
    """已在目标场景 -> 无需动作,返回 None。"""
    assert next_action(Scene.HOME, Scene.HOME) is None
    assert next_action(Scene.IN_APP, Scene.IN_APP) is None


def test_minus_one_to_home_swipes_right():
    """负一屏在桌面最左,向右滑退出回到桌面。"""
    act = next_action(Scene.MINUS_ONE, Scene.HOME)
    assert act.op == "swipe"
    assert act.params.get("direction") == "right"


def test_recent_apps_to_home_presses_home():
    """最近任务界面按 home 键回桌面。"""
    act = next_action(Scene.RECENT_APPS, Scene.HOME)
    assert act.op == "home"


def test_notification_to_home_goes_back():
    """下拉通知栏 back 收起。"""
    act = next_action(Scene.NOTIFICATION, Scene.HOME)
    assert act.op == "back"


def test_control_center_to_home_goes_back():
    """控制中心 back 收起。"""
    act = next_action(Scene.CONTROL_CENTER, Scene.HOME)
    assert act.op == "back"


def test_in_app_to_home_uses_home_first_page():
    """在 App 内回桌面并归位到第一屏。"""
    act = next_action(Scene.IN_APP, Scene.HOME)
    assert act.op == "home_first_page"


def test_unknown_to_home_falls_back_to_home_first_page():
    """未知场景兜底: home_first_page 尝试收敛回确定起点。"""
    act = next_action(Scene.UNKNOWN, Scene.HOME)
    assert act.op == "home_first_page"


def test_lock_screen_to_home_falls_back():
    """锁屏暂无解锁能力,兜底 home_first_page(实际需人工/后续扩展解锁)。"""
    act = next_action(Scene.LOCK_SCREEN, Scene.HOME)
    assert act.op == "home_first_page"


def test_fallback_action_minus_one_tries_home():
    from app.scene import fallback_action
    act = fallback_action(Scene.MINUS_ONE, Scene.HOME)
    assert act is not None and act.op == "home"  # 主动作 swipe right 失效后的备选


def test_fallback_action_unknown_scene_returns_home():
    from app.scene import fallback_action
    act = fallback_action(Scene.UNKNOWN, Scene.HOME)
    assert act is not None and act.op == "home"


def test_fallback_action_already_at_target_none():
    from app.scene import fallback_action
    assert fallback_action(Scene.HOME, Scene.HOME) is None


def test_next_action_generates_fresh_action_id():
    """每次返回的 Action 带唯一 actionId,不复用。"""
    a1 = next_action(Scene.MINUS_ONE, Scene.HOME)
    a2 = next_action(Scene.MINUS_ONE, Scene.HOME)
    assert a1.actionId and a2.actionId and a1.actionId != a2.actionId