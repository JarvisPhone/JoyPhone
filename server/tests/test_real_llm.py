import pytest

from app.decision.llm import FakeLLM, RealLLM, build_llm


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
    client = _FakeClient("tap 5")
    llm = RealLLM(client=client, model="gpt-4o-mini")

    out = llm.complete(system="sys", user="usr")

    assert out == "tap 5"
    assert client.captured["model"] == "gpt-4o-mini"
    msgs = client.captured["messages"]
    assert msgs[0] == {"role": "system", "content": "sys"}
    assert msgs[1] == {"role": "user", "content": "usr"}


def test_real_llm_disables_thinking_and_uses_recommended_temperature():
    # MiniMax-M3 支持 thinking 关闭；文档推荐 temperature=1.0。
    client = _FakeClient("read")
    llm = RealLLM(client=client, model="MiniMax-M3")

    llm.complete(system="sys", user="usr")

    assert client.captured["temperature"] == 1.0
    assert client.captured["extra_body"] == {"thinking": {"type": "disabled"}}


def test_real_llm_strips_think_tags():
    # MiniMax-M2.x 系列 thinking 无法关��，content 会带 <think>...</think>，
    # 需剥离后才能被 decision 层 parse_actions 解析。
    raw = "<think>\n用户要点第 5 行\n</think>\ntap 5"
    client = _FakeClient(raw)
    llm = RealLLM(client=client, model="MiniMax-M2.5-highspeed")

    out = llm.complete(system="sys", user="usr")

    assert out == "tap 5"


def test_real_llm_returns_multiline_instructions_verbatim():
    # 文本指令协议：多行盲操作 + 收尾 tap 必须原样返回，不做 JSON 截断。
    raw = "home_first\nnext_page\ntap 2"
    client = _FakeClient(raw)
    llm = RealLLM(client=client, model="MiniMax-M3")

    out = llm.complete(system="sys", user="usr")

    assert out == "home_first\nnext_page\ntap 2"


def test_build_llm_falls_back_to_fake_when_no_key(monkeypatch):
    # 隔离磁盘 .env：本测试验证「进程环境无 key 时回退 FakeLLM」的纯逻辑，
    # 不应受本地 server/.env 影响。
    monkeypatch.setattr("app.decision.llm._load_env_file", lambda: None)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    llm = build_llm()
    assert isinstance(llm, FakeLLM)

def test_real_llm_logs_req_resp_to_llm_log(tmp_path, monkeypatch):
    # llm.log 观测链路:RealLLM 每次调用须落 LLM-REQ/LLM-RESP 原始流量。
    from app.gateway import connection
    connection._reset_for_test(tmp_path)

    client = _FakeClient("tap 5")
    llm = RealLLM(client=client, model="MiniMax-M3")
    llm.complete(system="sys", user="usr-payload")

    content = (tmp_path / "llm.log").read_text(encoding="utf-8")
    assert "LLM-REQ" in content and "usr-payload" in content
    assert "LLM-RESP" in content and "tap 5" in content
    connection._reset_for_test(tmp_path)
