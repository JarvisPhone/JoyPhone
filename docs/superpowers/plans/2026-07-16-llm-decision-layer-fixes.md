# LLM 决策层三个真机 e2e Bug 修复计划

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现本计划。步骤用 checkbox（`- [ ]`）语法跟踪。

**Goal:** 根治真机 e2e 暴露的 3 个 LLM 决策层 bug：进对 app 后误 back+home 退出、未确认群名就 input 正文（错群发消息）、home 被当作纠错手段过度使用。

**Architecture:** 三条线并行修复——(1) prompt 层：区分"跑错 app"vs"对 app 内子页"，明确"已在目标 app 内如何找会话"的导航指引，禁止在目标 app 内 home；(2) 云端守卫层：input 正文前必须先确认当前会话标题匹配 target_chat，不匹配则拦截并强制 back；(3) skill 编排层：修复 feishu_send_message skill 在真机首页 next_step 匹配失败静默回落 LLM 的问题。

**Tech Stack:** Python 3.12 / FastAPI(WebSocket 网关) / pytest。核心文件 `server/app/decision.py`、`server/app/gateway.py`、`server/app/skills.py`、`server/app/session.py`。

---

## 背景：真机 e2e 取证结论（systematic-debugging Phase 1）

日志 `server/logs/gateway.log` 第 3252~3323 行，会话时间 2026-07-16 19:44:27。任务 goal=`打开飞书，给群「Android AI 开发组」发一条消息`，target_pkg=`com.ss.android.lark`，target_chat=`Android AI 开发组`。

**关键决策链证据：**

| 行 | pkg | skill | 决策 | 问题 |
|----|-----|-------|------|------|
| 3254 | in_app | (PKG_GUARD) | op=home | 一进来在别的 app，守卫回桌面（合理）|
| 3269/3273 | launcher | None | swipe left×2 | 桌面翻页找图标（**非作弊，真在滑**）|
| 3277/3286/3289 | launcher | None | tap | 点飞书图标 |
| **3291** | **lark** | **feishu_send_message** | **op=back → home → read** | **进对 app 却决策退出（bug1）** |
| 3300 | lark | feishu_send_message | op=back | 继续误退 |
| 3303 | lark | feishu_send_message | input='Android AI 开发组' | 往搜索框输群名（合理）|
| 3315 | lark | feishu_send_message | tap | 进了某群 |
| **3318** | **lark** | **feishu_send_message** | **input='@全体成员 请大家修改群昵称...'** | **未确认群名就打正文（bug2，用户断网点）**|
| 3321 | lark | feishu_send_message | abort | LLM 自己发现"在奇瑞Robotaxi群不是目标群"，但正文已 input |

**三个 bug 定性：**
- **bug1（进对 app 后误退出）**：3291 帧 pkg==target_pkg（已在飞书），skill 已命中 feishu_send_message，但决策仍是 back+home。根因双重：(a) skill 的第一步 `tap desc=搜索` 在真机飞书首页 62 节点里 `next_step` 匹配失败，静默返回 None 回落 LLM；(b) `_SYSTEM_PROMPT` 的 app 边界约束只教了"跑错 app→back/home/read/tap"，没教"已在目标 app 内如何找会话"，LLM 缺乏正向指引时误用了退出模板。
- **bug2（错群 input 正文）**：本轮修复2 只拦截"tap 命中发送按钮"，`input` 完全放行。3318 在未确认群名的情况下 input 了正文。缺少"input 正文前校验当前会话标题==target_chat"的守卫。
- **bug3（home 过度使用）**：3293 在飞书内 decided home。正确纠错策略应是 back 回会话列表继续找，而非 home 退出整个 app（用户观点正确）。

**代码现状核实（避免臆造）：**
- `server/app/gateway.py:365-398`：拦截逻辑设计上**只拦「tap 命中发送按钮」**，input 文案「正常放行进框」（见 362-364 注释）。`match_chat_title(target_chat_name, current_title)` 只在 tap 发送前校验，input 时**完全不校验**。这就是 bug2 的直接原因。
- `server/app/skills.py:142-165`：`next_step` 在无节点匹配 step 时**静默返回 None**（165 行），无任何日志。DecisionEngine 随即回落 LLM。这是 bug1 根因(a)。
- `server/app/decision.py:270-278`：`_pkg_guard_action` 在 `pkg == target_pkg` 时返回 None（273 行），守卫不介入，交给 skill/LLM。3291 pkg==lark==target 所以守卫没拦，符合设计。
- `server/app/decision.py:34`：`_SYSTEM_PROMPT` 的「app 边界硬约束」只教了「跑错 app→back/home/read/tap」，缺「已在目标 app 内如何找会话」的正向指引。这是 bug1 根因(b)。

