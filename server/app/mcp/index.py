"""BM25 工具索引:LLM 的 search_tools(query) 后端。

设计要点:
- 纯 stdlib,无第三方依赖(不引入 rank_bm25,避免新增包)
- 索引常驻内存:Provider 注册时 rebuild,增量时按需重建(Phase 1 用全量 rebuild)
- 召回后只下发精简 schema(去 provider 字段),让 LLM 看不到 vendor
- 默认 top-K=10,由 Config.MCP_SEARCH_TOP_K 控制
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from app.mcp.protocol import ToolDefinition, ToolSchema

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[一-鿿]")


def _tokenize(text: str) -> list[str]:
    """极简分词:英文/数字按 word(下划线作分隔符),中文按单字。

    不引分词器,Phase 1 只要求召回,不要求语义精度。
    中文字符之间无空格边界,整段切会让"截图"和"截图分享"
    变成两个不相干的 token;单字 + 1-gram 简单可靠,后续可换 jieba。
    """
    if not text:
        return []
    out: list[str] = []
    for m in _TOKEN_RE.finditer(text):
        s = m.group(0)
        if not s:
            continue
        # _TOKEN_RE 把英文/数字作为一个 token,中文每个字一个 token
        # 直接 append,小写归一化只对英文必要(中文大小写无意义)
        if "一" <= s[0] <= "鿿":
            out.append(s)
        else:
            out.append(s.lower())
    return out


@dataclass
class ScoredTool:
    """召回结果:(tool, score)。score 越大越相关。"""

    tool: ToolDefinition
    score: float


class BM25Index:
    """内存 BM25 索引。

    使用方式:
        idx = BM25Index()
        idx.add(tools)
        idx.search("kill wechat") -> [ScoredTool(...)]
    """

    # 标准 BM25 参数(经验值,k1=1.5 / b=0.75)
    K1 = 1.5
    B = 0.75

    def __init__(self) -> None:
        self._docs: list[ToolDefinition] = []
        # 倒排:token -> 该 token 出现的 doc 索引集合(去重用 set 转 list 时排序)
        self._postings: dict[str, list[int]] = {}
        # 每个 doc 的 token 计数与长度(按出现次数加权)
        self._doc_tf: list[Counter[str]] = []
        self._doc_len: list[int] = []
        self._avgdl: float = 0.0
        self._n_docs: int = 0
        self._idf: dict[str, float] = {}

    def add(self, tools: list[ToolDefinition]) -> None:
        """全量加入并重建索引。Phase 1 用全量重建;Phase 3 改增量。"""
        for t in tools:
            self._docs.append(t)
            tokens = self._index_tokens(t)
            tf = Counter(tokens)
            self._doc_tf.append(tf)
            self._doc_len.append(len(tokens))
            for tok in tf:
                self._postings.setdefault(tok, []).append(len(self._docs) - 1)
        self._recompute_stats()

    def clear(self) -> None:
        self._docs.clear()
        self._postings.clear()
        self._doc_tf.clear()
        self._doc_len.clear()
        self._idf.clear()
        self._avgdl = 0.0
        self._n_docs = 0

    def __len__(self) -> int:
        return self._n_docs

    def _index_tokens(self, t: ToolDefinition) -> list[str]:
        """把 tool 的字段拼成可索引文本(name 重复加权,name 最重要)。"""
        parts: list[str] = []
        # name 出现 3 次(强化召回权重,符合"工具名就是关键词"的直觉)
        parts.extend([t.name] * 3)
        if t.description:
            parts.append(t.description)
        for arg in t.arguments:
            parts.append(arg.name)
            if arg.description:
                parts.append(arg.description)
        return _tokenize(" ".join(parts))

    def _recompute_stats(self) -> None:
        self._n_docs = len(self._docs)
        if self._n_docs == 0:
            self._avgdl = 0.0
            self._idf = {}
            return
        self._avgdl = sum(self._doc_len) / self._n_docs
        idf: dict[str, float] = {}
        n = self._n_docs
        for tok, postings in self._postings.items():
            df = len(postings)
            # BM25+ IDF:ln(1 + (N - df + 0.5) / (df + 0.5))
            # 用 +1 平滑避免 df=N 时 IDF 为 0
            idf[tok] = math.log(1.0 + (n - df + 0.5) / (df + 0.5))
        self._idf = idf

    def search(self, query: str, top_k: int = 10) -> list[ScoredTool]:
        """按 BM25 打分,返回 top-K(按 score 倒序,score=0 剔除)。"""
        tokens = _tokenize(query)
        if not tokens or self._n_docs == 0:
            return []
        scores: dict[int, float] = {}
        for tok in tokens:
            postings = self._postings.get(tok)
            if not postings:
                continue
            idf = self._idf.get(tok, 0.0)
            for doc_idx in postings:
                tf = self._doc_tf[doc_idx][tok]
                dl = self._doc_len[doc_idx]
                denom = tf + self.K1 * (1.0 - self.B + self.B * dl / self._avgdl)
                inc = idf * (tf * (self.K1 + 1.0)) / denom
                scores[doc_idx] = scores.get(doc_idx, 0.0) + inc
        scored = [
            ScoredTool(tool=self._docs[i], score=s)
            for i, s in scores.items()
            if s > 0
        ]
        scored.sort(key=lambda x: x.score, reverse=True)
        return scored[:top_k]

    def to_llm_schema(self, scored: list[ScoredTool]) -> list[ToolSchema]:
        """把召回结果转成 LLM 可见的精简 schema(剥掉 provider 字段)。"""
        return [
            ToolSchema(
                name=s.tool.name,
                description=s.tool.description,
                arguments=s.tool.arguments,
            )
            for s in scored
        ]