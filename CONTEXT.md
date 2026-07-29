# JoyPhone Agent 架构上下文

## 概述

JoyPhone 是一个手机 Agent 系统，云端 LLM 推理 + 设备端执行（SDK 或无障碍服务）。

## 核心实体

**Device（设备）**：
运行 JoyPhone 客户端的 Android 手机。

**SDK Provider（SDK 提供者）**：
设备端厂商 SDK（如 vivo SDK），提供系统级能力（force_stop、install_silent 等）。
配置固定，连接后不改变。

**A11Y（无障碍服务）**：
设备端 Android 无障碍服务，提供 UI 自动化能力（tap、input、swipe 等）。
不是 MCP Provider，不出现在 BM25 索引中。
SDK 没有某能力时，设备端自动 fallback 到 A11Y。

**MCP Router（MCP 路由）**：
云端组件，负责将 tool 调用路由到正确的 Provider。
优先使用 SDK Provider，SDK 没有该 tool 时 fallback 到 A11Y。

**BM25 Index（BM25 索引）**：
云端内存索引，支持 `search_tools(query)` 模糊搜索 Provider 暴露的工具。

**Decision（决策）**：
LLM 推理结果，包含 tool_name 和 arguments。

**Action（动作）**：
云端下发给设备端的具体操作指令。

## 关键规则

1. **SDK 固定配置**：用户配置后，SDK 类型不改变
2. **A11Y 万能兜底**：SDK 缺少的能力，自动用 A11Y 补充
3. **BM25 搜索发现**：LLM 通过 `search_tools` 搜索可用工具
4. **Provider 解耦**：LLM 不知道 Provider 概念，只知道 tool 名称
