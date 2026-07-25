"""Scene × AppPage 专有 brief 注册表(LLM 决策时按当前 scene 注入)。

设计目标:把「这个场景最容易踩的坑」变成可注入的自然语言段,
不靠 prompt 教学让 LLM 自己推理。

brief 文风约束:
- 每段最多 5 行
- 一段只讲一件事(避免 LLM 抓不住重点)
- 默认中文(项目惯例),英文也行
- 通用 brief 写在本文件,app-specific 通过 AppProfile.llm_brief 注入
"""
from __future__ import annotations

from app.decision.app_page import AppPage
from app.decision.pkg_guard import Scene

# (scene, page) → brief 正文
# None 表示该组合无 brief(scene-level 已经有通用提示,不要重复)
_BRIEFS: dict[tuple[Scene, AppPage], str] = {
    # 顶层 scene
    (Scene.HOME, AppPage.UNKNOWN):
        "桌面: 直接 tap 目标应用图标。已 swipe 过最近 app 的请看 [OBSERVE] 顶部 tab 是否真的在桌面上(负一屏会误识别为可用图标)。",

    (Scene.MINUS_ONE, AppPage.UNKNOWN):
        "这是桌面「负一屏」(ColorOS 小布建议),**不是真正的桌面**。"
        "「XX 有 N 条通知」「XX 推荐」是磁贴,不是应用图标。\n"
        "退出:swipe right → 回到 launcher.home。",

    (Scene.NOTIFICATION, AppPage.UNKNOWN):
        "下拉通知栏。点通知会跳到对应 app 的具体页面,本任务通常不期望此行为。\n"
        "退出:swipe up 或 back 收起。",

    (Scene.CONTROL_CENTER, AppPage.UNKNOWN):
        "下拉控制中心。退出:swipe up 或 back 收起。",

    (Scene.LOCK_SCREEN, AppPage.UNKNOWN):
        "锁屏。先 unlock 设备再继续任务。unlock 方式因设备而异,常见是 swipe up。",

    (Scene.RECENT_APPS, AppPage.UNKNOWN):
        "最近任务视图。退出:按 home 回桌面。",

    # app 内页型
    (Scene.IN_APP, AppPage.INBOX_LIST):
        "消息/通讯录列表页。需要时可 tap 顶部搜索框;列表内可 swipe up/down 滚动。\n"
        "不要点标题栏(会进设置)。",

    (Scene.IN_APP, AppPage.CHAT):
        "聊天会话页。**单 back 返回上一级列表,不要按 home 退 app**。\n"
        "**严禁点击顶部标题栏**——那是群设置入口,误进立刻 single back。\n"
        "不确定是不是目标会话? 用 `expect title \"X\"` 核查,不要肉眼判断。",

    (Scene.IN_APP, AppPage.CONTACT_INFO):
        "联系人详情页。单 back 返回上一级。\n"
        "若想给联系人发消息,看是否有「发消息」按钮(常见 rid: btn_chat)。",

    (Scene.IN_APP, AppPage.GROUP_INFO):
        "群详情页。单 back 返回会话页。\n"
        "不要在这里点「群设置」之外的任何东西。",

    (Scene.IN_APP, AppPage.SETTINGS):
        "设置页。单 back 返回上一级;多层设置需多次 back。\n"
        "不要一次 home 退 app——会丢掉任务目标 app 内的导航进度。",

    (Scene.IN_APP, AppPage.SEARCH):
        "搜索结果页。结果列表里点目标那一行(不是搜索框本身)。\n"
        "单 back 或点左上角返回箭头回列表。",
}


def brief_for(scene: Scene, page: AppPage) -> str | None:
    """按 (scene, page) 查 brief;未命中返回 None(由调用方决定是否注入)。

    优先级:精确 (scene, page) > (scene, UNKNOWN) > None
    """
    key = (scene, page)
    if key in _BRIEFS:
        return _BRIEFS[key]
    # page 退化:找 (scene, UNKNOWN)
    fallback = (scene, AppPage.UNKNOWN)
    if fallback in _BRIEFS and fallback != key:
        return _BRIEFS[fallback]
    return None
