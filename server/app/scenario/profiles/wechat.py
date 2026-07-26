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
    # 微信 vs 飞书差异:微信会话页底部无 IM 风格常驻工具栏,返回键靠左上角「<」
    # 而不是标题栏;朋友圈/视频号入口是底部 tab「通讯录」≠ 飞书工作台。
    # 真机校准未做(2026-07-26):仅列与飞书行为差异点,等真机数据沉淀。
    llm_brief=(
        "微信特有提示:\n"
        "- 会话页顶部标题栏「<」是返回,不是群设置(微信无群设置面板,\n"
        "  长按会话/消息列表项才触发操作菜单)。\n"
        "- 发送按钮位置固定在输入框右侧(飞书在工具栏中段)。\n"
        "- 微信「通讯录」tab ≠ 飞书「工作台」,top tab 顺序:微信/通讯录/发现/我。\n"
        "- 「发现」tab 含朋友圈/视频号/小程序,**任务目标 app=微信时这里全是干扰**。\n"
        "- 实装关键词占位(待真机校准):expect match_text 时同时备好飞书+微信双语锚点。"
    ),
)
