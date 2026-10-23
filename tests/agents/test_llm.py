import socket

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
    import io
    import urllib.error
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
