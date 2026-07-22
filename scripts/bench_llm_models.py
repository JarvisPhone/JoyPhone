#!/usr/bin/env uv run python3
"""MiniMax 模型速度基准测试.

测试三个模型的速度,每次发一个真实的 decision prompt (来自最近的 llm.log),
跑 N 轮取平均值。

Usage:
    cd server && uv run python ../scripts/bench_llm_models.py

Models tested:
    - MiniMax-M2.5          (50 TPS, 不带 highspeed)
    - MiniMax-M2.5-highspeed (100 TPS, 当前在用)
    - MiniMax-M3            (100 TPS, 支持关闭 thinking)
"""
import json
import os
import statistics
import sys
import time
from pathlib import Path

try:
    from openai import OpenAI
except ImportError:
    print("ERROR: openai not installed. Run: uv add openai")
    sys.exit(1)


# 读 .env
def _load_env():
    # 尝试 server/.env（部署标准路径）和项目根 .env
    candidates = [
        Path(__file__).resolve().parent / ".env",                # scripts/.env
        Path(__file__).resolve().parents[1] / ".env",            # project_root/.env
        Path(__file__).resolve().parents[1] / "server" / ".env",  # server/.env
    ]
    for env_path in candidates:
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
            break  # 只加载第一个找到的

_load_env()

API_KEY = os.environ.get("LLM_API_KEY")
BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.minimaxi.com/v1")

if not API_KEY:
    print("ERROR: LLM_API_KEY not set")
    sys.exit(1)


# 真实 prompt (来自最近一次飞书输入场景的 llm.log)
SYSTEM_PROMPT = """你是 JoyPhone 手机助手的决策模型。

【任务】
用户目标是：打开飞书，给群「Android AI 开发组」发一条消息

【当前屏幕】
当前应用：com.ss.android.lark（飞书）
当前屏幕节点（已编码）：
[0] text "Ra"
[1] button "Ra"
[2] button "chat msg group"
[3] button "content"
[4] button "message"
[5] button "Android AI 开发组"
[6] button ""
[7] button "发送给 Android AI 开发组"
[8] input "发送给 Android AI 开发组"
[9] button "status transform btn"
[10] button "btn send"

【决策规则】
- 输出一个动作(op)及参数,格式：op 参数
- 可用 op: tap <节点序号或文本> | input <节点序号或文本> <内容> | back | home | swipe up|down|left|right | read_screen | done
- tap 用 match_text="文本" 而非节点序号（如果能匹配到的话）
- 不要输出任何解释，只输出动作指令
- 当前已在群聊页，输入框已聚焦，输入内容后要点「btn send」按钮发送"""

USER_PROMPT = "请决定下一步动作"


MODELS = {
    "MiniMax-M2.5": {
        "model": "MiniMax-M2.5",
        "thinking": {"type": "disabled"},  # M2.5 忽略此参数，但填上保持接口一致
    },
    "MiniMax-M2.5-highspeed": {
        "model": "MiniMax-M2.5-highspeed",
        "thinking": {"type": "disabled"},
    },
    "MiniMax-M3 (thinking=disabled)": {
        "model": "MiniMax-M3",
        "thinking": {"type": "disabled"},  # M3 支持关闭 thinking
    },
    "MiniMax-M3 (thinking=adaptive)": {
        "model": "MiniMax-M3",
        "thinking": {"type": "adaptive"},
    },
}


def run_single(client, model_name: str, cfg: dict) -> dict:
    """发一次请求，返回 {latency_s, output_tokens, output_text, thinking_tokens}。"""
    t0 = time.perf_counter()
    try:
        resp = client.chat.completions.create(
            model=cfg["model"],
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_PROMPT},
            ],
            temperature=1.0,
            extra_body={"thinking": cfg["thinking"]},
        )
        latency = time.perf_counter() - t0

        raw_content = resp.choices[0].message.content or ""

        # reasoning_content 只在 reasoning_split=true 时才独立字段，
        # 默认情况下 MiniMax 把 thinking 留在 <talk> 标签里（我们的 _clean_text 已处理）
        reasoning = getattr(resp.choices[0].message, "reasoning_content", "") or ""

        # 计算 token（用字符数近似，1 token ≈ 4 chars）
        output_chars = len(raw_content)
        output_tokens = output_chars // 4
        thinking_tokens = len(reasoning) // 4

        # 去掉 <talk> 标签
        import re
        cleaned = re.sub(r"<think>.*?</think>", "", raw_content, flags=re.DOTALL).strip()

        return {
            "ok": True,
            "latency_s": round(latency, 3),
            "output_tokens": output_tokens,
            "thinking_tokens": thinking_tokens,
            "output_text": cleaned[:80],
        }
    except Exception as e:
        latency = time.perf_counter() - t0
        return {
            "ok": False,
            "latency_s": round(latency, 3),
            "error": str(e),
        }


