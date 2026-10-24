import io
import json
import socket
import urllib.error

import pytest

from agents import llm
from agents.schemas import Plan


def closed_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_unreachable_ollama_raises_and_then_fails_fast(monkeypatch):
    backend = llm.OllamaBackend(url=f"http://127.0.0.1:{closed_port()}")
    with pytest.raises(llm.LLMError, match="failed"):
        backend.complete("s", "u", Plan)
    calls = []
    monkeypatch.setattr(llm.urllib.request, "urlopen", lambda *a, **k: calls.append(a))
    with pytest.raises(llm.LLMError, match="recently"):
        backend.complete("s", "u", Plan)
    assert calls == []


def test_backend_choice(monkeypatch):
    monkeypatch.setenv("AEROMIND_LLM", "none")
    assert llm.get_backend() is None
    monkeypatch.setenv("AEROMIND_LLM", "ollama")
    assert isinstance(llm.get_backend(), llm.OllamaBackend)


def test_an_http_error_does_not_open_the_breaker(monkeypatch):
    backend = llm.OllamaBackend(url="http://127.0.0.1:1")

    def fail(*_, **__):
        raise urllib.error.HTTPError("http://x", 500, "Internal Server Error", {}, io.BytesIO(b""))

    monkeypatch.setattr(llm.urllib.request, "urlopen", fail)
    with pytest.raises(llm.LLMError, match="HTTP 500"):
        backend.complete("s", "u", Plan)
    assert backend.down_until == 0.0


def test_length_limits_are_not_sent_to_the_local_model():
    from agents.schemas import FlightSummaryOut
    schema = llm.without_lengths(FlightSummaryOut.model_json_schema())
    assert "maxLength" not in str(schema) and "summary" in schema["properties"]


class Reply:
    """A urlopen() result holding a JSON body."""
    def __init__(self, body: dict):
        self.data = json.dumps(body).encode()

    def __enter__(self):
        return io.BytesIO(self.data)

    def __exit__(self, *_):
        return False


def groq_answer(output: dict) -> Reply:
    return Reply({"choices": [{"message": {"content": json.dumps(output)}}]})


PLAN = {"plan": [{"agent": "flight_summary", "reason": "always first"}]}


def test_groq_is_chosen_when_only_its_key_is_set(monkeypatch):
    monkeypatch.delenv("AEROMIND_LLM", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    assert isinstance(llm.get_backend(), llm.GroqBackend)


def test_groq_sends_the_schema_and_key_and_validates_the_reply(monkeypatch):
    sent = []

    def answer(request, timeout):
        sent.append(request)
        return groq_answer(PLAN)

    monkeypatch.setattr(llm.urllib.request, "urlopen", answer)
    result = llm.GroqBackend(api_key="gsk_test").complete("system", "user", Plan)
    body = json.loads(sent[0].data)
    assert result.plan[0].agent == "flight_summary"
    assert sent[0].get_header("Authorization") == "Bearer gsk_test"
    assert body["response_format"]["type"] == "json_schema"
    assert "maxLength" not in json.dumps(body["response_format"])


def test_groq_waits_and_retries_when_rate_limited(monkeypatch):
    replies = [urllib.error.HTTPError("http://x", 429, "Too Many Requests", {"retry-after": "3"}, io.BytesIO(b"")),
               groq_answer(PLAN)]
    waits = []

    def answer(*_, **__):
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(llm.urllib.request, "urlopen", answer)
    monkeypatch.setattr(llm.time, "sleep", waits.append)
    assert llm.GroqBackend(api_key="gsk_test").complete("s", "u", Plan).plan
    assert waits == [3.0]


def test_groq_without_a_key_fails_without_calling_out(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    calls = []
    monkeypatch.setattr(llm.urllib.request, "urlopen", lambda *a, **k: calls.append(a))
    with pytest.raises(llm.LLMError, match="GROQ_API_KEY"):
        llm.GroqBackend().complete("s", "u", Plan)
    assert calls == []