---

## File Structure

- `server/app/gateway.py`：新增 input 正文守卫（bug2 核心）。区分"搜索框 input"（放行）与"聊天输入框 input 正文"（需校验群名）。
- `server/app/decision.py`：修订 `_SYSTEM_PROMPT`，补"已在目标 app 内找会话"指引 + 禁止在目标 app 内 home（bug1(b)、bug3）。
- `server/app/skills.py`：`next_step` 匹配失败时记录诊断日志（bug1(a) 可观测性）。
- `server/app/chat_title_helpers.py`：复用已有 `detect_chat_title` / `match_chat_title` / `is_send_button`；bug2 需新增"判断某 input action 是否往聊天正文框输入"的辅助函数 `is_message_input`。
- 测试：`server/tests/test_gateway_loop.py`（bug2 守卫）、`server/tests/test_skills.py`（bug1 日志）、prompt 改动用现有断言或人工审查。

---

## Task 1: bug2——错群 input 正文守卫（最高优先级，防危险行为）

**目标**：LLM 决策 `input` 且该 input 是"往聊天正文框输入正文"（非搜索框）时，若当前会话标题不匹配 target_chat，则**拦截该 input**（不下发给端侧），并强制注入一个 `back` 动作回会话列表，同时记录日志。搜索框的 input（如输入群名搜索）不受影响。

**Files:**
- Modify: `server/app/chat_title_helpers.py`（新增 `is_message_input`）
- Modify: `server/app/gateway.py:400`（input 分支前插入守卫）
- Test: `server/tests/test_gateway_loop.py`

- [ ] **Step 1: 先读现有 helpers 确认可复用符号**

Run: `grep -n "def detect_chat_title\|def match_chat_title\|def is_send_button" server/app/chat_title_helpers.py`
Expected: 三个函数都存在。确认 `is_send_button(node)` 的签名与 Node 结构（`node.text`/`node.desc`/`node.className`/`node.bounds`）。

- [ ] **Step 2: 写 `is_message_input` 的失败测试**

在 `server/tests/test_skills.py` 或新建 `server/tests/test_chat_title_helpers.py` 中：

```python
from app.chat_title_helpers import is_message_input
from app.models import Node  # 按项目实际 Node 定义 import

def test_is_message_input_true_for_chat_editor():
    # 聊天正文输入框：EditText 且 desc/hint 含"输入"或在底部工具栏
    node = Node(text="", desc="输入消息", className="android.widget.EditText", bounds=[100, 2000, 900, 2160])
    assert is_message_input(node) is True

def test_is_message_input_false_for_search_box():
    # 搜索框：EditText 但 desc/hint 含"搜索"
    node = Node(text="", desc="搜索", className="android.widget.EditText", bounds=[100, 200, 900, 280])
    assert is_message_input(node) is False
```

- [ ] **Step 3: 运行测试确认失败**

Run: `cd server && .venv/bin/python -m pytest tests/test_chat_title_helpers.py -v`
Expected: FAIL with "cannot import name 'is_message_input'"

- [ ] **Step 4: 实现 `is_message_input`**

在 `server/app/chat_title_helpers.py` 末尾添加（`_SEARCH_HINTS`/`_MSG_HINTS` 按真机 desc 实际值调整，先用保守值）：

```python
_SEARCH_HINTS = ("搜索", "search")
_MSG_HINTS = ("输入", "发消息", "message", "说点什么")


def is_message_input(node) -> bool:
    """判断一个节点是否是「聊天正文输入框」（区别于搜索框）。

    规则：className 含 EditText；desc/text 命中消息类提示词且不含搜索类提示词。
    搜索框（desc 含"搜索"）明确返回 False，避免误伤"输入群名搜索"。
    """
    cls = (getattr(node, "className", "") or "").lower()
    if "edittext" not in cls:
        return False
    label = f"{getattr(node, 'desc', '') or ''}{getattr(node, 'text', '') or ''}".lower()
    if any(h in label for h in _SEARCH_HINTS):
        return False
    return any(h in label for h in _MSG_HINTS)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd server && .venv/bin/python -m pytest tests/test_chat_title_helpers.py -v`
