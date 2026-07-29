# A11Y as Universal Fallback, Not MCP Provider

A11Y (Android 无障碍服务) provides UI automation capabilities (tap, input, swipe, etc.) that work on any Android device. Instead of exposing A11Y as an MCP Provider in the tool registry, we route all UI operations through Action downlink, with the device falling back to AccessibilityService when the SDK Provider lacks the capability.

Key rules:
- A11Y is NOT an MCP Provider. It does NOT appear in BM25 search results.
- All UI operations (tap, input, swipe, etc.) are sent as Action downlink.
- When SDK Provider lacks a capability, device falls back to AccessibilityService automatically.
- BM25 index contains only SDK Provider tools.
