"""Detached uvicorn launcher for macOS.

macOS bash & + nohup 在某些 shell session 下(Sandbox/Cursor terminal)会回收后台子进程。
本脚本用 Python os.setsid + double-fork 完全脱离 controlling terminal + parent process,
等同 systemd unit / launchd plist 的 detach 效果,但临时使用够用。

HOST / PORT 由环境变量 SERVER_HOST / SERVER_PORT 提供(参考 server/.env.example)。
启动时自动 load server/.env 到 process env(env 已被 .gitignore);不修改 .env 也可,
直接 SERVER_HOST / SERVER_PORT 环境变量 / inline 覆盖都有用。
"""
import os
import sys
from pathlib import Path

# 1) 加载 server/.env → process env(已 gitignore)
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(env_path)
except ImportError:
    print("warn: python-dotenv 未安装;跳过 .env 加载(可 uv add python-dotenv)", file=sys.stderr)
except Exception as e:
    print(f"warn: load_dotenv 失败: {e}", file=sys.stderr)

HOST = os.environ.get("SERVER_HOST", "0.0.0.0")
PORT = os.environ.get("SERVER_PORT", "8000")

# PROJECT_ROOT = 本仓库 server/ 目录(本脚本的父目录)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# === 启动时清空日志 ===
# 设计目标:每次 `run_uvicorn_detached.py` 起新进程前,清掉三个实时日志,
# 旧轮 trace 保留在 logs/.archive/<timestamp>/,避免 `tail -f` 读到上轮污染。
# 这样真机测试可以无脑 "起服务端 → 跑场景 → 看完",不必手动 : > truncate。
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LIVE_LOGS = ("uvicorn.log", "comm.log", "llm.log")

def _archive_and_clear_live_logs():
    """把当前 LIVE_LOGS 归档到 .archive/<start_ts>/,再 truncate。"""
    import datetime as _dt
    ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    archive = LOG_DIR / ".archive" / ts
    archive.mkdir(parents=True, exist_ok=True)
    for name in LIVE_LOGS:
        src = LOG_DIR / name
        if src.exists() and src.stat().st_size > 0:
            # 移到 archive,改名加时间戳便于排查
            dest = archive / f"{name}.{ts}"
            try:
                src.rename(dest)
            except OSError:
                # rename 跨 device / 文件被占用时退化为 copy+truncate
                import shutil
                shutil.copy2(src, dest)
                with src.open("w") as f:
                    pass
    # 也清掉 metrics 流式日志(metrics/<task>.json 归档保留)
    metrics_dir = PROJECT_ROOT / "data" / "metrics"
    if metrics_dir.exists():
        for f in metrics_dir.glob("metrics.log*"):
            try:
                f.rename(archive / f.name)
            except OSError:
                f.write_text("")

cmd = [
    "uv", "run", "uvicorn", "app.main:create_app",
    "--host", HOST, "--port", PORT, "--factory",
]
log = str(LOG_DIR / "uvicorn.log")

_archive_and_clear_live_logs()

# First fork: parent exits, child becomes orphan adopted by init (pid 1)
pid = os.fork()
if pid > 0:
    # Parent: return immediately
    print(f"spawned pid={pid} host={HOST} port={PORT}")
    sys.exit(0)

# Child: detach session
os.setsid()

# Second fork: ensure we can never reacquire controlling terminal
pid = os.fork()
if pid > 0:
    os._exit(0)

# Grandchild: redirect stdio to log + /dev/null, change cwd
sys.stdin = open("/dev/null")
log_fh = open(log, "ab")
os.dup2(log_fh.fileno(), sys.stdout.fileno())
os.dup2(log_fh.fileno(), sys.stderr.fileno())
log_fh.close()

os.chdir(str(PROJECT_ROOT))

# Replace process image with uvicorn
os.execvp(cmd[0], cmd)