Expected: PASS

- [ ] **Step 6: 写 gateway input 守卫的失败测试**

在 `server/tests/test_gateway_loop.py` 添加（复用文件内既有的 fake WS / session 构造模式，参照同文件 `test_send_intercept*` 类测试的搭建方式）：

```python
def test_input_message_in_wrong_chat_is_intercepted(...):
    # 构造：pkg==target_pkg(lark)，nodeTree 含一个聊天正文输入框(is_message_input=True)
    # 且当前会话标题="奇瑞Robotaxi项目" != target_chat="Android AI 开发组"
    # LLM 决策 op=input text="正文"
    # 断言：该 input 未被 send_text 下发；改为下发一个 op=back；日志含 [INPUT_GUARD]
    ...
```

- [ ] **Step 7: 运行测试确认失败**

Run: `cd server && .venv/bin/python -m pytest tests/test_gateway_loop.py::test_input_message_in_wrong_chat_is_intercepted -v`
Expected: FAIL（当前 input 被直接放行）

- [ ] **Step 8: 在 gateway.py input 分支前插入守卫**

在 `server/app/gateway.py:400` 的 `if action.op in ("tap", "input"):` **之前**插入：

```python
                # 【错群防护】input 正文前必须确认当前会话标题匹配 target_chat。
                # 仅拦「聊天正文框 input」，搜索框 input（输群名搜索）放行。
                if (
                    action.op == "input"
                    and target_app_pkg
                    and uplink.pkg == target_app_pkg
                    and target_chat_name
                ):
                    from app.chat_title_helpers import is_message_input
                    input_id = action.params.get("id")
                    target_node = next(
                        (n for n in uplink.nodeTree if str(getattr(n, "index", "")) == str(input_id)),
                        None,
                    )
                    if target_node is not None and is_message_input(target_node):
                        current_title = detect_chat_title(uplink.nodeTree)
                        if not (current_title and match_chat_title(target_chat_name, current_title)):
                            logger.warning(
                                "[INPUT_GUARD] 拦截错群 input：target=%s current=%s text=%r -> 强制 back",
                                target_chat_name, current_title, action.params.get("text"),
                            )
                            _back = Action(op="back", params={}).to_json()
                            log_down("action", _back)
                            await websocket.send_text(_back)
                            break  # 结束本批，重抓帧
```

- [ ] **Step 9: 运行测试确认通过**

Run: `cd server && .venv/bin/python -m pytest tests/test_gateway_loop.py::test_input_message_in_wrong_chat_is_intercepted -v`
Expected: PASS

- [ ] **Step 10: 跑该文件全量回归**

Run: `cd server && .venv/bin/python -m pytest tests/test_gateway_loop.py -v`
Expected: 新测试 PASS，既有测试无新增失败（已知 `test_gateway_budget_exhausted_aborts` 为改动前既有失败，忽略）。

- [ ] **Step 11: Commit**

```bash
git add server/app/chat_title_helpers.py server/app/gateway.py server/tests/test_chat_title_helpers.py server/tests/test_gateway_loop.py
git commit -m "fix(gateway): 错群 input 正文守卫，未匹配 target_chat 时拦截并强制 back"
```

---

## Task 2: bug1(b) + bug3——修订 _SYSTEM_PROMPT（补正向指引 + 禁 app 内 home）

**目标**：在 `_SYSTEM_PROMPT` 的「app 边界硬约束」里补两条：(1) `pkg == target_pkg` 时如何在目标 app 内找会话（用搜索/上下滑，禁 back+home 退出）；(2) 明确"已在目标 app 内，禁止输出 home"。修 3291 的 back+home 误决策与 3293 的 home 过度使用。

**Files:**
- Modify: `server/app/decision.py:37`（`pkg == target_pkg` 那条约束的展开）

- [ ] **Step 1: 读现状确认待改行**

