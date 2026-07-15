from app.llm import FakeLLM
from app.negotiation import NegotiationBot, NegotiationIntent, NegotiationAction


class TestClassifyIntent:
    def test_confirm_intent(self):
        llm = FakeLLM(["confirm"])
        bot = NegotiationBot(llm=llm)

        assert bot.classify_intent("好的，我同意") == NegotiationIntent.CONFIRM
        assert bot.classify_intent("可以，没问题") == NegotiationIntent.CONFIRM

    def test_reject_intent(self):
        llm = FakeLLM(["reject"])
        bot = NegotiationBot(llm=llm)

        assert bot.classify_intent("不要了，谢谢") == NegotiationIntent.REJECT
        assert bot.classify_intent("我拒绝") == NegotiationIntent.REJECT

    def test_negotiate_intent(self):
        llm = FakeLLM(["negotiate"])
        bot = NegotiationBot(llm=llm)

        assert bot.classify_intent("能便宜点吗") == NegotiationIntent.NEGOTIATE
        assert bot.classify_intent("可以分期吗") == NegotiationIntent.NEGOTIATE

    def test_escalate_intent(self):
        llm = FakeLLM(["escalate"])
        bot = NegotiationBot(llm=llm)

        assert bot.classify_intent("我要转人工") == NegotiationIntent.ESCALATE
        assert bot.classify_intent("我要投诉") == NegotiationIntent.ESCALATE

    def test_empty_text_returns_unknown(self):
        llm = FakeLLM(["unknown"])
        bot = NegotiationBot(llm=llm)

        assert bot.classify_intent("") == NegotiationIntent.UNKNOWN
        assert bot.classify_intent("   ") == NegotiationIntent.UNKNOWN


class TestRespond:
    def test_confirm_reply_returns_done(self):
        llm = FakeLLM(['{"action":"done","reply":"好的，感谢确认！"}'])
        bot = NegotiationBot(llm=llm)

        result = bot.respond(goal="压价", incoming="好的，同意", history=[])

        assert result["action"] == NegotiationAction.DONE.value

    def test_negotiate_reply_returns_continue(self):
        llm = FakeLLM(['{"action":"continue","reply":"可以分期吗？"}'])
        bot = NegotiationBot(llm=llm)

        result = bot.respond(goal="压价", incoming="有点贵", history=[])

        assert result["action"] == NegotiationAction.CONTINUE.value
        assert "分期" in result["reply"]

    def test_escalate_reply_returns_escalate(self):
        llm = FakeLLM(['{"action":"escalate","reply":"为您转接人工"}'])
        bot = NegotiationBot(llm=llm)

        result = bot.respond(goal="压价", incoming="我要投诉", history=[])

        assert result["action"] == NegotiationAction.ESCALATE.value

    def test_empty_incoming_returns_continue(self):
        llm = FakeLLM(['{"action":"continue","reply":""}'])
        bot = NegotiationBot(llm=llm)

        result = bot.respond(goal="压价", incoming="", history=[])

        assert result["action"] == NegotiationAction.CONTINUE.value

    def test_reject_returns_escalate(self):
        llm = FakeLLM(['{"action":"escalate","reply":"明白"}'])
        bot = NegotiationBot(llm=llm)

        result = bot.respond(goal="压价", incoming="我不要", history=[])

        assert result["action"] == NegotiationAction.ESCALATE.value

    def test_fallback_on_llm_error(self):
        llm = FakeLLM([None])
        bot = NegotiationBot(llm=llm)

        result = bot.respond(goal="压价", incoming="你好", history=[])

        assert result["action"] == NegotiationAction.CONTINUE.value

    def test_history_formatted_in_prompt(self):
        captured = {}

        def capture_llm(system, user, image_b64=None):
            captured["system"] = system
            captured["user"] = user
            return '{"action":"continue","reply":"收到"}'

        from app.llm import LLM

        class CapturingLLM(LLM):
            def complete(self, system, user, image_b64=None):
                return capture_llm(system, user, image_b64)

        bot = NegotiationBot(llm=CapturingLLM())
        history = [
            {"role": "agent", "content": "您好"},
            {"role": "user", "content": "价格多少"},
        ]

        result = bot.respond(goal="销售", incoming="价格多少", history=history)

        assert "您好" in captured["system"]
        assert "价格多少" in captured["system"]


class TestParseResponse:
    def test_parse_valid_json(self):
        llm = FakeLLM(['{"action":"done","reply":"确认"}'])
        bot = NegotiationBot(llm=llm)

        result = bot.respond(goal="test", incoming="ok", history=[])

        assert result["action"] == "done"
        assert result["reply"] == "确认"

    def test_fallback_on_invalid_json(self):
        llm = FakeLLM(["这不是JSON格式"])
        bot = NegotiationBot(llm=llm)

        result = bot.respond(goal="test", incoming="hi", history=[])

        assert result["action"] == NegotiationAction.CONTINUE.value
