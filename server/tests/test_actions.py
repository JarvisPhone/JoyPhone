"""parse_actions / Op 协议层新增 3 op 的契约测试。

覆盖 2026-07-26 P2 expansion Task 1:scroll_to / open_notifications / open_quick_settings。

TDD discipline:这些测试应先于实现写出来,实装后变绿;
若有人改 engine._NOARG_OPS / parse_actions / protocol.Op,这些测试会报警。
"""
from app.decision.engine import _NOARG_OPS, parse_actions
from app.protocol import Op


def test_protocol_op_literal_includes_scroll_to():
    """协议 v2 Op 字面量类型含 scroll_to,作为下行 action 的合法值。"""
    # Op 是 typing.Literal,运行时等同于字符串;具体校验通过 _validate 行为可见。
    assert "scroll_to" in Op.__args__


def test_protocol_op_literal_includes_open_notifications():
    assert "open_notifications" in Op.__args__


def test_protocol_op_literal_includes_open_quick_settings():
    assert "open_quick_settings" in Op.__args__


def test_noarg_ops_maps_open_notifications():
    """open_notifications 无参动词走 _NOARG_OPS,parse_actions 输出 op 字段。"""
    specs = parse_actions("open_notifications")
    assert specs == [{"op": "open_notifications"}]


def test_noarg_ops_maps_open_quick_settings():
    specs = parse_actions("open_quick_settings")
    assert specs == [{"op": "open_quick_settings"}]


def test_scroll_to_top_direction():
    """scroll_to top 解析为 direction=top。"""
    specs = parse_actions("scroll_to top")
    assert specs == [{"op": "scroll_to", "direction": "top"}]


def test_scroll_to_bottom_direction():
    specs = parse_actions("scroll_to bottom")
    assert specs == [{"op": "scroll_to", "direction": "bottom"}]


def test_scroll_to_invalid_direction_ignored():
    """scroll_to 后跟非 top/bottom 视为无效,跳过(specs 空)。"""
    assert parse_actions("scroll_to side") == []


def test_scroll_to_no_direction_ignored():
    """scroll_to 不带参数视为无效(必须 top/bottom)。"""
    assert parse_actions("scroll_to") == []


def test_unknown_verb_still_skipped():
    """未在 _NOARG_OPS / 解析分支注册的 verb 静默跳过(保持向后兼容)。"""
    assert parse_actions("fly_to_mars") == []


def test_open_quick_settings_in_noarg_map():
    """_NOARG_OPS 是 freeze 字典(实装用),确保 open_* 在里面。"""
    assert _NOARG_OPS["open_notifications"] == "open_notifications"
    assert _NOARG_OPS["open_quick_settings"] == "open_quick_settings"