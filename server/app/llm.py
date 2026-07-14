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
import re


def _clean_text(text: str | None) -> str:
    """清洗 LLM 原始输出：仅剥离 <think>...</think> 推理标签，返回纯文本指令。

    文本指令协议下，LLM 返回多行「动词 + 参数」指令，不再是 JSON。
    MiniMax-M2.x thinking 无法关闭，content 会带 <think>...</think>，剥掉即可。
    None / 空输入返回空字符串。
    """
    if not text:
        return ""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


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
            temperature=1.0,
            extra_body={"thinking": {"type": "disabled"}},
        )
        _content = resp.choices[0].message.content
        import logging
        logging.getLogger("phoneagent.gateway").info(
            "[LLM-RAW-UNCLEANED] %r", _content
        )
        return _clean_text(_content)

def build_llm() -> LLM:
    _load_env_file()
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        return FakeLLM(["read"])

    from openai import OpenAI

    base_url = os.environ.get("LLM_BASE_URL")
    model = os.environ.get("LLM_MODEL", "MiniMax-M3")
    client = OpenAI(api_key=api_key, base_url=base_url)
    return RealLLM(client=client, model=model)


def _load_env_file() -> None:
    # 自动加载 server/.env（若存在），不覆盖已存在的进程环境变量。
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    from pathlib import Path

    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)