Run: `grep -n "如果 target_pkg 非空 且 pkg == target_pkg" server/app/decision.py`
Expected: 命中 37 行 `- 如果 target_pkg 非空 且 pkg == target_pkg：正常推进任务。`

- [ ] **Step 2: 替换该行为更明确的正向指引**

把 `server/app/decision.py:37` 的整行：

```
- 如果 target_pkg 非空 且 pkg == target_pkg：正常推进任务。
```

替换为：

```
- 如果 target_pkg 非空 且 pkg == target_pkg：你**已经在目标 app 内**，绝不要输出 `home`，也不要用 `back`+`home` 退出当前 app。此时只需在 app 内推进任务：找不到目标会话/页面时，用搜索框输入名称搜索，或用 `swipe up`/`swipe down` 在列表内滚动查找；进错了子页（如进错群聊）用**单个 `back`** 回上一级列表继续找，禁止一路 back+home 退回桌面重来。
```

- [ ] **Step 3: 在「打开应用的流程」后补充「app 内找会话的流程」**

在 `server/app/decision.py:45`（`4. 若连续多次 swipe left...abort` 那行）之后、`【重要·负一屏识别】` 之前，插入一段：

```

在目标 app 内找会话/联系人的流程(pkg == target_pkg 时)：
1. 优先用顶部搜索：tap 搜索框 -> input 目标名称 -> 在结果里 tap 匹配项。
2. 进入会话后，先核对页面顶部标题是否与目标会话名一致；不一致说明进错，输出单个 `back` 回上一级，换一个结果再试或重新搜索。
3. 反复 back 后仍找不到目标会话 -> abort，原因填「未找到会话<名称>」。禁止用 home 退出 app。
```

- [ ] **Step 4: 修订「跑错应用」示例的措辞，避免被 app 内场景误用**

把 `server/app/decision.py:61` 的：

```
示例(跑错应用,回桌面重开目标 app)：
```

替换为（强调仅限 pkg != target_pkg）：

```
示例(仅当 pkg != target_pkg 即跑错应用时,回桌面重开目标 app)：
```

- [ ] **Step 5: 语法自检**

Run: `cd server && .venv/bin/python -c "import app.decision"`
Expected: 无报错（prompt 是字符串，只验证模块可导入、无语法错误）。

- [ ] **Step 6: 人工审查 prompt 一致性**

通读修订后的 `_SYSTEM_PROMPT`，确认：不存在"pkg==target 时仍鼓励 back+home"的表述；"打开应用流程"（pkg!=target）与"app 内找会话流程"（pkg==target）两段互不冲突。

- [ ] **Step 7: Commit**

```bash
git add server/app/decision.py
git commit -m "fix(prompt): app 内正向找会话指引，禁止已在目标 app 内 home/back+home"
```

---

## Task 3: bug1(a)——skill next_step 匹配失败可观测性

**目标**：`SkillLibrary.next_step` 在 skill 命中但当前帧无节点匹配 step（返回 None，回落 LLM）时打一条 warning 日志。不改变控制流（仍回落 LLM），只补可观测性，方便后续判断"是 skill 匹配太脆还是 LLM 误判"。

**Files:**
- Modify: `server/app/skills.py:165`（`return None` 前加日志）
- Test: `server/tests/test_skills.py`

- [ ] **Step 1: 写失败测试（断言日志）**

在 `server/tests/test_skills.py` 添加：

```python
import logging

def test_next_step_logs_when_no_node_matches(caplog):
    lib = SkillLibrary()  # 按文件内既有构造方式
    nodes = []  # 空节点，必然匹配失败
    with caplog.at_level(logging.WARNING, logger="phoneagent.skills"):
        result = lib.next_step("feishu_send_message", nodes, cursor=0)
    assert result is None
    assert any("SKILL_NO_MATCH" in r.message for r in caplog.records)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd server && .venv/bin/python -m pytest tests/test_skills.py::test_next_step_logs_when_no_node_matches -v`
Expected: FAIL（当前无日志）

- [ ] **Step 3: 在 next_step 的末尾 return None 前加日志**

把 `server/app/skills.py:165` 的：

```python
        return None
```

（`next_step` 方法体内、for 循环后那一处）替换为：

