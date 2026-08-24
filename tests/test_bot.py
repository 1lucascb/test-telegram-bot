from bot import repeat_message, safe_api_call, ApiTelegramException

# Exception: environment variable 'TELEGRAM_BOT_TOKEN' is not set
# Solution: Define the TELEGRAM_BOT_TOKEN environment variable before running the tests. You can set it in your terminal or command prompt using:
# export TELEGRAM_BOT_TOKEN='0:0' pytest  # For Linux/Mac

def test_safe_api_call_retries(monkeypatch):
    class MockApiTelegramException(ApiTelegramException):
        def __init__(self, error_code, result_json):
            self.error_code = error_code
            self.result_json = result_json

    call_count = {"count": 0}

    def mock_func(*args, **kwargs):
        call_count["count"] += 1
        if call_count["count"] < 3:
            raise MockApiTelegramException(429, {"parameters": {"retry_after": 1}})
        return "Success"

    monkeypatch.setattr("bot.time.sleep", lambda x: None)  # Skip actual sleep for testing
    result = safe_api_call(mock_func)
    assert result == "Success"
    assert call_count["count"] == 3

