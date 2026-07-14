import logging
import os
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path


def _log_dir() -> Path:
    d = Path(os.getenv("PHONEAGENT_LOG_DIR",
                        Path(__file__).resolve().parents[1] / "logs"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _make_logger(name: str, filename: str) -> logging.Logger:
    lg = logging.getLogger(name)
    lg.setLevel(logging.INFO)
    lg.propagate = False
    if not lg.handlers:
        h = RotatingFileHandler(
            _log_dir() / filename, maxBytes=10 * 1024 * 1024,
            backupCount=5, encoding="utf-8",
        )
        h.setFormatter(logging.Formatter("%(message)s"))
        lg.addHandler(h)
    return lg


_comm_logger = _make_logger("phoneagent.comm", "comm.log")
_llm_logger = _make_logger("phoneagent.llmraw", "llm.log")


def _ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def log_up(msg_type: str, content: str) -> None:
    _comm_logger.info("%s|UP|%s|%s", _ts(), msg_type, content)


def log_down(msg_type: str, content: str) -> None:
    _comm_logger.info("%s|DOWN|%s|%s", _ts(), msg_type, content)


def log_llm_req(content: str) -> None:
    _llm_logger.info("%s|LLM-REQ|%s", _ts(), content)


def log_llm_resp(content: str) -> None:
    _llm_logger.info("%s|LLM-RESP|%s", _ts(), content)


def _reset_for_test(dir_path) -> None:
    """测试用：重建 handler 指向指定目录。"""
    global _comm_logger, _llm_logger
    os.environ["PHONEAGENT_LOG_DIR"] = str(dir_path)
    for name in ("phoneagent.comm", "phoneagent.llmraw"):
        lg = logging.getLogger(name)
        for h in list(lg.handlers):
            lg.removeHandler(h)
            h.close()
    _comm_logger = _make_logger("phoneagent.comm", "comm.log")
    _llm_logger = _make_logger("phoneagent.llmraw", "llm.log")