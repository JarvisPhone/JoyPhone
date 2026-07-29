# Two-Root-Tools: search_tools and call_tool

LLM only sees two root tools: `search_tools(query)` for BM25-based tool discovery, and `call_tool(name, args)` for execution. The full tool registry (dozens of SDK methods) is never sent to LLM in the system prompt. This reduces token consumption and allows scaling to many tools without prompt explosion.
