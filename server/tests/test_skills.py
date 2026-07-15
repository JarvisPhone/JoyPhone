from app.protocol import Node
from app.skills import SkillLibrary, SkillStep, SkillMatcher, Skill


class TestSkillMatcher:
    def test_match_by_text(self):
        nodes = [
            Node(id="n1", text="通讯录", clickable=True),
            Node(id="n2", text="搜索", clickable=True),
        ]

        step = SkillStep(op="tap", text="通讯录")
        assert SkillMatcher.match_node(step, nodes, 0) is True
        assert SkillMatcher.match_node(step, nodes, 1) is False

    def test_match_by_desc(self):
        nodes = [
            Node(id="n1", text="", desc="搜索图标", clickable=True),
        ]

        step = SkillStep(op="tap", desc="搜索图标")
        assert SkillMatcher.match_node(step, nodes, 0) is True

    def test_match_by_view_id(self):
        nodes = [
            Node(id="n1", text="", viewIdResourceName="com.feishu:id/search"),
        ]

        step = SkillStep(op="tap", view_id="search")
        assert SkillMatcher.match_node(step, nodes, 0) is True

    def test_match_by_index(self):
        nodes = [
            Node(id="n1", text="A"),
            Node(id="n2", text="B"),
        ]

        step = SkillStep(op="tap", index=1)
        assert SkillMatcher.match_node(step, nodes, 0) is False
        assert SkillMatcher.match_node(step, nodes, 1) is True


class TestSkillLibrary:
    def test_get_skill(self):
        library = SkillLibrary()

        skill = library.get("feishu_send_message")
        assert skill is not None
        assert skill.name == "feishu_send_message"
        assert skill.app == "com.ss.android.lark"

    def test_unknown_skill_returns_none(self):
        library = SkillLibrary()

        step = library.next_step("unknown_skill", [], 0)
        assert step is None

    def test_next_step_match(self):
        library = SkillLibrary()
        nodes = [
            Node(id="n1", text="", desc="搜索", clickable=True),
            Node(id="n2", text="发送", clickable=True),
        ]

        step = library.next_step("feishu_send_message", nodes, 0)
        assert step is not None
        assert step["op"] == "tap"

    def test_next_step_cursor_out_of_range(self):
        library = SkillLibrary()
        nodes = [Node(id="n1", text="搜索")]

        step = library.next_step("feishu_send_message", nodes, 999)
        assert step is None

    def test_select_by_goal_and_pkg(self):
        library = SkillLibrary()

        skill_name = library.select("在飞书给张三发消息", "com.ss.android.lark")
        assert skill_name == "feishu_send_message"

    def test_select_no_match_returns_none(self):
        library = SkillLibrary()

        skill_name = library.select("打开微信", "com.tencent.mm")
        assert skill_name is None

    def test_register_new_skill(self):
        library = SkillLibrary()
        new_skill = Skill(
            name="wechat_send",
            app="com.tencent.mm",
            description="微信发送消息",
            keywords=["微信", "发送"],
            steps=[SkillStep(op="tap", text="发送")],
        )

        library.register(new_skill)

        assert library.get("wechat_send") is not None
        assert library.select("打开微信发消息", "com.tencent.mm") == "wechat_send"


class TestSkillStep:
    def test_to_dict(self):
        step = SkillStep(op="tap", text="搜索", input_text="hello")
        d = step.to_dict()

        assert d["op"] == "tap"
        assert d["text"] == "搜索"
        assert d["input_text"] == "hello"

    def test_from_dict(self):
        d = {"op": "tap", "text": "搜索", "input_text": "hi"}
        step = SkillStep.from_dict(d)

        assert step.op == "tap"
        assert step.text == "搜索"
        assert step.input_text == "hi"
