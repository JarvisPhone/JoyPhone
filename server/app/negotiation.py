import json

from app.llm import LLM


class NegotiationBot:
    def __init__(self, llm: LLM):
        self._llm = llm

    def respond(self, goal: str, incoming: str, history: list[dict]) -> dict:
        payload = {"goal": goal, "incoming": incoming, "history": history}
        raw = self._llm.complete(
            system="negotiate next reply",
            user=json.dumps(payload, ensure_ascii=False),
        )
        return json.loads(raw)