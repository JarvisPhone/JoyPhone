"""内置 app UI profile。"""
from app.scenario.profiles.feishu import FEISHU_PROFILE
from app.scenario.profiles.misc import MISC_PROFILES
from app.scenario.profiles.wechat import WECHAT_PROFILE

# 全量注册列表:顺序与旧 app_goal_resolver._APP_ALIASES 一致,
# resolve_pkg 按顺序取首个别名命中。
ALL_PROFILES = [FEISHU_PROFILE, WECHAT_PROFILE, *MISC_PROFILES]

__all__ = ["ALL_PROFILES", "FEISHU_PROFILE", "WECHAT_PROFILE"]
