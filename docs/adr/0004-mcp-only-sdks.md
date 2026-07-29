# MCP Registers Only SDK Providers, Not A11Y

ADR 0001 declared "A11Y is not an MCP Provider" as a rule, but Phase 1 still shipped a stub `A11yProvider` registered alongside `VivoProvider` in tests. This ADR codifies the corrected boundary after the A11yProvider removal: MCP Provider Registry only carries vendor SDK adapters (vivo / huawei / future), and A11Y ops flow exclusively through the Action downlink channel.

## Status

Accepted 2026-07-29. Implementation removed `server/app/mcp/providers/a11y/` directory and revised AGENTS.md boundary section.

## Context

Phase 1 introduced `A11yProvider` as a mock to unblock McpRouter integration tests. It exposed `force_stop / tap / swipe / input` as MCP tools — a category confusion that masked the real boundary:

- A11Y ops (`tap`, `input`, `swipe`, `back`, `home`, `read`, `wait`, `expect`, `done`, `abort`, ...) are universal — they exist on every Android device via `AccessibilityService`. No SDK, no certificate, no daemon-RPC.
- SDK ops (`force_stop_via_vivo`, `install_silent`, `lock_a11y`, `kill_background`, ...) are vendor-specific — they require a corporate SDK holder, certificate, and device daemon.

Putting `tap` in MCP makes no sense: a11y is the fallback, not a tool. ADR 0001 said so but the code still had `A11yProvider`. This commit removes the contradiction.

## Decision

### Channel split

| Channel | Source | Op set | Executor |
|---|---|---|---|
| **Action downlink** | `[TOOLS]` segment in system prompt | `tap / longpress / input / swipe / scroll_to / back / home / press_enter / open_notifications / open_quick_settings / expect / read / wait / done / abort` | Device AccessibilityService (universal fallback) |
| **MCP call_tool** | BM25 search → `ToolSchema` | `force_stop / install_silent / kill_background / reboot_device / lock_a11y / unlock_a11y / query_running_packages / ...` | Provider → DaemonClient → device daemon HTTP-RPC |

### Hard rules

1. `A11yProvider` does not exist. Do not add it back. Do not invent "UniversalProvider" / "FallbackProvider" abstractions.
2. `server/app/mcp/providers/` only hosts vendor SDK adapters. New providers follow `mcp/providers/<vendor>/<vendor>.py` and `register` to the global registry.
3. BM25 corpus = `registry.all_tools()` = SDK Provider tools union. A11y ops are never indexed.
4. Per device-capability architecture (2026-07-22): capability flows down to the device; op routing is on-device. The cloud only knows tools via BM25; the device daemon selects SDK execution or returns "unsupported".
5. Action and MCP call do not mix in the same decision frame. LLM produces either `Decision(actions=[...])` for Action downlink or `call_tool(name, args)` for SDK tool call — not both.

### Why "scenarios don't get a Provider either"

A natural temptation is to expose scenario-specific operations as MCP tools ("send_im", "open_chat"). Resist: those are compositions of A11Y ops + SDK ops, driven by scenario packs on the cloud side. The cloud composes; the device executes.

## Consequences

- A11Y is a real fallback, not a syscall. If SDK Provider can't `force_stop`, the cloud's failure path is "skip instance, log warning" — not "route to a11y provider with the same tool name".
- BM25 index is small and focused: only vendor SDK tools. LLM won't get confused by "tap" appearing as both a tool and an op.
- Adding a new vendor SDK is a one-place change: drop `mcp/providers/<vendor>/.py`, register in bootstrap. No touch on a11y paths.
- Test surface shrinks: BM25 tests don't need to fake a11y; router tests don't need the mock provider.
- Historical tests referencing `A11yProvider` must be cleaned up. This commit handles them.
- LLM must understand two channels in its prompt. `[TOOLS]` segment covers a11y; `search_tools` covers SDK. Documented in AGENTS.md.

## Rejected alternatives

- **Reuse `A11yProvider` as a real provider**: A11Y has no SDK, no certificate, no daemon. It would be a dead-end stub. Rejected.
- **Make A11Y a "default" provider**: when nothing else handles, route to a11y. This conflates routing with capability. Capability is on-device; routing is on-cloud. Rejected.
- **Unify Action and MCP into a single `tool` concept**: same JSON, different execution. Cleaner in theory, but loses the strong distinction that SDK ops require `device.hello` capability check while A11Y ops don't. Rejected for now; revisit if the dichotomy proves fragile in practice.
