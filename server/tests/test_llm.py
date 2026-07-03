import pytest

from app.llm import FakeLLM, LLM


def test_fake_llm_returns_scripted_response():
    llm = FakeLLM(["first", "second"])
    assert llm.complete(system="s", user="u") == "first"


def test_fake_llm_returns_last_when_exhausted():
    llm = FakeLLM(["a", "b"])
    assert llm.complete(system="s", user="u") == "a"
    assert llm.complete(system="s", user="u") == "b"
    assert llm.complete(system="s", user="u") == "b"


def test_llm_is_abstract():
    with pytest.raises(TypeError):
        LLM()