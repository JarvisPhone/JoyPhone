#!/usr/bin/env bash
# 真机端到端联调脚本：重连无障碍服务 → 打开飞书 → 让 Agent 接管。
# 云端 uvicorn 需已在 0.0.0.0:8000 运行；观察 uvicorn 终端日志核对全链路。
set -euo pipefail

A11Y="com.example.phoneagent/com.example.phoneagent.accessibility.PhoneAgentService"
FEISHU_PKG="com.ss.android.lark"

echo "[1/4] 检查设备..."
adb devices

echo "[2/4] 重新绑定无障碍服务（触发 WS 连接）..."
adb shell settings put secure accessibility_enabled 0 || true
adb shell settings delete secure enabled_accessibility_services || true
sleep 2
adb shell settings put secure enabled_accessibility_services "$A11Y"
adb shell settings put secure accessibility_enabled 1
sleep 3
echo -n "  Bound services: "
adb shell dumpsys accessibility | grep -i "Bound services" | head -1

echo "[3/4] 回到桌面，稳定 2s..."
adb shell input keyevent KEYCODE_HOME
sleep 2

echo "[4/4] 打开飞书，Agent 应开始决策（观察 uvicorn 日志）..."
adb shell monkey -p "$FEISHU_PKG" -c android.intent.category.LAUNCHER 1 >/dev/null 2>&1
echo "完成。请观察云端 uvicorn 日志的 perception / decided op 输出。"