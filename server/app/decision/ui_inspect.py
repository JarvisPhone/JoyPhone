"""通用 UI 识别 helpers(从 chat_title_helpers 移植并参数化)。

纯函数,无副作用。关键词表由调用方传入,使本模块与具体聊天 App
(飞书/微信/QQ)的关键词解耦,可复用于任意 title 识别场景。
"""
from __future__ import annotations

from typing import Iterable, Optional

from app.protocol import Node


def detect_title(
    nodeTree: Iterable[Node],
    title_keywords: tuple[str, ...],
    desc_keywords: tuple[str, ...] = ("title", "标题"),
) -> Optional[str]:
    """从当前屏幕节点树里识别页面标题(如聊天页顶部 toolbar 的群名/联系人名)。

    策略(按优先级):
      1. resource id 含 title_keywords 任一关键词的节点的 text
      2. desc 含 desc_keywords 任一关键词的节点的 text(部分 app 用 content-desc 而非 text)
      3. 退化:第一个非输入区、长度 >= 2 的非空 text

    返回 None 表示当前页无法识别标题。
    """
    nodes = list(nodeTree)

    for n in nodes:
        rid = (n.viewIdResourceName or "").lower()
        if any(k in rid for k in title_keywords):
            t = (n.text or "").strip()
            if len(t) >= 2:
                return t

    for n in nodes:
        desc = (n.desc or "").lower()
        raw_desc = n.desc or ""
        if any(k.lower() in desc or k in raw_desc for k in desc_keywords):
            t = (n.text or raw_desc).strip()
            if len(t) >= 2:
                return t

    for n in nodes:
        if n.editable:
            continue
        t = (n.text or "").strip()
        if len(t) >= 2:
            return t

    return None


def match_title(target: str, current: str) -> bool:
    """宽松匹配:target 是 current 的子串,或 current 是 target 的子串。

    用于容忍真机上标题带后缀(企业标记/emoji/标点)的情况。
    """
    if not target or not current:
        return False
    t = target.replace(" ", "").strip()
    c = current.replace(" ", "").strip()
    if not t or not c:
        return False
    return t in c or c in t
