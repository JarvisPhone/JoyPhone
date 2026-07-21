import logging
import os
import re
from abc import ABC, abstractmethod
from typing import Optional

import httpx

logger = logging.getLogger("phoneagent.llm")


class LLMError(Exception):
    pass


class LLM(ABC):
    @abstractmethod
    def complete(self, system: str, user: str, image_b64: str | None = None) -> str:
        ...


def _clean_text(text: str | None) -> str:
    """剥掉 <think>...</think> 推理标签，返回纯文本指令。"""
    if not text:
        return ""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


class FakeLLM(LLM):
    def __init__(self, responses: list[str | None] | str | None = None):
        if responses is None:
            responses = ["read"]
        elif isinstance(responses, (str, type(None))):
            responses = [responses]
        self._responses = list(responses)
        self._index = 0

    def complete(self, system: str, user: str, image_b64: str | None = None) -> str:
        if not self._responses:
            return ""
        if self._index >= len(self._responses):
            return self._responses[-1] or ""
        resp = self._responses[self._index]
        self._index += 1
        return resp if resp is not None else ""


class RealLLM(LLM):
    def __init__(self, client, model: str):
        self._client = client
        self._model = model

    def complete(self, system: str, user: str, image_b64: str | None = None) -> str:
        # 原始流量落 llm.log(延迟导入避免 decision->gateway 的模块级依赖)
        from app.gateway.connection import log_llm_req, log_llm_resp
        log_llm_req(user)
        try:
            messages: list[dict] = [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
            if image_b64:
                messages.append({
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_b64}"}},
                    ],
                })

            resp = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=1.0,
                extra_body={"thinking": {"type": "disabled"}},
            )
            _content = resp.choices[0].message.content
            cleaned = _clean_text(_content)
            log_llm_resp(cleaned)
            return cleaned

        except httpx.HTTPStatusError as e:
            logger.error("LLM HTTP error: %s %s", e.response.status_code, e.response.text)
            raise LLMError(f"LLM HTTP error: {e.response.status_code}") from e
        except Exception as e:
            logger.error("LLM call failed: %s", e)
            raise LLMError(f"LLM call failed: {e}") from e


def build_llm() -> LLM:
    _load_env_file()
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        logger.info("No LLM_API_KEY found, using FakeLLM")
        return FakeLLM(["read"])

    try:
        from openai import OpenAI
    except ImportError:
        logger.warning("OpenAI SDK not installed, using FakeLLM")
        return FakeLLM(["read"])

    base_url = os.environ.get("LLM_BASE_URL")
    model = os.environ.get("LLM_MODEL", "MiniMax-M3")

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        return RealLLM(client=client, model=model)
    except Exception as e:
        logger.error("Failed to create LLM client: %s", e)
        return FakeLLM(["read"])


def _load_env_file() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    from pathlib import Path

    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)
