import json
import uuid

from app.llm import LLM
from app.protocol import Action, Perception
from app.skill_cache import SkillCache
from app.skills import SkillLibrary


_SYSTEM_PROMPT = """你是一个 Android 手机操作代理的决策核心。给定当前屏幕的可交互节点、任务目标和历史操作，你必须决定「下一步」执行的单个 UI 动作。

你必须只输出一个 JSON 对象，不要输出任何解释、思考过程、Markdown 代码块或额外文字。

JSON 格式：{"op": "<操作类型>", "params": {<参数键值对，值必须为字符串>}}

合法的 op 取值及其含义：
- tap: 点击某个节点。params: {"match_text": "节点文本"} 或 {"id": "节点id"}
- input: 在输入框输入文本。params: {"text": "要输入的内容", "match_text": "输入框附近文本(可选)"}
- swipe: 滑动。params: {"direction": "up|down|left|right"}
- back: 返回键。params: {}
- home: 回到桌面。params: {}
- home_first_page: 回到桌面并归位到最左第一屏(打开应用前必先执行)。params: {}
- next_page: 在桌面向后翻一屏找应用图标。params: {}
- wait: 等待。params: {"ms": "毫秒数"}
- read_screen: 重新读取屏幕(当信息不足以决策时用)。params: {}
- done: 任务已完成。params: {}
- abort: 无法完成任务，放弃。params: {"reason": "原因"}

打开应用的流程：
1. 先 home_first_page 回到桌面第一屏
2. read_screen 读取当前屏，在节点里找目标应用图标(按名称匹配)
3. 找到图标 -> tap 打开；没找到 -> next_page 翻到下一屏，再 read_screen 继续找
4. 若某次 next_page 后返回的历史记录里 atEnd 为 true 且仍没找到图标 -> abort，reason 填「未找到应用<名称>」

示例：
看到搜索框 -> {"op": "input", "params": {"text": "张三", "match_text": "搜索"}}
信息不足 -> {"op": "read_screen", "params": {}}"""


class DecisionEngine:
    def __init__(self, llm: LLM, skills: SkillLibrary, cache: SkillCache | None = None):
        self._llm = llm
        self._skills = skills
        self._cache = cache

    def _cache_step(self, goal: str, perception: Perception, cursor: int) -> dict | None:
        if self._cache is None:
            return None
        entry = self._cache.get(goal, perception.pkg)
        if entry is None or cursor >= len(entry["steps"]):
            return None
        step = entry["steps"][cursor]
        match_text = step.get("params", {}).get("match_text", "")
        if match_text and not any(match_text in (n.text or "") for n in perception.nodeTree):
            return None  # 无法重定位 -> 回退
        return step

    def decide(
        self,
        goal: str,
        perception: Perception,
        skill_name: str | None,
        cursor: int,
        history: list[dict],
    ) -> Action:
        step = self._cache_step(goal, perception, cursor)
        if step is not None:
            return Action(actionId=str(uuid.uuid4()), op=step["op"], params=step.get("params", {}))

        if skill_name:
            step = self._skills.next_step(skill_name, perception.nodeTree, cursor)
            if step is not None:
                params = {k: v for k, v in step.items() if k != "op"}
                return Action(actionId=str(uuid.uuid4()), op=step["op"], params=params)

        payload = {
            "goal": goal,
            "nodes": [n.model_dump(exclude_none=True) for n in perception.nodeTree],
            "history": history,
        }
        raw = self._llm.complete(
            system=_SYSTEM_PROMPT,
            user=json.dumps(payload, ensure_ascii=False),
        )
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return Action(actionId=str(uuid.uuid4()), op="read_screen", params={})
        if not isinstance(data, dict) or "op" not in data:
            return Action(actionId=str(uuid.uuid4()), op="read_screen", params={})
        return Action(actionId=str(uuid.uuid4()), op=data["op"], params=data.get("params", {}))