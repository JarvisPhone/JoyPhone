from app.llm import FakeLLM
from app.negotiation import NegotiationBot


def test_continue_reply():
    llm = FakeLLM(['{"status":"continue","reply":"可以分期吗？"}'])
    bot = NegotiationBot(llm=llm)

    result = bot.respond(goal="压价", incoming="有点贵", history=[])

    assert result["status"] == "continue"
    assert "分期" in result["reply"]


def test_handover_reply():
    llm = FakeLLM(['{"status":"handover","reply":""}'])
    bot = NegotiationBot(llm=llm)

    result = bot.respond(goal="压价", incoming="我要投诉", history=[])

    assert result["status"] == "handover"