```python
        logging.getLogger("phoneagent.skills").warning(
            "[SKILL_NO_MATCH] skill=%s cursor=%s step_op=%s 当前帧无节点匹配，回落 LLM 决策",
            skill_name, cursor, step.op,
        )
        return None
```

确认文件顶部已 `import logging`；若无则在 import 区添加。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd server && .venv/bin/python -m pytest tests/test_skills.py::test_next_step_logs_when_no_node_matches -v`
Expected: PASS

- [ ] **Step 5: 跑 skills 全量回归**

Run: `cd server && .venv/bin/python -m pytest tests/test_skills.py -v`
Expected: 无新增失败。

- [ ] **Step 6: Commit**

```bash
git add server/app/skills.py server/tests/test_skills.py
git commit -m "feat(skills): next_step 匹配失败时记录 SKILL_NO_MATCH 日志便于诊断回落"
```

---

## Task 4: 全量回归 + 真机 e2e 复验

- [ ] **Step 1: 全量回归**

Run: `cd server && .venv/bin/python -m pytest -q`
Expected: 除既有 4 个 baseline 失败外无新增失败。逐一比对失败列表与 baseline（`test_skill_hit_without_llm`、`test_gateway_budget_exhausted_aborts`、`test_fake_llm_returns_last_when_exhausted`、`test_llm_is_abstract`）。

- [ ] **Step 2: 重启 uvicorn 使改动生效**

```bash
pkill -f "uvicorn app.gateway" || true
cd /Users/leijiabin.1/myspace/JoyPhone/server && nohup .venv/bin/python -m uvicorn app.gateway:create_app --factory --host 0.0.0.0 --port 8000 > logs/uvicorn_e2e.log 2>&1 &
```

- [ ] **Step 3: 真机 e2e 复验同一任务**

真机下发 `打开飞书，给群「Android AI 开发组」发一条消息`。验证点（**禁 uiautomator/截图，仅看 gateway.log 决策链**）：
- 进入飞书后无 back+home（bug1 已修）
- 未匹配群名时不 input 正文，出现 `[INPUT_GUARD]` 拦截 + back（bug2 已修）
- 无 app 内 home（bug3 已修）
- skill 匹配失败时可见 `[SKILL_NO_MATCH]`（bug1(a) 可观测）

---

## Self-Review

**1. Spec coverage：**
- bug1(a) skill 静默回落 → Task 3 加日志（可观测性；控制流不变，因为 LLM 回落本身是设计，真正修 LLM 误判靠 Task 2 prompt）✅
- bug1(b) prompt 缺正向指引 → Task 2 ✅
- bug2 错群 input 正文 → Task 1 ✅
- bug3 home 过度使用 → Task 2（禁 app 内 home）✅

**2. Placeholder scan：** Task 1 Step 6 的 gateway 测试用了"参照同文件既有测试搭建"的描述而非完整测试体——因为该测试需要复用 test_gateway_loop.py 里较重的 fake WS/session fixture，执行时须先读该文件的既有 send-intercept 测试照搬骨架。**执行者注意：Step 6 必须先读 `server/tests/test_gateway_loop.py` 的现有 tap 拦截测试，照其 fixture 结构写，不可凭空造 Node/WS。**

**3. Type consistency：** `is_message_input(node)` 在 Task 1 定义并在 gateway 守卫中调用，签名一致；`detect_chat_title`/`match_chat_title` 复用 gateway 已 import 的符号；`SKILL_NO_MATCH`/`INPUT_GUARD`/`SKILL_NO_MATCH` 日志 tag 前后一致。

**4. 顺序建议：** Task 1（防危险行为）最高优先，先做。Task 2、3 可并行。

**⚠️ 风险与前置确认：**
- 本轮已 GREEN 但未 commit 的**云端修复**（active 闸门 + tap 发送拦截 + 死代码清理）与本 plan 是**不同 scope**。执行前需与用户确认：先 commit 云端修复，再按本 plan 分 3 个独立 commit 处理 LLM 决策层。
- `is_message_input` 的 `_MSG_HINTS`/`_SEARCH_HINTS` 需用真机飞书实际节点 desc 校准（先用保守值，真机复验时按 gateway.log/comm.log 里的实际 desc 微调）。
- prompt 改动无法单测覆盖行为，只能靠真机 e2e 复验，属"验证滞后"风险点。

---