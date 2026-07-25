"""退出路径模板库。

每个 Scene / AppPage 给出标准退出路径,LLM 决策时如果不知道「当前怎么出去」,
按 exit_hint 提示找方向。LoopGuard 触发后也可以把 exit_hint 当作反馈文本。

设计上:模板纯文本,不调用 LLM,使用 `_` 占位由调用方填入。
"""
from __future__ import annotations

from app.decision.app_page import AppPage
from app.decision.pkg_guard import Scene


# --- 顶层场景退出提示 ---

_SCENE_HINTS: dict[Scene, str] = {
    Scene.HOME:
        "桌面: 无需退出,直接 tap 目标应用图标",
    Scene.MINUS_ONE:
        "负一屏: swipe right 向右滑退出回到桌面;或按 home 键",
    Scene.NOTIFICATION:
        "下拉通知栏: swipe up 或 back 收起",
    Scene.CONTROL_CENTER:
        "控制中心: swipe up 或 back 收起",
    Scene.IN_APP:
        "在 App 内: 单个 back 退出当前二级页回到上一页;不要连按 back+home",
    Scene.LOCK_SCREEN:
        "锁屏: 先 unlock 设备再继续任务",
    Scene.RECENT_APPS:
        "最近任务: 按 home 键回到桌面",
    Scene.UNKNOWN:
        "未知场景: 单 back 尝试;若不变化则按 home 键兜底回桌面",
}


# --- App 内页型退出提示(优先级高于 Scene.IN_APP 通用提示)----

_APP_PAGE_HINTS: dict[AppPage, str] = {
    AppPage.INBOX_LIST:
        "消息/通讯录列表: 无需退出,在列表内找目标;可用顶部搜索",
    AppPage.CHAT:
        "聊天会话页: 单 back 返回上一级会话列表;不要按 home 退出 app",
    AppPage.CONTACT_INFO:
        "联系人详情页: 单 back 返回上一级",
    AppPage.GROUP_INFO:
        "群详情页: 单 back 返回会话页",
    AppPage.SETTINGS:
        "设置页: 单 back 返回上一级;多层设置需多次 back,不要一次 home 退",
    AppPage.SEARCH:
        "搜索结果页: 单 back 或点左上角返回箭头",
    AppPage.UNKNOWN:
        "app 内未识别页: 单 back 尝试;若 1 帧未变化则 home 兜底",
}


def hint_for_scene(scene: Scene) -> str:
    """顶层场景的退出提示。"""
    return _SCENE_HINTS.get(scene, _SCENE_HINTS[Scene.UNKNOWN])


def hint_for_app_page(page: AppPage) -> str:
    """App 内页型的退出提示。"""
    return _APP_PAGE_HINTS.get(page, _APP_PAGE_HINTS[AppPage.UNKNOWN])


def exit_hint(scene: Scene, page: AppPage) -> str:
    """组合退出提示:scene 通用 + page 特定(page=UNKNOWN 时只返回 scene 提示)。"""
    base = hint_for_scene(scene)
    if page == AppPage.UNKNOWN:
        return base
    page_hint = hint_for_app_page(page)
    # 同一行的两个分句用「·」分隔
    return f"{base} · {page_hint}"