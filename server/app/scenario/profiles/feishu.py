"""飞书 AppProfile:UI 识别特征纯数据。

关键词取自旧 chat_title_helpers 硬编码:
  - title_rid_keywords <- _TITLE_RID_KEYWORDS
  - send_button_keywords <- _SEND_BUTTON_RID_KEYWORDS + _SEND_BUTTON_TEXT_KEYWORDS(合并)
  - search_hints <- _SEARCH_HINTS
  - message_input_hints <- _MSG_HINTS
"""
from app.scenario.base import AppProfile

FEISHU_PROFILE = AppProfile(
    pkg="com.ss.android.lark",
    aliases=["飞书", "feishu", "lark"],
    title_rid_keywords=[
        "title",
        "chat_name",
        "conversation_name",
        "tv_title",
        "tv_chat_name",
        "toolbar_title",
        "action_bar",
        "tv_conversation",
        "title_zone",
        "chat_info_view",
        # 群聊页群名节点(text=群名,如 "Android AI 开发组")— 2026-07-23 真机取自
        # comm.log 00:14:48 perception:id=0-0-1-1-2-0 不在默认集合里时,priority 1
        # 不命中,会退化命中 chat_message_list_view="Ra" 残留节点,触发 INPUT_GUARD
        # 误报 → 全帧 input 被拦截。
        "default_center_view_container",
        "chat_info_view_redesign",
    ],
    send_button_keywords=[
        "send_button",
        "btn_send",
        "iv_send",
        "send_btn",
        "ib_send",
        "tv_send",
        "sendmessage",
        "发送",
        "send",
        "sending",
    ],
    search_hints=[
        "搜索",
        "查找",
        "search",
    ],
    message_input_hints=[
        "输入",
        "发消息",
        "发送消息",
        "发送给",
        "说点什么",
        "写点什么",
        "message",
        "type a message",
    ],
    # 个人主页左侧抽屉(跨启动持久化,back 无效):特征 rid 取自真机帧
    sidebar_rid_keywords=[
        "cl_join_team",
        "layout_personal_status",
        "tenant_desc",
        "my_profile",
    ],
)
