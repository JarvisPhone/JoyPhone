from app.infra.config import Config


def test_constants():
    assert Config.MAX_STEPS_DEFAULT == 40
    assert Config.CONFIRM_ID_PREFIX == "cfm"
    assert Config.CONFIRM_ID_LENGTH == 8
    assert Config.MAX_CONFIRM_COUNT == 1
    assert Config.CONFIRM_TIMEOUT_MS == 5000
    assert Config.PRE_SEND_REVERT_WINDOW_SEC == 10.0
    assert Config.POST_SEND_PATROL_THRESHOLD == 2
    assert Config.WRONG_CHAT_INPUT_THRESHOLD == 2
    assert Config.AWAITING_CONFIRM_TIMEOUT_SEC == 30
