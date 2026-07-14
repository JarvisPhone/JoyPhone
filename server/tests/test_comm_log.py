from app.comm_log import log_up, log_down, log_llm_req, log_llm_resp, _comm_logger, _llm_logger


def test_log_up_writes_line(tmp_path, monkeypatch):
    monkeypatch.setenv("PHONEAGENT_LOG_DIR", str(tmp_path))
    from app import comm_log
    comm_log._reset_for_test(tmp_path)
    log_up("perception", '{"a":1}')
    content = (tmp_path / "comm.log").read_text(encoding="utf-8")
    assert "UP" in content and "perception" in content and '{"a":1}' in content


def test_log_down_and_llm(tmp_path):
    from app import comm_log
    comm_log._reset_for_test(tmp_path)
    log_down("action", "tap 3")
    log_llm_req("system+user")
    log_llm_resp("tap 3")
    comm = (tmp_path / "comm.log").read_text(encoding="utf-8")
    llm = (tmp_path / "llm.log").read_text(encoding="utf-8")
    assert "DOWN" in comm and "tap 3" in comm
    assert "LLM-REQ" in llm and "LLM-RESP" in llm