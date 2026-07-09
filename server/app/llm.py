from __future__ import annotations

from abc import ABC, abstractmethod


class LLM(ABC):
    @abstractmethod
    def complete(
        self,
        system: str,
        user: str,
        image_b64: str | None = None,
    ) -> str:
        raise NotImplementedError


class FakeLLM(LLM):
    def __init__(self, responses: list[str]):
        self._responses = responses
        self._index = 0

    def complete(self, system: str, user: str, image_b64: str | None = None) -> str:
        if self._index < len(self._responses):
            value = self._responses[self._index]
            self._index += 1
            return value
        return self._responses[-1]


import os


class RealLLM(LLM):
    def __init__(self, client, model: str):
        self._client = client
        self._model = model

    def complete(self, system: str, user: str, image_b64: str | None = None) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,
        )
        return resp.choices[0].message.content


def build_llm() -> LLM:
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        return FakeLLM(['{"op":"read_screen","params":{}}'])

    from openai import OpenAI

    base_url = os.environ.get("LLM_BASE_URL")
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    client = OpenAI(api_key=api_key, base_url=base_url)
    return RealLLM(client=client, model=model)