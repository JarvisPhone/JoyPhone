"""BM25 索引召回归位 + 精简 schema 转换。"""
from __future__ import annotations

import pytest

from app.mcp.index import BM25Index
from app.mcp.protocol import ToolArgument, ToolDefinition


def _tool(name: str, desc: str, args: list[ToolArgument] | None = None) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=desc,
        arguments=args or [],
        provider="a11y",
    )


def _corpus() -> list[ToolDefinition]:
    return [
        _tool("force_stop", "强制停止某个应用,后台一键 kill", [ToolArgument(name="pkg", type="string")]),
        _tool("tap", "按语义锚点点击节点", [ToolArgument(name="match_text", type="string")]),
        _tool("swipe", "从一个点滑到另一个点", [
            ToolArgument(name="x1", type="number"),
            ToolArgument(name="y1", type="number"),
            ToolArgument(name="x2", type="number"),
            ToolArgument(name="y2", type="number"),
        ]),
        _tool("input", "在当前输入框输入文本", [ToolArgument(name="text", type="string")]),
        _tool("kill_background", "清理后台进程,常用于杀微信 qq", [ToolArgument(name="pkg", type="string")]),
        _tool("screenshot", "截屏返回 base64", []),
    ]


def test_search_basic_keyword_returns_relevant_tool():
    idx = BM25Index()
    idx.add(_corpus())
    res = idx.search("kill wechat")
    names = [r.tool.name for r in res]
    # "kill" 召回:force_stop/kill_background 都该上榜,screenshot 不该上
    assert "force_stop" in names
    assert "kill_background" in names
    assert "screenshot" not in names


def test_search_chinese_query_tokenizes_per_char():
    idx = BM25Index()
    idx.add(_corpus())
    res = idx.search("点击屏幕上的按钮")
    names = [r.tool.name for r in res]
    assert "tap" in names


def test_search_unknown_query_returns_empty():
    idx = BM25Index()
    idx.add(_corpus())
    assert idx.search("zzz_no_such_token") == []


def test_search_empty_corpus_returns_empty():
    idx = BM25Index()
    assert idx.search("anything") == []


def test_search_top_k_caps_results():
    idx = BM25Index()
    idx.add(_corpus())
    res = idx.search("kill app", top_k=2)
    assert len(res) <= 2


def test_search_scores_are_nonnegative_and_sorted_desc():
    idx = BM25Index()
    idx.add(_corpus())
    res = idx.search("input text")
    assert res, "expected at least one hit"
    for r in res:
        assert r.score >= 0
    for a, b in zip(res, res[1:]):
        assert a.score >= b.score


def test_tool_name_ranks_higher_than_description_only_token():
    """name 出现 3 次加权,应比 description-only token 命中更靠前。"""
    idx = BM25Index()
    tools = [
        _tool("screenshot", "返回一张截图"),
        _tool("kill_background", "截图分享入口"),  # "截图" 仅在描述里
    ]
    idx.add(tools)
    res = idx.search("截图")
    assert res[0].tool.name == "screenshot"


def test_to_llm_schema_strips_provider_field():
    idx = BM25Index()
    idx.add(_corpus())
    res = idx.search("tap")
    schemas = idx.to_llm_schema(res)
    assert schemas
    for s in schemas:
        assert s.name
        assert s.description
        # LLM 看不到 provider 字段(原 ToolDefinition.provider 不会被复制)
        assert not hasattr(s, "provider")


def test_clear_resets_index():
    idx = BM25Index()
    idx.add(_corpus())
    assert len(idx) == len(_corpus())
    idx.clear()
    assert len(idx) == 0
    assert idx.search("kill") == []


def test_idf_universal_token_is_lower_than_rare_token():
    """全文档通用 token 的 IDF 应低于稀有 token,等价于"通用词无判别力"。"""
    idx = BM25Index()
    tools = [
        _tool("tap", "通用的点击操作"),
        _tool("kill_background", "清理后台进程"),
    ]
    idx.add(tools)
    res = idx.search("kill 后台")
    # "kill" 仅出现在 kill_background 中,理应让它排第一
    assert res[0].tool.name == "kill_background"


def test_provider_field_required_for_internal_use():
    """ToolDefinition.provider 字段必须能写入并 round-trip,用于内部路由去 vendor 化。"""
    t = ToolDefinition(name="x", description="y", provider="vivo")
    assert t.provider == "vivo"
    dumped = t.model_dump()
    assert dumped["provider"] == "vivo"
    # LLM 侧协议层 ToolSchema 没有 provider 字段,这是契约
    from app.mcp.protocol import ToolSchema

    s = ToolSchema(name="x", description="y", arguments=[])
    assert "provider" not in s.model_dump()