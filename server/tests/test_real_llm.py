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


def test_real_llm_strips_think_tags():
    # MiniMax-M2.x 系列 thinking 无法关闭，content 会带 <think>...</think>，
    # 需剥离后才能被 decision 层 json.loads 解析。
    raw = '<think>\n用户要点搜索按钮\n</think>\n{"op":"tap","params":{"match_text":"搜索"}}'
    client = _FakeClient(raw)
    llm = RealLLM(client=client, model="MiniMax-M2.5-highspeed")

    out = llm.complete(system="sys", user="usr")

    assert out == '{"op":"tap","params":{"match_text":"搜索"}}'


def test_real_llm_extracts_json_from_prose():
    # 兜底：即使模型在 JSON 前后夹杂说明文字，也应提取出首个完整 JSON 对象。
    raw = 'Sure, here is the action:\n{"op":"back","params":{}}\nHope it helps.'
    client = _FakeClient(raw)
    llm = RealLLM(client=client, model="MiniMax-M3")

    out = llm.complete(system="sys", user="usr")

    assert out == '{"op":"back","params":{}}'


def test_build_llm_falls_back_to_fake_when_no_key(monkeypatch):
    # 隔离磁盘 .env：本测试验证「进程环境无 key 时回退 FakeLLM」的纯逻辑，
    # 不应受本地 server/.env 影响。
    monkeypatch.setattr("app.llm._load_env_file", lambda: None)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    llm = build_llm()
    assert isinstance(llm, FakeLLM)