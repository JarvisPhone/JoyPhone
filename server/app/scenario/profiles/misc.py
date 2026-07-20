"""其余 app 的最小 AppProfile:仅别名(pkg + aliases),无 UI 识别关键词。

别名照抄旧 app_goal_resolver._APP_ALIASES(00ded0a),保证 resolve_pkg
对钉钉/QQ/淘宝等 goal 的解析与旧行为一致(pkg_guard 边界约束不失效)。
飞书 / 微信有完整 UI 关键词,归 feishu.py / wechat.py,不在此列。
"""
from app.scenario.base import AppProfile

QQ_PROFILE = AppProfile(
    pkg="com.tencent.mobileqq",
    aliases=["qq"],
    title_rid_keywords=[],
    send_button_keywords=[],
    search_hints=[],
    message_input_hints=[],
)

DINGTALK_PROFILE = AppProfile(
    pkg="com.alibaba.android.rimet",
    aliases=["钉钉", "dingtalk", "dingding"],
    title_rid_keywords=[],
    send_button_keywords=[],
    search_hints=[],
    message_input_hints=[],
)

TAOBAO_PROFILE = AppProfile(
    pkg="com.taobao.taobao",
    aliases=["淘宝", "taobao"],
    title_rid_keywords=[],
    send_button_keywords=[],
    search_hints=[],
    message_input_hints=[],
)

JD_PROFILE = AppProfile(
    pkg="com.jingdong.app.mall",
    aliases=["京东", "jd", "jingdong"],
    title_rid_keywords=[],
    send_button_keywords=[],
    search_hints=[],
    message_input_hints=[],
)

MEITUAN_PROFILE = AppProfile(
    pkg="com.sankuai.meituan",
    aliases=["美团", "meituan"],
    title_rid_keywords=[],
    send_button_keywords=[],
    search_hints=[],
    message_input_hints=[],
)

XHS_PROFILE = AppProfile(
    pkg="com.xingin.xhs",
    aliases=["小红书", "xhs", "rednote", "xiaohongshu"],
    title_rid_keywords=[],
    send_button_keywords=[],
    search_hints=[],
    message_input_hints=[],
)

DOUYIN_PROFILE = AppProfile(
    pkg="com.ss.android.ugc.aweme",
    aliases=["抖音", "douyin", "tiktok"],
    title_rid_keywords=[],
    send_button_keywords=[],
    search_hints=[],
    message_input_hints=[],
)

ZHIHU_PROFILE = AppProfile(
    pkg="com.zhihu.android",
    aliases=["知乎", "zhihu"],
    title_rid_keywords=[],
    send_button_keywords=[],
    search_hints=[],
    message_input_hints=[],
)

AMAP_PROFILE = AppProfile(
    pkg="com.autonavi.minimap",
    aliases=["高德", "amap", "autonavi"],
    title_rid_keywords=[],
    send_button_keywords=[],
    search_hints=[],
    message_input_hints=[],
)

BAIDU_MAP_PROFILE = AppProfile(
    pkg="com.baidu.BaiduMap",
    aliases=["百度地图", "baidu map"],
    title_rid_keywords=[],
    send_button_keywords=[],
    search_hints=[],
    message_input_hints=[],
)

TENCENT_MAP_PROFILE = AppProfile(
    pkg="com.tencent.map",
    aliases=["腾讯地图", "tencent map"],
    title_rid_keywords=[],
    send_button_keywords=[],
    search_hints=[],
    message_input_hints=[],
)

DIALER_PROFILE = AppProfile(
    pkg="com.android.dialer",
    aliases=["电话", "dialer", "打电话", "call"],
    title_rid_keywords=[],
    send_button_keywords=[],
    search_hints=[],
    message_input_hints=[],
)

CONTACTS_PROFILE = AppProfile(
    pkg="com.android.contacts",
    aliases=["通讯录", "contacts"],
    title_rid_keywords=[],
    send_button_keywords=[],
    search_hints=[],
    message_input_hints=[],
)

SETTINGS_PROFILE = AppProfile(
    pkg="com.android.settings",
    aliases=["设置", "settings"],
    title_rid_keywords=[],
    send_button_keywords=[],
    search_hints=[],
    message_input_hints=[],
)

CAMERA_PROFILE = AppProfile(
    pkg="com.android.camera",
    aliases=["相机", "camera"],
    title_rid_keywords=[],
    send_button_keywords=[],
    search_hints=[],
    message_input_hints=[],
)

MESSAGING_PROFILE = AppProfile(
    pkg="com.google.android.apps.messaging",
    aliases=["短信", "sms", "message"],
    title_rid_keywords=[],
    send_button_keywords=[],
    search_hints=[],
    message_input_hints=[],
)

# 顺序与旧 _APP_ALIASES 一致(飞书/微信在 profiles/__init__ 的 ALL_PROFILES 里补前两位)
MISC_PROFILES: list[AppProfile] = [
    QQ_PROFILE,
    DINGTALK_PROFILE,
    TAOBAO_PROFILE,
    JD_PROFILE,
    MEITUAN_PROFILE,
    XHS_PROFILE,
    DOUYIN_PROFILE,
    ZHIHU_PROFILE,
    AMAP_PROFILE,
    BAIDU_MAP_PROFILE,
    TENCENT_MAP_PROFILE,
    DIALER_PROFILE,
    CONTACTS_PROFILE,
    SETTINGS_PROFILE,
    CAMERA_PROFILE,
    MESSAGING_PROFILE,
]
