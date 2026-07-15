"""把任务目标(自然语言)解析成目标 Android 应用 package。

目标 pkg 用于「app 边界」硬约束：云端决策时,一旦感知 pkg != 目标 pkg,就必须
先回桌面、再 home_first + 找图标重开目标 app,不能顺手 tap 通知/磁贴跳到
其他 app。

不依赖 LLM,纯关键字匹配(快、零成本、可单测)。后续若需要,再叠一层 LLM 兜底。
"""
from __future__ import annotations

from typing import Optional


_APP_ALIASES: list[tuple[str, tuple[str, ...]]] = [
    ("com.ss.android.lark", ("飞书", "feishu", "lark")),
    ("com.tencent.mm", ("微信", "wechat", "weixin")),
    ("com.tencent.mobileqq", ("qq",)),
    ("com.alibaba.android.rimet", ("钉钉", "dingtalk", "dingding")),
    ("com.taobao.taobao", ("淘宝", "taobao")),
    ("com.jingdong.app.mall", ("京东", "jd", "jingdong")),
    ("com.sankuai.meituan", ("美团", "meituan")),
    ("com.xingin.xhs", ("小红书", "xhs", "rednote", "xiaohongshu")),
    ("com.ss.android.ugc.aweme", ("抖音", "douyin", "tiktok")),
    ("com.zhihu.android", ("知乎", "zhihu")),
    ("com.autonavi.minimap", ("高德", "amap", "autonavi")),
    ("com.baidu.BaiduMap", ("百度地图", "baidu map")),
    ("com.tencent.map", ("腾讯地图", "tencent map")),
    ("com.android.dialer", ("电话", "dialer", "打电话", "call")),
    ("com.android.contacts", ("通讯录", "contacts")),
    ("com.android.settings", ("设置", "settings")),
    ("com.android.camera", ("相机", "camera")),
    ("com.google.android.apps.messaging", ("短信", "sms", "message")),
]


def resolve_target_pkg(goal: str) -> Optional[str]:
    """从 goal 里提取目标 app 的 package;无法识别返回 None。

    规则:goal 中出现任一别名(中文/英文,大小写不敏感)即返回首个匹配的 pkg。
    """
    if not goal:
        return None
    haystack = goal.lower()
    for pkg, aliases in _APP_ALIASES:
        for alias in aliases:
            if alias.lower() in haystack:
                return pkg
    return None


def is_known_pkg(pkg: str) -> bool:
    return pkg in {p for p, _ in _APP_ALIASES}