import json
import logging
from enum import Enum
from typing import Literal

from app.llm import LLM


logger = logging.getLogger("phoneagent.negotiation")


class NegotiationIntent(Enum):
    CONFIRM = "confirm"
    REJECT = "reject"
    NEGOTIATE = "negotiate"
    ESCALATE = "escalate"
    UNKNOWN = "unknown"


class NegotiationAction(Enum):
    CONTINUE = "continue"
    DONE = "done"
    ESCALATE = "escalate"


_INTENT_SYSTEM_PROMPT = """你是一个消息意图分类器。根据对方回复判断其意图（只能输出一个词）：

- confirm: 明确同意/确认（如"好的"、"可以"、"知道了"、"同意"）
- reject: 明确拒绝（如"不要"、"不需要"、"算了"）
- negotiate: 提出条件/讨价还价（如"能便宜点吗"、"分期可以吗"、"再考虑"）
- escalate: 要求转人工/投诉（如"转人工"、"找客服"、"投诉"）
- unknown: 无法判断

对方回复: {incoming}

意图:"""


_NEGOTIATION_SYSTEM_PROMPT = """你是一个专业的商务协商助手。根据任务目标和对话历史，生成下一轮回复。

任务目标: {goal}

对话历史:
{history}

对方最新回复: {incoming}

请生成回复，回复要简洁、专业、有说服力。如果对方同意了，表示感谢并确认；如果对方在讨价还价，给出合理方案；如果对方拒绝或要转人工，按照指示处理。

回复格式（JSON）：
{{"action": "continue|done|escalate", "reply": "你的回复文本"}}

action说明：
- continue: 继续协商，等待对方下一步回复
- done: 对方已确认/同意，任务完成
- escalate: 需要转人工处理"""


class NegotiationBot:
    def __init__(self, llm: LLM):
        self._llm = llm

    def classify_intent(self, text: str) -> NegotiationIntent:
        if not text or not text.strip():
            return NegotiationIntent.UNKNOWN

        try:
            prompt = _INTENT_SYSTEM_PROMPT.format(incoming=text)
            result = self._llm.complete(system=prompt, user="")
            result = result.strip().lower()

            if "confirm" in result or "同意" in text or "好的" in text:
                return NegotiationIntent.CONFIRM
            if "reject" in result or "不要" in text or "拒绝" in text:
                return NegotiationIntent.REJECT
            if "negotiate" in result or "便宜" in text or "分期" in text or "考虑" in text:
                return NegotiationIntent.NEGOTIATE
            if "escalate" in result or "人工" in text or "客服" in text or "投诉" in text:
                return NegotiationIntent.ESCALATE
            return NegotiationIntent.UNKNOWN
        except Exception as e:
            logger.warning(f"Intent classification failed: {e}")
            return NegotiationIntent.UNKNOWN

    def respond(
        self,
        goal: str,
        incoming: str,
        history: list[dict],
    ) -> dict:
        if not incoming or not incoming.strip():
            return {"action": NegotiationAction.CONTINUE.value, "reply": ""}

        intent = self.classify_intent(incoming)

        if intent == NegotiationIntent.CONFIRM:
            return {
                "action": NegotiationAction.DONE.value,
                "reply": "好的，感谢您的确认！任务已完成。",
            }

        if intent == NegotiationIntent.ESCALATE:
            return {
                "action": NegotiationAction.ESCALATE.value,
                "reply": "好的，我将为您转接人工客服，请稍候。",
            }

        if intent == NegotiationIntent.REJECT:
            return {
                "action": NegotiationAction.ESCALATE.value,
                "reply": "明白了，如果您有其他需要，请随时告诉我。",
            }

        history_text = self._format_history(history)
        try:
            prompt = _NEGOTIATION_SYSTEM_PROMPT.format(
                goal=goal,
                history=history_text,
                incoming=incoming,
            )
            raw = self._llm.complete(system=prompt, user="")
            return self._parse_response(raw)
        except Exception as e:
            logger.error(f"Negotiation response failed: {e}")
            return {"action": NegotiationAction.CONTINUE.value, "reply": "收到，请继续。"}

    def _format_history(self, history: list[dict]) -> str:
        if not history:
            return "（无历史记录）"
        lines = []
        for i, msg in enumerate(history[-5:], 1):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            lines.append(f"{i}. [{role}]: {content}")
        return "\n".join(lines)

    def _parse_response(self, raw: str) -> dict:
        try:
            data = json.loads(raw)
            if "action" in data and "reply" in data:
                return {
                    "action": data.get("action", "continue"),
                    "reply": data.get("reply", ""),
                }
        except json.JSONDecodeError:
            pass

        lines = raw.strip().split("\n")
        reply = " ".join(line.strip() for line in lines if line.strip())
        return {"action": NegotiationAction.CONTINUE.value, "reply": reply}
