import pytest

from app.decision.llm import FakeLLM, LLM, _clean_text


def test_fake_llm_allows_empty_responses_on_init():
    llm = FakeLLM([])
    assert isinstance(llm, FakeLLM)


def test_fake_llm_returns_scripted_response():
    llm = FakeLLM(["first", "second"])
    assert llm.complete(system="s", user="u") == "first"


def test_fake_llm_returns_last_when_exhausted():
    llm = FakeLLM(["a", "b"])
    assert llm.complete(system="s", user="u") == "a"
    assert llm.complete(system="s", user="u") == "b"
    assert llm.complete(system="s", user="u") == "b"


def test_fake_llm_single_class_exhaustion_semantics():
    import app.decision.llm as m
    assert len([n for n in dir(m) if n == "FakeLLM"]) == 1
    llm = m.FakeLLM(["a", "b"])
    assert [llm.complete("", ""), llm.complete("", ""), llm.complete("", "")] == ["a", "b", "b"]


def test_llm_is_abstract():
    with pytest.raises(TypeError):
        LLM()


# ---- _clean_text: 文本指令协议下只剥 <think>，不做 JSON 提取 ----


def test_clean_text_strips_think_tags():
    raw = "<think>\n用户要点第 5 行\n</think>\ntap 5"
    assert _clean_text(raw) == "tap 5"


def test_clean_text_preserves_plain_multiline_instructions():
    # 纯文本多行指令必须原样保留(不能被截成首个 JSON 对象)。
    raw = "home_first\nnext_page\ntap 2"
    assert _clean_text(raw) == "home_first\nnext_page\ntap 2"


def test_clean_text_does_not_extract_json():
    # 文本协议下即使内容里含大括号也不做 JSON 提取，原样(去 think)返回。
    raw = "input 3 {你好}"
    assert _clean_text(raw) == "input 3 {你好}"


def test_clean_text_none_returns_empty():
    assert _clean_text(None) == ""


def test_clean_text_empty_returns_empty():
    assert _clean_text("") == ""
    assert _clean_text("   \n  ") == ""