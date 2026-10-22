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
