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
        "说点什么",
        "写点什么",
        "message",
        "type a message",
    ],
)
