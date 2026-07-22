"""Detached uvicorn launcher for macOS.

macOS bash & + nohup 在某些 shell session 下(Sandbox/Cursor terminal)会回收后台子进程。
本脚本用 Python os.setsid + double-fork 完全脱离 controlling terminal + parent process,
等同 systemd unit / launchd plist 的 detach 效果,但临时使用够用。
"""
import os
import sys

cmd = [
    "uv", "run", "uvicorn", "app.main:create_app",
    "--host", "0.0.0.0", "--port", "8000", "--factory",
]
log = "/Users/conv/myspace/JoyPhone/server/logs/uvicorn.log"

# First fork: parent exits, child becomes orphan adopted by init (pid 1)
pid = os.fork()
if pid > 0:
    # Parent: return immediately
    print(f"spawned pid={pid}")
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

os.chdir("/Users/conv/myspace/JoyPhone/server")

# Replace process image with uvicorn
os.execvp(cmd[0], cmd)