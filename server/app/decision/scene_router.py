"""SceneRouter：场景 -> handler 的纯函数路由器。

把「哪个场景归哪个 handler 管辖」这条职责边界抽成独立纯函数，避免
pkg_guard / home_locate 各自 detect_scene 各自主张桌面管辖权导致的短路
（真机 bug：pkg_guard 排前面把 HOME/MINUS_ONE 抢走 return，短路 home_locate）。

route_by_scene 按「传入的 Scene 参数」分派，自身不重复 detect_scene——
scene 由调用方（engine）一次性判定后传入，保证全链唯一真相。

职责边界（唯一真相）：
- HOME / MINUS_ONE           -> home_locate（无 aliases 或返回 None -> None 回落 LLM）
- IN_APP 且 pkg == target    -> None（已在目标 app，回落 LLM 正常决策）
- IN_APP 非目标 / NOTIFICATION / CONTROL_CENTER / RECENT_APPS
  / LOCK_SCREEN / UNKNOWN     -> pkg_guard
"""
from __future__ import annotations

from dataclasses import dataclass

from app.decision.home_locate import home_locate_action
from app.decision.llm import LLM
from app.decision.pkg_guard import Scene, pkg_guard_action
from app.decision.types import DecisionSource
from app.protocol import Action, Perception


@dataclass
class RouteContext:
    """一次路由所需的全部上下文（纯数据，无行为）。"""
    frame: Perception
    target_pkg: str
    aliases: list[str]
    guard: dict
    escape_llm: LLM


def route_by_scene(
    scene: Scene, ctx: RouteContext
) -> tuple[list[Action], DecisionSource] | None:
    """按 scene 分派到对应 handler；handler 不介入时返回 None（回落 LLM）。"""
    if scene in (Scene.HOME, Scene.MINUS_ONE):
        located = home_locate_action(ctx.frame, ctx.target_pkg, ctx.aliases, ctx.guard)
        return (located, "home_locate") if located is not None else None
    if scene == Scene.IN_APP and ctx.frame.pkg == ctx.target_pkg:
        return None
    guarded = pkg_guard_action(ctx.frame, ctx.target_pkg, ctx.guard, ctx.escape_llm)
    return (guarded, "pkg_guard") if guarded is not None else None