import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from card_generator.llm import LLMClient, LLMError


@contextmanager
def fake_api(status: int, body: dict):
    """A local HTTP server that answers every POST the same way and keeps the request bodies."""
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, format, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", requests
    finally:
        server.shutdown()


def completion(content: str) -> dict:
    return {
        "id": "test",
        "object": "chat.completion",
        "created": 0,
        "model": "test-model",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
    }


def error(message: str) -> dict:
    return {"error": {"message": message, "type": "invalid_request_error"}}


MESSAGES = [{"role": "user", "content": "Карточка для манометра"}]


def test_returns_model_answer_and_asks_for_json():
    with fake_api(200, completion('{"seo_title": "Манометр"}')) as (url, requests):
        answer = LLMClient(url, "test-model", max_retries=0).complete_json(MESSAGES)

    assert answer == '{"seo_title": "Манометр"}'
    assert requests[0]["model"] == "test-model"
    assert requests[0]["messages"] == MESSAGES
    assert requests[0]["response_format"] == {"type": "json_object"}
    assert requests[0]["temperature"] == 0.3
    assert requests[0]["max_tokens"] == 2500


def test_temperature_and_length_cap_can_be_left_to_the_provider():
    with fake_api(200, completion("{}")) as (url, requests):
        LLMClient(url, "test-model", temperature=None, max_tokens=None, max_retries=0).complete_json(MESSAGES)

    assert "temperature" not in requests[0]
    assert "max_tokens" not in requests[0]


def test_empty_answer_is_an_error():
    with fake_api(200, completion("")) as (url, _):
        with pytest.raises(LLMError, match="пуст"):
            LLMClient(url, "test-model", max_retries=0).complete_json(MESSAGES)


def test_wrong_key_points_to_the_key_setting():
    with fake_api(401, error("Incorrect API key provided")) as (url, _):
        with pytest.raises(LLMError, match="LLM_API_KEY"):
            LLMClient(url, "test-model", max_retries=0).complete_json(MESSAGES)


def test_unknown_model_names_the_model():
    with fake_api(404, error("model 'qwen9:70b' not found")) as (url, _):
        with pytest.raises(LLMError, match="qwen9:70b"):
            LLMClient(url, "qwen9:70b", max_retries=0).complete_json(MESSAGES)


def test_unreachable_server_names_the_address():
    with pytest.raises(LLMError, match="127.0.0.1:9"):
        LLMClient("http://127.0.0.1:9/v1", "test-model", max_retries=0).complete_json(MESSAGES)


def test_settings_come_from_environment(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("LLM_MODEL", "qwen2.5:7b")
    monkeypatch.setenv("LLM_TEMPERATURE", "")
    monkeypatch.setenv("LLM_TIMEOUT", "300")
    monkeypatch.setenv("LLM_MAX_TOKENS", "4000")

    client = LLMClient.from_env()

    assert (client.base_url, client.model, client.temperature, client.timeout, client.max_tokens) == (
        "http://localhost:11434/v1", "qwen2.5:7b", None, 300.0, 4000,
    )


def test_model_must_be_configured(monkeypatch):
    monkeypatch.delenv("LLM_MODEL", raising=False)
    with pytest.raises(LLMError, match="LLM_MODEL"):
        LLMClient.from_env()


def test_non_numeric_setting_is_explained(monkeypatch):
    monkeypatch.setenv("LLM_MODEL", "qwen2.5:7b")
    monkeypatch.setenv("LLM_TEMPERATURE", "низкая")
    with pytest.raises(LLMError, match="LLM_TEMPERATURE"):
        LLMClient.from_env()
