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
        if not responses:
            raise ValueError("responses must not be empty")
        self._responses = responses
        self._index = 0

    def complete(self, system: str, user: str, image_b64: str | None = None) -> str:
        if self._index < len(self._responses):
            value = self._responses[self._index]
            self._index += 1
            return value
        return self._responses[-1]