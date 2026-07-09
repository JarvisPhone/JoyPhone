import pytest

from app.llm import FakeLLM, RealLLM, build_llm


class _FakeChoice:
    def __init__(self, content):
        self.message = type("M", (), {"content": content})()


class _FakeResp:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeClient:
    def __init__(self, content):
        self._content = content
        self.captured = {}

        parent = self

        class _Completions:
            def create(self, **kwargs):
                parent.captured = kwargs
                return _FakeResp(parent._content)

        self.chat = type("C", (), {"completions": _Completions()})()


def test_real_llm_sends_prompt_and_returns_content():
    client = _FakeClient('{"op":"tap","params":{"match_text":"搜索"}}')
    llm = RealLLM(client=client, model="gpt-4o-mini")

    out = llm.complete(system="sys", user="usr")

    assert out == '{"op":"tap","params":{"match_text":"搜索"}}'
    assert client.captured["model"] == "gpt-4o-mini"
    msgs = client.captured["messages"]
    assert msgs[0] == {"role": "system", "content": "sys"}
    assert msgs[1] == {"role": "user", "content": "usr"}


def test_build_llm_falls_back_to_fake_when_no_key(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    llm = build_llm()
    assert isinstance(llm, FakeLLM)