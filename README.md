<div align="center">

# JoyPhone

### Say it, the phone does it.

An open-source, cloud–device co-piloted AI phone agent · cloud as the brain, the phone as the hands & eyes

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-3776AB.svg)](https://www.python.org/)
[![Kotlin](https://img.shields.io/badge/kotlin-2.x-7F52FF.svg)](https://kotlinlang.org/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](#-contributing)

**English** | [中文](README.zh-CN.md)

</div>

---

JoyPhone is an **open-source, cloud–device co-piloted AI phone agent**: a cloud-hosted large model acts as the "brain" for decision-making, while a real Android device — using the `AccessibilityService` permission — acts as the "hands and eyes" to drive any app. No vendor SDK, no root, no vendor cooperation required. It looks at the screen, taps buttons, fills inputs, and scrolls just like a human would. You say one sentence; it does the rest.

It is inspired by products like Doubao Phone that promise "control the whole phone with one voice command", but takes a **fully open, cloud–device co-piloted, model-replaceable** route: it is not tied to any vendor's LLM, not locked to any phone brand, and turns "let AI use a phone like a human" into an **open project anyone can join, reproduce, and iterate on**.

> Long-term vision: a user says one sentence to the phone — "send Mom a WeChat message that I'm coming home for dinner tonight", "open Douyin and search for recent cat videos", "forward the last meeting notes to the work group" — and the phone listens, opens the apps, types, and confirms by itself. No more drilling through menus layer by layer, no more cross-app data moving, no more trapping people on small screens doing repetitive labor.

## Highlights

1. **Zero-SDK dependency**: drives any real-app UI via the Android AccessibilityService, sidestepping vendor bans and rate limits. One approach covers Feishu / WeCom / WeChat / SMS / Douyin and all social channels — anti-detection and brand-agnostic.
2. **Cloud–device "hands-eyes-brain" separation**: the phone only perceives (node tree + screenshot) and acts (tap / input / swipe); the cloud runs the multimodal large model for decisions — decisions can be hot-swapped, models replaced, and compute is unbounded, so iteration cost is far lower than on-device-integrated solutions.
3. **Skill library self-sedimentation moat**: every successful step sequence is automatically solidified into a reusable "skill"; on hit it replays as a script, on miss it falls back to the LLM. The more you use it, the faster and more accurate it gets; a community-built skill library forms a long-term flywheel.
4. **Voice one-shot driven** (roadmap): evolve from a pure-text goal to "voice command → cloud ASR → decision → negotiation", aiming to complete complex multi-step cross-app operations with one sentence, like Doubao Phone — but fully open and with a model of your choice.

## Architecture Overview

```
┌──────────────────────── Cloud (FastAPI + Python) ─────────────────────────┐
│  Task mgmt │ WS gateway + session FSM │ Decision engine │ Negotiation bot │
│  LLM abstraction │ Skill library │ Scene FSM │ Metrics │ Comm log          │
└────────────▲──────────────────────────────┬───────────────────────────────┘
             │ WebSocket (perception ↑ / action ↓)
             │  bidirectional real-time long-lived connection
┌────────────┴──────────────────────────────▼───────────────────────────────┐
│                    Android (Kotlin / AccessibilityService)                 │
│   Perception (node tree + screenshot) │ Execution (tap / input / swipe)     │
│   Event listening (new message upload) │ Connection mgmt (auto-reconnect)   │
└─────────────────────────────────────────────────────────────────────────────┘
                          ↑ drives real apps (Feishu / WeCom / WeChat / Douyin …)
```

The two ends communicate over a bidirectional real-time WebSocket channel:

- **Uplink** (App → Cloud): `perception` (node tree + screenshot), `action.result`, `event.newMessage`, `heartbeat`, `task.request`
- **Downlink** (Cloud → App): `task.start`, `action`, `task.done`, `task.abort`

Session FSM: `NAVIGATING → IN_CHAT → SENT → WAITING_REPLY → NEGOTIATING → DONE / ABORT`, enforced by `server/app/session.py` with legal-transitions + a step budget to prevent runaway.

## Roadmap

JoyPhone is a long-running open-source project that advances by milestone:

| Phase | Goal | Status |
|------|------|------|
| M1 Cloud–device minimal loop | Text goal → real-device accessibility control → decision + act + report | ✅ Working |
| M2 Skill self-sedimentation | Successful paths auto-solidify to "skills", replay-on-hit | ✅ MVP |
| M2.5 Screen-scene FSM | Cloud frame-by-frame driven generic return-home + dual stall/oscillation escape (LLM semantic escape → mechanical fallback three-tier ladder) | 🚧 In progress |
| M3 Multi-app onboarding | WeChat / WeCom / Douyin node adaptation and skill library | 🚧 In progress |
| M4 Voice one-shot driven | Cloud ASR → intent parsing → decision, ready out-of-the-mouth like Doubao Phone | 🔜 Planned |
| M5 Multi-device scheduling | One cloud manages many phones, ops backend and task queue | 🔜 Planned |
| M6 WS gateway high-perf | Rewrite gateway in Rust to shoulder more device concurrency | 🔬 Research |
| M7 Voice outbound / call center | Plug into a call center, AI actively dials out and multi-round voice negotiation | 🔬 Research |

## Repository Structure

```
JoyPhone/
├── server/                 # Cloud: FastAPI + Python ≥3.14
│   ├── app/
│   │   ├── gateway.py           # WebSocket gateway + single-task session main loop
│   │   ├── decision.py          # Decision engine (cache → skill → LLM three-tier fallback)
│   │   ├── protocol.py          # Uplink/downlink message protocol (Pydantic models)
│   │   ├── session.py           # Session FSM + step budget
│   │   ├── llm.py               # LLM abstraction (FakeLLM / RealLLM)
│   │   ├── skills.py            # Static skill library
│   │   ├── skill_cache.py       # Runtime self-learning skill cache
│   │   ├── scene.py             # Screen-scene FSM (cloud-side return-home + stuck/oscillation escape)
│   │   ├── app_goal_resolver.py # Parse NL goal → target Android package (app-boundary hard constraint)
│   │   ├── chat_title_helpers.py# Chat-title detection / message-input locate / send-button matching
│   │   ├── negotiation.py       # Negotiation bot
│   │   ├── comm_log.py          # Rotating up/down-link + raw-LLM logger
│   │   └── metrics.py           # Per-task metrics collector (steps, LLM calls, skill/cache hits, duration)
│   ├── tests/                   # pytest unit/integration tests + replay fixtures
│   ├── scripts/e2e_feishu.sh   # Real-device end-to-end debug script
│   ├── pyproject.toml
│   └── .env.example             # LLM config template (OpenAI-compatible)
│
├── android/                # Android: Kotlin + Compose + Hilt
│   └── app/src/main/java/com/example/phoneagent/
│       ├── accessibility/      # PhoneAgentService / Executor / Perception / NodeFlattener / GestureGeometry …
│       ├── net/                 # WsClient / WsDispatcher (long connect + auto-reconnect)
│       ├── protocol/            # Messages.kt — serialization models aligned with cloud
│       ├── domain/              # AgentModels / SampleRequest / TaskState / TraceEvent / ActionLog
│       ├── data/                # AgentStateRepository (debug-panel state)
│       ├── ui/                  # AgentScreen / DebugPanel / MainViewModel (Jetpack Compose)
│       ├── di/                  # AppModule — Hilt DI graph
│       ├── AccessibilityStatus.kt
│       ├── AgentApplication.kt  # Hilt-enabled Application
│       └── MainActivity.kt
│
└── docs/
    ├── superpowers/            # Design and implementation plans (specs / plans, archived by date)
    ├── competition/            # Competitive analysis notes
    └── CODE_REVIEW_REPORT.md
```

## Cloud Design Highlights

### Decision engine three-tier fallback (`server/app/decision.py`)

For every perception frame, the next action is produced by priority:

1. **Skill cache hit**: look up `SkillCache` by `(goal, pkg)`; on hit, replay the sediment-ed step sequence. If a step can't be re-located on the current node tree, fall back to the next tier.
2. **Static skill library**: look up `SkillLibrary` by `skill_name`; locate the node by `match_text` on the current node tree and replay.
3. **LLM reasoning**: feed the goal + structured screen state (`[idx] type "text"`, interactive nodes first, up to `MAX_LLM_NODES=80`) + action history to the LLM, asking it to output exactly one JSON action object.

A `tap` decided by the LLM is resolved on the cloud side to the exact coordinate center using the node `id` / `match_text` before being sent down — avoiding on-device full-screen substring match false hits (e.g. minus-one-screen tiles). The system prompt bakes in common-sense constraints like "minus-one-screen detection" and "swipe on home to find the app".

### Screen-scene FSM (`server/app/scene.py`)

Frame by frame on the cloud side, the current perception is classified into a finite scene: `HOME` (any desktop page) / `MINUS_ONE` (the -1 screen) / `RECENT_APPS` / `LOCK_SCREEN` / `NOTIFICATION` / `CONTROL_CENTER` / `IN_APP` / `UNKNOWN`. Resource-id matching is suffix-based (`endswith` / `contains`) so it is cross-device without hardcoding any vendor package prefix. The FSM replaces `decision.py`'s pkg-only guard and roots out the endless loop circling between launcher states. It also provides a convergence guard that combines stall (`STALL_THRESHOLD=3` consecutive same-scene same-op) and oscillation (non-target scene repeating `CYCLE_THRESHOLD=2` times inside a `WINDOW=6` window), escalating to an LLM semantic-escape (`LLM_ESCALATION_TRIES=1`) then a mechanical-fallback three-tier ladder (`FALLBACK_TRIES=2`).

### Goal → application boundary (`server/app/app_goal_resolver.py`)

Parses a natural-language goal into a target Android `package` with pure keyword matching — fast, zero-cost, unit-testable. The resolved `pkg` becomes an app-boundary hard constraint: once the perceived `pkg != target pkg`, the cloud first returns to home, then `home` + finds the icon to re-open the target app — it will never tap a notification / tile to jump to another app. Aliases are built in for Feishu / WeChat / QQ / DingTalk / Taobao / JD / Meituan / Xiaohongshu / Douyin / Zhihu / Amap / Baidu Map / Tencent Map / Dialer / Contacts, etc.

### LLM abstraction (`server/app/llm.py`)

- `FakeLLM`: replays a preset response sequence — for offline / CI tests.
- `RealLLM`: OpenAI-compatible SDK based; defaults to MiniMax-M2.x (with `extra_body={"thinking":{"type":"disabled"}}` to disable reasoning); auto-strips `` reasoning segments and extracts the first balanced JSON so downstream `json.loads` is always usable. **Any OpenAI-compatible model (Doubao / DeepSeek / Qwen / self-hosted vLLM, etc.) plugs in with one config line.**
- Without `LLM_API_KEY` it gracefully degrades to `FakeLLM` — runs out of the box, no external network service required.

### Skill self-sedimentation (`server/app/skill_cache.py`)

When a task ends normally (`done`), the current `applied_steps` are written back to cache keyed by `(goal, pkg)`. The next time the same goal + app appears it replays directly as a script with zero LLM-quota use. If a step can't be re-located the whole entry is invalidated and waits for re-learning — an MVP policy that is simple and reliable, and the primitive underlying the community skill-library flywheel.

### Observability (`server/app/comm_log.py` / `metrics.py`)

- `comm_log`: a rotating file logger for the bidirectional comm log (`comm.log`) and raw LLM traffic (`llm.log`), capped at 10 MB × 5 files. The log dir is overridable via the `PHONEAGENT_LOG_DIR` env var.
- `metrics`: a per-task metrics collector (`TaskMetrics`) tracking `steps`, `llm_calls`, `skill_hits`, `cache_hits`, `status`, `error`, and duration, so any task run can be replayed/compared offline.

### Chat-title helpers (`server/app/chat_title_helpers.py`)

Pure heuristics for chat-page anchoring — whether the current page is the target chat title, whether a node is a message-input box, and whether a node is a send button — keeps the cloud side anchored to a specific conversation inside IM apps with very few tokens.

## Android Design Highlights

### `PhoneAgentService` (`accessibility/PhoneAgentService.kt`)

Extends `AccessibilityService`; the accessibility-service core:

- On `onServiceConnected` it starts the WebSocket, registers callbacks, and reports an `ANDROID_ID`-based device id.
- After receiving `task.start` it reports the first perception frame; subsequent window changes are debounced by `DEBOUNCE_MS=400` before reporting to avoid jitter.
- `onAccessibilityEvent` only reacts when `taskActive`; `action` supports a read-only debug mode (triggered by a `[DEBUG-ONESHOT]` goal prefix): report one frame, do not execute the returned action — convenient for manually navigating to a target page and then single-frame-verifying the cloud decision.
- The default connect address lives in the `PhoneAgentService.WS_URL` constant — modify for your environment.

### `Executor` (`accessibility/Executor.kt`)

Translates cloud action commands into Accessibility API calls:

- `tap`: prefer `dispatchGesture` click using the cloud-sent `x/y` coordinates; when missing, fall back to a center click on the node matched by `match_text` substring.
- `input`: find the first editable node and perform `ACTION_SET_TEXT`.
- `swipe` / `back` / `home`: standard gestures and global actions.
- Desktop paging/scrolling and return-home are driven by the **cloud scene FSM** frame by frame (`server/app/scene.py`): `detect_scene` identifies the current scene → `next_action` looks up the transition table and sends a single atomic action → the cloud guard detects stall and oscillation and applies three-tier escape. The phone side acts as a dumb executor. Coordinate geometry is still extracted into a unit-testable `GestureGeometry`.

### Perception & node pruning (`accessibility/NodeFlattener.kt` / `Perception.kt`)

Reads the `rootInActiveWindow` node tree, keeps only visible nodes that carry text or are interactive, and serializes them into `Node` lists aligned with the cloud protocol, drastically cutting link load and LLM token cost.

### Tech stack

Jetpack Compose (single Activity + Compose UI) + Hilt (`@AndroidEntryPoint` injects `WsClient` / `AgentStateRepository`) + OkHttp WebSocket + kotlinx.serialization. `minSdk=26 / targetSdk=36 / JVM 17`.

## Quick Start

### Cloud

```bash
cd server
cp .env.example .env            # fill in LLM_API_KEY (any OpenAI-compatible endpoint)
# Python ≥3.14 recommended, using uv: uv sync
uv run uvicorn app.gateway:create_app --factory --host 0.0.0.0 --port 8000
```

Without `LLM_API_KEY` it auto-uses `FakeLLM`, so the protocol chain can be exercised offline.

### Android

1. Connect a real device via USB (`minSdk≥26`), confirm it shows up in `adb devices`.
2. Configure the SDK path in `android/local.properties` (gitignored).
3. Open the `android/` project in Android Studio and Run `app`.
4. System settings → Accessibility → enable the "PhoneAgent" service.
5. Modify `PhoneAgentService.WS_URL` to point at your cloud address.

### Real-device end-to-end debug

```bash
server/scripts/e2e_feishu.sh
# re-bind the accessibility service to trigger WS connect → return to home → open Feishu →
# watch the perception / decided op output in the uvicorn log
```

The "Task goal" input box at the top of the App ships a natural-language goal (e.g. "send Zhang San a message on Feishu: meeting tomorrow morning"); it goes up via `task.request` and the cloud kicks off the decision loop.

## Testing

```bash
cd server
uv run pytest                          # full suite
uv run pytest tests/test_decision.py  # decision engine unit tests
PHONEAGENT_FAKE_LLM='[...]' uv run pytest tests/test_gateway_loop.py  # inject FakeLLM and run the gateway main loop
```

Android unit tests live in `android/app/src/test/`, covering the pure-logic parts of `GestureGeometry`, `NodeFlattener`, `Messages` (protocol models), `WsDispatcher`, `AgentStateRepository`, `MainViewModel`, and `AccessibilityStatus`.

## Key Testability Design

A perception sequence captured on a real device is stored as a "replay fixture" (e.g. `server/tests/fixtures/feishu_happy_path.json`); the cloud can replay a complete decision loop offline from it — **no real device required, the AI decision logic can be re-verified in CI over and over**. This is the project's quality base and TDD landing point — the "device side is uncontrollable, cloud side is reproducible" engineering discipline.

## 🤝 Contributing

JoyPhone is a **fully open-source** project. Any contribution — a line of code, a skill, a new app's node adaptation, a bug report, a doc polish — moves the project one step closer to "say it, the phone does it".

### What you can contribute

- **Cloud side**: decision engine, negotiation bot, skill library for new apps, LLM adapters, WS gateway performance, tests and replay fixtures.
- **Android side**: node-pruning algorithms, accessibility adaptation for new apps, gesture execution, auto-reconnect, UI debug panel.
- **Skill library**: sediment a successful "goal → success step sequence" of yours into a reusable skill for everyone — the core of the community flywheel.
- **Docs**: README polish, architecture diagrams, usage tutorials, new-app onboarding guides.
- **Tests**: add unit/integration tests and edge-case replay fixtures.

### How to submit a PR

1. **Fork** this repo to your GitHub account.
2. Branch off `main`:

   ```bash
   git checkout -b feat/your-feature
   ```

3. Make changes; keep each commit focused on one thing and follow the [Conventional Commits](https://www.conventionalcommits.org/) style, e.g.:

   ```text
   feat(decision): support WeChat chat-page node pruning
   fix(android): fix auto-reconnect intermittent NPE
   test(server): add Feishu happy-path replay fixture
   docs: add a new-app onboarding guide
   ```

4. Before submitting, ensure local checks pass:

   ```bash
   # Cloud
   cd server && uv run pytest
   # Android
   cd android && ./gradlew test
   ```

5. Push to your fork and open a **Pull Request** against `main`:

   - Use Conventional Commits for the **title** (e.g. `feat(android): support WeChat send-message skill`).
   - The **description** should explain: what problem / why / how tested. If the change touches decision logic, attaching a replay fixture or log is even better.
   - If the PR corresponds to an issue, link it (`Closes #123`).

6. Wait for review. Small changes usually land the same day; changes touching the decision main loop or the protocol will go through several rounds of discussion.

### PR conventions

- **One PR, one thing**: split a PR mixing unrelated changes into several.
- **Stay testable**: pair new logic with unit tests; for real-device changes attach logs or a replay fixture.
- **Don't break the protocol format**: when extending the up/down message protocol, open an issue to discuss a backward-compatible plan first.
- **No sneaky heavy dependencies**: the cloud follows `pyproject.toml`, Android follows `libs.versions.toml`; do not bloat dependencies on your own.
- **Security**: never commit secrets, `.env`, or `local.properties`; never introduce code that could leak device information.

Feel free to open an [Issue](../../issues) for discussion first — far more efficient than charging ahead silently. In the early stage we keep the direction open; "talk first, then act" beats "do a lot, then talk".

## Design & Plan Documents

Historical design and implementation plans are archived by date in `docs/superpowers/` (`specs/` design drafts / `plans/` implementation plans), so the evolution is traceable. Competitive analysis notes live in `docs/competition/`, and `docs/CODE_REVIEW_REPORT.md` records the latest code-review pass.

## License

This project is open-sourced under the **MIT License**. Community contributions are MIT-licensed by default; you are free to use, modify, and redistribute it.