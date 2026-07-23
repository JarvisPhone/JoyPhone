<div align="center">

# JoyPhone

### Say it, the phone does it.

An open-source AI phone assistant · Cloud as the brain, the phone as the hands & eyes

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.14-3776AB.svg)](https://www.python.org/)
[![Kotlin](https://img.shields.io/badge/kotlin-2.x-7F52FF.svg)](https://kotlinlang.org/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](#-contributing)

[**English** | [中文](README.zh-CN.md)]

</div>

---

## What is JoyPhone?

JoyPhone is an **AI assistant that controls your phone for you**. You tell it what to do in plain language, and it autonomously opens apps, types messages, taps buttons, and completes tasks on a real Android phone—just like a human would.

Imagine saying:
- "Send a WeChat message to Mom saying I'm coming home for dinner"
- "Open Douyin and search for cute cat videos"
- "Forward the last meeting notes to the work group"

JoyPhone listens, understands, and does it all. No more digging through menus, no more repetitive taps, no more struggling with tiny screens.

**JoyPhone is inspired by products like Doubao Phone that promise "control the whole phone with one voice command," but takes a fully open, customizable route**: it's not tied to any specific AI model, any phone brand, or any company. This is an open project anyone can use, learn from, and contribute to.

## Key Features

### 1. Works with Any App — No Developer APIs Needed

JoyPhone uses Android's built-in accessibility features to interact with apps directly, just like a human user would. This means it works with **WeChat, Feishu, DingTalk, Douyin, SMS**, and virtually any other app—without needing special permissions from app developers.

### 2. Cloud-Powered Intelligence

The heavy thinking happens in the cloud: JoyPhone uses a large language model (LLM) to understand your goals, analyze screen content, and decide what to do next. This means:
- **Fast responses** — no phone hardware limitations
- **Easy updates** — change AI models without reinstalling anything
- **Works on any Android phone** — the phone just follows instructions

### 3. Gets Smarter Over Time

Every successful task creates a "skill" that JoyPhone remembers. The next time you ask for something similar, it completes it instantly without hesitation. The more you use it, the faster and more reliable it becomes.

### 4. Your Privacy, Your Control

JoyPhone processes your screen content through cloud AI, but all decisions happen on YOUR configured server. No data goes to third parties you don't trust.

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                           Cloud (Your Server)                   │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │ Task Master │  │ AI Brain    │  │ Skills Library          │ │
│  │ (manages    │  │ (understands│  │ (learned from past      │ │
│  │  your tasks)│  │  goals &    │  │  successful tasks)       │ │
│  │             │  │  screens)   │  │                          │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
└────────────────────────────┬────────────────────────────────────┘
                             │ Internet (WebSocket)
┌────────────────────────────▼────────────────────────────────────┐
│                     Your Android Phone                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │ Eyes        │  │ Hands       │  │ Connection Manager      │ │
│  │ (reads      │  │ (taps,      │  │ (stays connected,       │ │
│  │  screens)   │  │  types)     │  │  auto-reconnects)       │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                             ↑
              JoyPhone controls apps like a human user
              (Feishu, WeChat, Douyin, SMS, etc.)
```

**The flow is simple:**
1. You give JoyPhone a goal (e.g., "send a message to Zhang San")
2. Your phone shows JoyPhone what's on screen
3. The cloud AI decides the next action
4. Your phone executes it (tap, type, scroll)
5. Repeat until the task is done

## What Can JoyPhone Do?

| Category | Examples |
|----------|----------|
| **Messaging** | Send WeChat/Feishu messages, reply to groups, forward content |
| **Search & Browse** | Open Douyin and search, browse Weibo, find content |
| **Information Entry** | Fill forms, complete registrations, input data |
| **Social Media** | Post updates, comment, share content |
| **Daily Tasks** | Set reminders, check notifications, navigate apps |

## Roadmap

We're building JoyPhone step by step:

| Phase | Goal | Status |
|-------|------|--------|
| Core Loop | Text goal → phone action → done | ✅ Working |
| Skill Learning | Remember successful paths, replay instantly | ✅ MVP |
| Smart Navigation | Handle app switching, stuck detection, auto-recovery | 🚧 In progress |
| More Apps | Support WeChat, Douyin, and more | 🚧 In progress |
| Voice Control | Talk to your phone instead of typing | 🔜 Planned |
| Multi-Phone Control | One server managing multiple phones | 🔜 Planned |

## Quick Start

### Prerequisites

- **A computer** (Windows, macOS, or Linux) to run the cloud server
- **An Android phone** (Android 8.0 / API 26 or higher)
- **USB cable** to connect phone to computer (for initial setup)
- **Python 3.14+** on your computer
- **An OpenAI-compatible AI model** (optional, but recommended for best results)

### Step 1: Set Up the Cloud Server

#### For macOS / Linux

```bash
# 1. Navigate to the server folder
cd server

# 2. Copy the environment template
cp .env.example .env

# 3. Open .env in a text editor and fill in your AI API key
# Look for LLM_API_KEY= and add your key
# Any OpenAI-compatible API works (OpenAI, DeepSeek, Doubao, etc.)

# 4. Install dependencies (using uv package manager)
uv sync

# 5. Start the server
uv run uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000
```

#### For Windows (PowerShell)

```powershell
# 1. Navigate to the server folder
cd server

# 2. Copy the environment template
Copy-Item .env.example .env

# 3. Open .env in Notepad and fill in your AI API key
# Look for LLM_API_KEY= and add your key

# 4. Install dependencies (using uv package manager)
uv sync

# 5. Start the server
uv run uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000
```

> **Note:** If you don't have `uv` installed, install it first:
> - macOS/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
> - Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

> **Without an API key?** The server will run in demo mode with simulated responses—perfect for testing the interface.

### Step 2: Find Your Computer's IP Address

The phone needs to know where to find your server.

#### For macOS

```bash
# Run this in Terminal
ifconfig | grep "inet " | grep -v 127.0.0.1
```

#### For Linux

```bash
# Run this in terminal
ip addr show | grep "inet "
```

#### For Windows

```powershell
# Run this in PowerShell
ipconfig | Select-String "IPv4"
```

Look for an address like `192.168.x.x` — this is your local IP.

### Step 3: Set Up the Android App

1. **Connect your Android phone to your computer via USB**

2. **Enable USB debugging on your phone:**
   - Go to Settings → About Phone
   - Tap "Build Number" 7 times to enable Developer Options
   - Go to Settings → Developer Options
   - Enable "USB Debugging"

3. **Configure the server address on your phone:**
   
   Open the file `android/app/build.gradle.kts` and find the `WS_URL` setting. Change it to your computer's IP address:
   
   ```kotlin
   // Example: if your computer's IP is 192.168.1.100
   WS_URL = "ws://192.168.1.100:8000/ws"
   ```

4. **Build and install the app:**
   
   Open the `android/` folder in Android Studio and run the app on your phone, or use command line:

   ```bash
   cd android
   ./gradlew installDebug
   ```

5. **Enable JoyPhone's accessibility service:**
   - Go to Settings → Accessibility → Installed Apps
   - Find "JoyPhone" or "PhoneAgent"
   - Enable it and grant all permissions

### Step 4: Test It!

1. Make sure your computer and phone are on the same WiFi network
2. Open the JoyPhone app on your phone
3. You should see a "Connected" status
4. Type a goal like "Open Feishu and send a message to Zhang San: Hello!"
5. Watch JoyPhone work!

## Using JoyPhone

### Basic Commands

Just type what you want to accomplish:

| What You Type | What JoyPhone Does |
|---------------|-------------------|
| "Send a WeChat message to Mom: I'll be home at 6" | Opens WeChat, finds Mom, sends the message |
| "Open Douyin and search for cooking videos" | Opens Douyin, uses search, shows results |
| "Forward this message to the work group" | Opens the relevant app, finds the group, forwards |
| "Open Settings and check my storage" | Opens Settings, navigates to storage info |

### Tips for Best Results

1. **Be specific**: Instead of "message John," try "send a WeChat message to John saying the meeting is at 3pm"

2. **Include context**: "Open Feishu, go to the Project Alpha group, and send: The report is ready"

3. **Check connectivity**: Make sure your phone stays connected to the same WiFi as your server

## Privacy & Security

- **Your phone, your server**: All AI processing happens on YOUR configured server
- **No third-party access**: Your data doesn't go to JoyPhone's developers
- **Local processing**: Screen content is analyzed by your own AI model
- **You control everything**: Stop the server anytime, and nothing leaves your network

## Architecture (For Developers)

JoyPhone has two main parts:

### Cloud Server (`server/`)
- **Python + FastAPI** — handles AI decisions and task management
- **WebSocket** — real-time communication with the phone
- **Decision Engine** — analyzes screens and decides actions
- **Skill Library** — remembers successful task patterns

### Android App (`android/`)
- **Kotlin + Jetpack Compose** — modern Android UI
- **Accessibility Service** — reads screens and performs actions
- **WebSocket Client** — stays connected to the cloud

## Contributing

JoyPhone is fully open-source. We welcome contributions of all kinds:

- Report bugs or suggest features via GitHub Issues
- Contribute code (see CONTRIBUTING section in docs)
- Share your successful "skills" with the community
- Improve documentation

## License

This project is open-source under the **MIT License**. You are free to use, modify, and distribute it.

---

**JoyPhone — Let AI use your phone like a human. The more you use it, the smarter it gets.**
