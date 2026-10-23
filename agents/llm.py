"""LLM backends with structured JSON output: Claude (Anthropic API) or a local Ollama model.

Chosen by AEROMIND_LLM = anthropic | ollama | none. Unset: Claude when ANTHROPIC_API_KEY is set,
otherwise Ollama when its server answers, otherwise none (every agent then uses its rule-based
fallback). Each backend returns a validated instance of the requested Pydantic model or raises
LLMError.
"""
import http.client
import json
import os
import time
import urllib.error
import urllib.request

from pydantic import BaseModel, ValidationError

CLAUDE_MODEL = os.environ.get("AEROMIND_CLAUDE_MODEL", "claude-opus-5-5")
OLLAMA_URL = os.environ.get("AEROMIND_OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("AEROMIND_OLLAMA_MODEL", "qwen2.5:3b")
MAX_OUTPUT_TOKENS = 4000
OLLAMA_TIMEOUT_S = 120
#: A small local model can loop while writing JSON; capping the reply makes that a quick, retried
#: invalid answer instead of a two-minute timeout. Every agent's answer fits well within this.
MAX_LOCAL_TOKENS = 1500
LENGTH_KEYS = ("maxLength", "minLength")


def without_lengths(schema):
    """The schema without string length limits: llama.cpp compiles them into a grammar repetition so slow
    that generation stalls. Pydantic still enforces them on the reply, which is then retried."""
    if isinstance(schema, dict):
        return {k: without_lengths(v) for k, v in schema.items() if k not in LENGTH_KEYS}
    if isinstance(schema, list):
        return [without_lengths(v) for v in schema]
    return schema
#: After a connection failure or timeout, skip the backend this long: a dead server should cost one
#: timeout, not one per agent per flight (a laptop resumed from suspend left Ollama's GPU unusable).
BREAKER_S = 300
OLLAMA_PING_S = 2


class LLMError(RuntimeError):
    pass


class ClaudeBackend:
    name = "claude"

    def __init__(self, model: str = CLAUDE_MODEL):
        import anthropic
        self.anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.model = model

    def complete(self, system: str, user: str, output: type[BaseModel]) -> BaseModel:
        try:
            response = self.client.messages.parse(model=self.model, max_tokens=MAX_OUTPUT_TOKENS, system=system,
                                                  messages=[{"role": "user", "content": user}], output_format=output)
        except self.anthropic.APIConnectionError as error:
            raise LLMError(f"Claude unreachable: {error}") from error
        except self.anthropic.APIStatusError as error:
            raise LLMError(f"Claude API error {error.status_code}: {error.message}") from error
        except self.anthropic.APIError as error:
            raise LLMError(f"Claude API error: {error}") from error
        if response.stop_reason == "refusal":
            raise LLMError("Claude declined the request")
        if response.parsed_output is None:
            raise LLMError(f"no structured output (stop reason {response.stop_reason})")
        return response.parsed_output


class OllamaBackend:
    name = "ollama"

    def __init__(self, model: str = OLLAMA_MODEL, url: str = OLLAMA_URL):
        self.model = model
        self.url = url.rstrip("/")
        self.down_until = 0.0

    def _post(self, path: str, body: dict, timeout: float) -> dict:
        if time.monotonic() < self.down_until:
            raise LLMError(f"Ollama at {self.url} failed recently; using the rules until it recovers")
        request = urllib.request.Request(f"{self.url}{path}", data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            # the server answered: one failed request, retried by the caller; the server is not down
            raise LLMError(f"Ollama at {self.url} returned HTTP {error.code}") from error
        except (OSError, http.client.HTTPException) as error:
            self.down_until = time.monotonic() + BREAKER_S
            raise LLMError(f"Ollama at {self.url} failed: {error}") from error
        except ValueError as error:
            raise LLMError(f"Ollama at {self.url} returned invalid JSON: {error}") from error

    def complete(self, system: str, user: str, output: type[BaseModel]) -> BaseModel:
        body = {"model": self.model, "stream": False, "format": without_lengths(output.model_json_schema()),
                "options": {"temperature": 0, "num_predict": MAX_LOCAL_TOKENS},
                "keep_alive": "10m",
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        reply = self._post("/api/chat", body, OLLAMA_TIMEOUT_S)
        content = reply.get("message", {}).get("content", "")
        try:
            return output.model_validate_json(content)
        except ValidationError as error:
            raise LLMError(f"invalid JSON from {self.model}: {error.errors()[:3]}") from error

    def available(self) -> bool:
        try:
            tags = self._post_get("/api/tags")
        except LLMError:
            return False
        return any(m.get("name") == self.model for m in tags.get("models", []))

    def _post_get(self, path: str) -> dict:
        try:
            with urllib.request.urlopen(f"{self.url}{path}", timeout=OLLAMA_PING_S) as response:
                return json.load(response)
        except (OSError, http.client.HTTPException, ValueError) as error:
            raise LLMError(str(error)) from error


def get_backend():
    """The configured backend, or None for rule-based fallbacks only."""
    choice = os.environ.get("AEROMIND_LLM", "").strip().lower()
    if choice == "none":
        return None
    if choice == "anthropic" or (not choice and os.environ.get("ANTHROPIC_API_KEY")):
        return ClaudeBackend()
    ollama = OllamaBackend()
    if choice == "ollama" or ollama.available():
        return ollama
    return None


def timed(call):
    started = time.monotonic()
    result = call()
    return result, round(time.monotonic() - started, 2)
