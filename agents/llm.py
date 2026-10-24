"""LLM backends with structured JSON output: Claude (Anthropic API), Groq (free-tier API) or a local
Ollama model.

Chosen by AEROMIND_LLM = anthropic | groq | ollama | none. Unset: Claude when ANTHROPIC_API_KEY is set,
otherwise Groq when GROQ_API_KEY is set, otherwise Ollama when its server answers, otherwise none
(every agent then uses its rule-based fallback). Each backend returns a validated instance of the requested Pydantic model or raises
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
GROQ_URL = os.environ.get("AEROMIND_GROQ_URL", "https://api.groq.com/openai/v1")
#: a Groq model with JSON-schema output (console.groq.com/docs/structured-outputs)
GROQ_MODEL = os.environ.get("AEROMIND_GROQ_MODEL", "openai/gpt-oss-120b")
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
#: free-tier APIs answer HTTP 429 when a minute's quota is used up; wait as told (capped) and retry
RATE_LIMIT_RETRIES = 2
RATE_LIMIT_MAX_WAIT_S = 30.0
HTTP_TIMEOUT_S = 120


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


class HttpBackend:
    """A JSON-over-HTTP backend with a circuit breaker: a server that cannot be reached is skipped for
    BREAKER_S, while an HTTP error is one failed request that the caller retries."""
    name = "http"

    def __init__(self, model: str, url: str):
        self.model = model
        self.url = url.rstrip("/")
        self.down_until = 0.0

    def _post(self, path: str, body: dict, timeout: float, headers: dict = None) -> dict:
        if time.monotonic() < self.down_until:
            raise LLMError(f"{self.name} at {self.url} failed recently; using the rules until it recovers")
        request = urllib.request.Request(f"{self.url}{path}", data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json", **(headers or {})})
        for attempt in range(RATE_LIMIT_RETRIES + 1):
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    return json.load(response)
            except urllib.error.HTTPError as error:
                if error.code == 429 and attempt < RATE_LIMIT_RETRIES:
                    time.sleep(retry_after(error))
                    continue
                raise LLMError(f"{self.name} at {self.url} returned HTTP {error.code}") from error
            except (OSError, http.client.HTTPException) as error:
                self.down_until = time.monotonic() + BREAKER_S
                raise LLMError(f"{self.name} at {self.url} failed: {error}") from error
            except ValueError as error:
                raise LLMError(f"{self.name} at {self.url} returned invalid JSON: {error}") from error
        raise LLMError(f"{self.name} at {self.url} is rate limited")

    def _parse(self, content: str, output: type[BaseModel]) -> BaseModel:
        try:
            return output.model_validate_json(content)
        except ValidationError as error:
            raise LLMError(f"invalid JSON from {self.model}: {error.errors()[:3]}") from error


def retry_after(error: urllib.error.HTTPError) -> float:
    """Seconds the server asked us to wait, within RATE_LIMIT_MAX_WAIT_S."""
    try:
        wait = float(error.headers.get("retry-after", 1))
    except (TypeError, ValueError):
        wait = 1.0
    return min(max(wait, 0.0), RATE_LIMIT_MAX_WAIT_S)


class GroqBackend(HttpBackend):
    """Groq's OpenAI-compatible chat API (free tier, key from console.groq.com)."""
    name = "groq"

    def __init__(self, model: str = GROQ_MODEL, url: str = GROQ_URL, api_key: str = None):
        super().__init__(model, url)
        self.api_key = api_key or os.environ.get("GROQ_API_KEY", "")

    def complete(self, system: str, user: str, output: type[BaseModel]) -> BaseModel:
        if not self.api_key:
            raise LLMError("GROQ_API_KEY is not set")
        schema = {"name": output.__name__, "strict": False, "schema": without_lengths(output.model_json_schema())}
        body = {"model": self.model, "temperature": 0, "max_completion_tokens": MAX_OUTPUT_TOKENS,
                "response_format": {"type": "json_schema", "json_schema": schema},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        reply = self._post("/chat/completions", body, HTTP_TIMEOUT_S, {"Authorization": f"Bearer {self.api_key}"})
        try:
            content = reply["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as error:
            raise LLMError(f"unexpected reply from {self.name}: {str(reply)[:200]}") from error
        return self._parse(content, output)


class OllamaBackend(HttpBackend):
    name = "ollama"

    def __init__(self, model: str = OLLAMA_MODEL, url: str = OLLAMA_URL):
        super().__init__(model, url)

    def complete(self, system: str, user: str, output: type[BaseModel]) -> BaseModel:
        body = {"model": self.model, "stream": False, "format": without_lengths(output.model_json_schema()),
                "options": {"temperature": 0, "num_predict": MAX_LOCAL_TOKENS},
                "keep_alive": "10m",
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        reply = self._post("/api/chat", body, OLLAMA_TIMEOUT_S)
        return self._parse(reply.get("message", {}).get("content", ""), output)

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
    if choice == "groq" or (not choice and os.environ.get("GROQ_API_KEY")):
        return GroqBackend()
    ollama = OllamaBackend()
    if choice == "ollama" or ollama.available():
        return ollama
    return None


def timed(call):
    started = time.monotonic()
    result = call()
    return result, round(time.monotonic() - started, 2)
