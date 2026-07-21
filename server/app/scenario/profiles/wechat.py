"""微信 AppProfile:UI 识别特征纯数据。

注意:关键词暂与飞书相同(占位),待真机校准后按微信实际
resource id / hint 文案调整。
"""
from app.scenario.base import AppProfile

# TODO: 以下关键词暂复用飞书配置,待真机校准(sample.capture 探针 -> 标注 -> 校准)
WECHAT_PROFILE = AppProfile(
    pkg="com.tencent.mm",
    aliases=["微信", "wechat", "weixin"],
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