def run_model(client, model_name: str, cfg: dict, runs: int = 5) -> dict:
    print(f"\n  Testing {model_name} ({cfg['model']}) × {runs} runs...")
    latencies = []
    tokens = []
    thinking_tokens = []
    errors = []

    for i in range(runs):
        result = run_single(client, model_name, cfg)
        if result["ok"]:
            latencies.append(result["latency_s"])
            tokens.append(result["output_tokens"])
            thinking_tokens.append(result["thinking_tokens"])
            status = "OK"
        else:
            errors.append(result["error"])
            status = f"ERR: {result['error'][:60]}"
        print(f"    run {i+1}: {result.get('latency_s', '?')}s  |  {result.get('output_tokens', 0)}tok  |  {result.get('thinking_tokens', 0)}think-tok  |  {status}")

    if not latencies:
        return {"ok": False, "errors": errors}

    return {
        "ok": True,
        "model_name": model_name,
        "model_id": cfg["model"],
        "runs": runs,
        "latency_avg": round(statistics.mean(latencies), 3),
        "latency_min": round(min(latencies), 3),
        "latency_max": round(max(latencies), 3),
        "latency_stdev": round(statistics.stdev(latencies), 3) if len(latencies) > 1 else 0,
        "tokens_avg": round(statistics.mean(tokens), 1),
        "thinking_avg": round(statistics.mean(thinking_tokens), 1),
        "tps_avg": round(statistics.mean(tokens) / statistics.mean(latencies), 1),
    }


def main():
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 5

    print("=" * 70)
    print(f"MiniMax 模型速度基准测试  ({runs} runs / model)")
    print(f"API: {BASE_URL}")
    print(f"Prompt: {len(SYSTEM_PROMPT)} chars system + {len(USER_PROMPT)} chars user")
    print("=" * 70)

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    results = []

    for name, cfg in MODELS.items():
        r = run_model(client, name, cfg, runs=runs)
        results.append(r)
        if r["ok"]:
            print(f"  → avg={r['latency_avg']}s  min={r['latency_min']}s  "
                  f"max={r['latency_max']}s  std={r['latency_stdev']}s  "
                  f"tokens={r['tokens_avg']}  think={r['thinking_avg']}  "
                  f"TPS={r['tps_avg']}")
        else:
            print(f"  → ALL FAILED: {r.get('errors', ['unknown'])}")

    # 汇总表
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"{'Model':<35} {'avg(s)':>7} {'min':>6} {'max':>6} {'std':>6} {'tok':>6} {'think':>6} {'TPS':>6}")
    print("-" * 70)
    for r in results:
        if r["ok"]:
            print(
                f"{r['model_name']:<35} "
                f"{r['latency_avg']:>7.3f} "
                f"{r['latency_min']:>6.3f} "
                f"{r['latency_max']:>6.3f} "
                f"{r['latency_stdev']:>6.3f} "
                f"{r['tokens_avg']:>6.1f} "
                f"{r['thinking_avg']:>6.1f} "
                f"{r['tps_avg']:>6.1f}"
            )
        else:
            print(f"{name:<35}  FAILED")
    print("=" * 70)

    # 推荐
    ok_results = [r for r in results if r["ok"]]
    if ok_results:
        fastest = min(ok_results, key=lambda r: r["latency_avg"])
        print(f"\n推荐（端到端最快）: {fastest['model_name']}  ({fastest['latency_avg']}s avg)")


if __name__ == "__main__":
    main()
