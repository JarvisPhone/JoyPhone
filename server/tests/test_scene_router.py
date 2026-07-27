# server/tests/test_scene_router.py
"""SceneRouter 纯函数场景路由单测（T1）。

route_by_scene 是「场景 -> handler」映射的唯一真相，按传入的 Scene 参数
分派，不重复 detect_scene：
- HOME / MINUS_ONE  -> home_locate（无 aliases 或 None -> None 回落 LLM）
- IN_APP 且 pkg==target -> None
- IN_APP 非目标 / NOTIFICATION / ... -> pkg_guard
"""
from __future__ import annotations

from app.decision.llm import FakeLLM
from app.decision.pkg_guard import Scene
from app.decision.scene_router import RouteContext, route_by_scene
from app.protocol import Node, Perception

_TARGET = "com.ss.android.lark"
_ALIASES = ["飞书", "Lark"]


def _home(nodes: list[Node]) -> Perception:
    ws = Node(id="ws", viewIdResourceName="com.coloros.launcher:id/workspace", bounds=(0, 0, 1080, 2400))
    return Perception(pkg="com.coloros.launcher", nodeTree=[ws, *nodes])


def _minus_one() -> Perception:
    ws = Node(id="ws", viewIdResourceName="com.coloros.launcher:id/workspace", bounds=(40, 60, 1040, 2340))
    return Perception(pkg="com.coloros.launcher", nodeTree=[ws])


def _ctx(frame: Perception, aliases: list[str] | None = None) -> RouteContext:
    return RouteContext(
        frame=frame,
        target_pkg=_TARGET,
        aliases=_ALIASES if aliases is None else aliases,
        guard={},
        escape_llm=FakeLLM(["back"]),
    )


def test_home_scene_routes_to_home_locate():
    # HOME + 有 aliases + 无目标图标 -> home_locate 归位滑动
    frame = _home([Node(id="1", text="微信")])
    result = route_by_scene(Scene.HOME, _ctx(frame))
    assert result is not None
    actions, source = result
    assert source == "home_locate"
    assert actions[0].op == "swipe"


def test_minus_one_routes_to_home_locate():
    # MINUS_ONE + 有 aliases -> home_locate
    result = route_by_scene(Scene.MINUS_ONE, _ctx(_minus_one()))
    assert result is not None
    _, source = result
    assert source == "home_locate"


def test_home_scene_no_aliases_returns_none():
    # HOME + aliases=[] -> None（回落 LLM）
    frame = _home([Node(id="1", text="微信")])
    assert route_by_scene(Scene.HOME, _ctx(frame, aliases=[])) is None


def test_in_app_target_returns_none():
    # IN_APP 且 frame.pkg == target_pkg -> None
    frame = Perception(pkg=_TARGET, nodeTree=[])
    assert route_by_scene(Scene.IN_APP, _ctx(frame)) is None


def test_in_app_non_target_routes_to_pkg_guard():
    # IN_APP 且 pkg != target -> pkg_guard
    frame = Perception(pkg="com.tencent.mm", nodeTree=[])
    result = route_by_scene(Scene.IN_APP, _ctx(frame))
    assert result is not None
    _, source = result
    assert source == "pkg_guard"


def test_notification_routes_to_pkg_guard():
    # NOTIFICATION 场景 -> pkg_guard
    frame = Perception(pkg="com.android.systemui", nodeTree=[])
    result = route_by_scene(Scene.NOTIFICATION, _ctx(frame))
    assert result is not None
    _, source = result
    assert source == "pkg_guard"