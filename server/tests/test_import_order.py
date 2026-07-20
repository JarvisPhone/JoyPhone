"""防回归:app.main 作为首导入入口(uvicorn app.main:create_app)不得循环崩溃。"""
import subprocess
import sys


def test_main_as_first_import():
    result = subprocess.run(
        [sys.executable, "-c", "from app.main import create_app"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
