"""把任务目标(自然语言)解析成目标 Android 应用 package。

目标 pkg 用于「app 边界」硬约束：云端决策时,一旦感知 pkg != 目标 pkg,就必须
先回桌面、再 home_first + 找图标重开目标 app,不能顺手 tap 通知/磁贴跳到
其他 app。

不依赖 LLM,纯关键字匹配(快、零成本、可单测)。后续若需要,再叠一层 LLM 兜底。
"""
from __future__ import annotations

import re
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


# ---- 目标标识符提取（群名 / 联系人）----
# 优先级：成对引号 > 成对书名号 > 裸词（在「给/找/发给/发给/搜索/搜/消息给/发给...」之后）
_BRACKETED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"[\u201c\u201d]([^\u201c\u201d]{2,40})[\u201c\u201d]"),  # "..."
    re.compile(r"[\u300c\u300d]([^\u300c\u300d]{2,40})[\u300c\u300d]"),  # 「...」
    re.compile(r"[\u300e\u300f]([^\u300e\u300f]{2,40})[\u300e\u300f]"),  # 『...』
)


def extract_target(goal: str) -> Optional[str]:
    """从自然语言 goal 里提取消息接收方(群名 / 联系人)。无法识别返回 None。

    三层匹配:
      1. 双引号 / 「」 / 『』 包起来的字符串("给『张三』发消息" -> 张三)
      2. 「给/发给/搜索/找 X 群/好友/消息」句式里 X(裸词,中文/英文 up to 40 字)
      3. 没匹配到 -> None (走 LLM 决策上下文,不强校验)
    """
    if not goal:
        return None

    # 1) 成对引号 / 书名号
    for pat in _BRACKETED_PATTERNS:
        m = pat.search(goal)
        if m:
            t = m.group(1).strip()
            if t:
                return t

    # 2) 句式抽取："给/发给/搜索/搜索 X 群" / "找 X 好友"
    #    X 是连续的汉字 / 英文 + 数字 / 下划线 / 连字符 / 空格
    structural = re.search(
        r"(?:给|发给|给到|发送给|发给|发消息给|搜索|搜|搜一下|找|找一下)\s*"
        r"([\u4e00-\u9fffA-Za-z0-9_\-\s]{2,40}?)\s*"
        r"(?:发|群|好友|联系人|发一条|发一条消息|发消息|发信息|发条消息|发条信息|发微信|发飞书|$)",
        goal,
    )
    if structural:
        t = structural.group(1).strip()
        # 去掉前缀干扰词（如"群" / "好友"）
        t = re.sub(r"^(群|好友|联系人|群组)\s*", "", t)
        if t:
            return t

    return None