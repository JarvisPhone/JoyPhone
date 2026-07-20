"""场景层:ScenarioPack 协议、AppProfile 数据与 UI 识别 helpers。"""
from app.scenario.base import AppProfile, ScenarioPack, select_scenario
from app.scenario.ui import (
    extract_target,
    is_message_input,
    is_send_button,
    match_title,
    resolve_pkg,
)

__all__ = [
    "AppProfile",
    "ScenarioPack",
    "extract_target",
    "is_message_input",
    "is_send_button",
    "match_title",
    "resolve_pkg",
    "select_scenario",
]
