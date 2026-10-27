"""Meterless Nightshift Runtime client: OpenAI-compatible, authenticated, bounded.

Verified against Nightshift 1.2.1 on the development machine:
    GET  {METERLESS_BASE_URL}/models            -> {"data": [{"id": "meterless/local", ...}, ...]}
    POST {METERLESS_BASE_URL}/chat/completions  -> OpenAI completion plus a "meterless" block
         carrying requested_model, routed_model, winning_route, receipt_id, receipt_envelope, usage.
    Authorization: Bearer <proxy token>; meterless-app: <stable app id>. Missing token -> 401.
A routing id such as `meterless/local` is not a model name: Nightshift picks the model, and the
receipt says which one answered. Nothing here fabricates a completion; every failure raises.
"""

import os
import random
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Protocol

import httpx

from app.integrations.zetaris import IntegrationNotConfigured


class MeterlessError(RuntimeError):
    """A configured Meterless call failed. Never a reason to invent model output."""


class MeterlessUnavailable(MeterlessError):
    """Runtime unreachable, timed out, not ready, or answered 5xx after bounded retries."""


class MeterlessAuthError(MeterlessError):
    """The proxy token was rejected (401/403)."""


class MeterlessResponseError(MeterlessError):
    """The Runtime refused the request or answered 200 with an unusable completion."""


@dataclass(frozen=True)
class Completion:
    text: str
    model_id: str
    receipt_id: str
    requested_model: str = ""
    provider: str = ""
    receipt_signed: bool = False
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int | None = None
    cross_check: str | None = None
    from_cache: bool = False


class InferenceProvider(Protocol):
    def chat(self, messages: Sequence[Mapping[str, str]], *, max_tokens: int = 512, temperature: float = 0.0) -> Completion:
        ...


@dataclass(frozen=True)
class MeterlessStatus:
    status: str = "not_configured"
    nightshift: str = "not_configured"
    engine: str = "not_configured"
    reason: str = "Set METERLESS_BASE_URL and METERLESS_API_TOKEN or METERLESS_TOKEN_FILE to enable Nightshift."


DEFAULT_MODEL = "meterless/local"
# Transient: worth a bounded retry. 503 includes Nightshift's "local runtime is not ready".
RETRY_STATUSES = frozenset({429, 502, 503, 504})


@dataclass(frozen=True)
class MeterlessConfig:
    base_url: str
    api_token: str = field(repr=False)
    model: str = DEFAULT_MODEL
    app: str = "sentry-ai"
    connect_timeout: float = 5.0
    read_timeout: float = 120.0
    max_retries: int = 2
    structured_output: bool = False
    fresh_inference: bool = False

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "MeterlessConfig":
        env = os.environ if environ is None else environ
        base_url = env.get("METERLESS_BASE_URL", "").strip()
        token = env.get("METERLESS_API_TOKEN", "").strip()
        token_file = env.get("METERLESS_TOKEN_FILE", "").strip()
        if not token and token_file:
            try:
                token = Path(token_file).read_text(encoding="utf-8").strip()
            except OSError as exc:
                raise IntegrationNotConfigured(f"METERLESS_TOKEN_FILE is not readable ({type(exc).__name__})") from exc
        missing = [name for name, value in (("METERLESS_BASE_URL", base_url),
                                            ("METERLESS_API_TOKEN or METERLESS_TOKEN_FILE", token)) if not value]
        if missing:
            raise IntegrationNotConfigured(f"Nightshift needs {', '.join(missing)}")
        return cls(
            base_url=base_url.rstrip("/"),
            api_token=token,
            model=env.get("METERLESS_MODEL", "").strip() or DEFAULT_MODEL,
            app=env.get("METERLESS_APP", "").strip() or "sentry-ai",
            connect_timeout=float(env.get("METERLESS_CONNECT_TIMEOUT_SECONDS") or 5),
            read_timeout=float(env.get("METERLESS_READ_TIMEOUT_SECONDS") or 120),
            max_retries=int(env.get("METERLESS_MAX_RETRIES") or 2),
        )


class NightshiftClient:
    """Chat completions through the Nightshift Runtime, never a direct model provider."""

    def __init__(
        self, config: MeterlessConfig, transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self._sleep = sleep
        self._http = httpx.Client(
            base_url=config.base_url,
            timeout=httpx.Timeout(config.read_timeout, connect=config.connect_timeout),
            transport=transport,
            headers={"Authorization": f"Bearer {config.api_token}", "meterless-app": config.app},
        )

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "NightshiftClient":
        return cls(MeterlessConfig.from_env(environ))

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "NightshiftClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def models(self) -> list[str]:
        payload = self._request("GET", "/models")
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            raise MeterlessResponseError("Unexpected /models response: expected data[]")
        return [item["id"] for item in data if isinstance(item, dict) and isinstance(item.get("id"), str)]

    def chat(self, messages: Sequence[Mapping[str, str]], *, max_tokens: int = 512, temperature: float = 0.0) -> Completion:
        body = {
            "model": self.config.model, "stream": False, "max_tokens": max_tokens,
            "temperature": temperature, "messages": [dict(message) for message in messages],
        }
        if self.config.structured_output:
            body["response_format"] = {"type": "json_object"}
        # A revised investigation must not reuse a semantically similar rejected draft.
        headers = {"meterless-scope": "sentry-" + uuid.uuid4().hex} if self.config.fresh_inference else None
        return parse_completion(self._request("POST", "/chat/completions", json=body, headers=headers), self.config.model)

    def _request(self, method: str, path: str, json: Any = None, headers: Any = None) -> Any:
        attempts = self.config.max_retries + 1
        for attempt in range(1, attempts + 1):
            try:
                response = self._http.request(method, path, json=json, headers=headers)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt == attempts:
                    raise MeterlessUnavailable(
                        f"Nightshift unreachable at {self.config.base_url} after {attempts} attempts ({type(exc).__name__})"
                    ) from exc
            else:
                if response.status_code in (401, 403):
                    raise MeterlessAuthError(f"Nightshift rejected the token (HTTP {response.status_code})")
                if response.status_code == 200:
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise MeterlessResponseError("Nightshift returned a non-JSON success response") from exc
                if response.status_code not in RETRY_STATUSES and response.status_code < 500:
                    raise MeterlessResponseError(
                        f"Nightshift rejected the request (HTTP {response.status_code}): {_message(response)}")
                if attempt == attempts:
                    raise MeterlessUnavailable(
                        f"Nightshift HTTP {response.status_code} after {attempts} attempts: {_message(response)}")
            self._sleep(min(4.0, 0.5 * 2 ** (attempt - 1)) + random.uniform(0, 0.25))
        raise AssertionError("unreachable")


def _message(response: httpx.Response) -> str:
    try:
        payload = response.json()
        error = payload.get("error") if isinstance(payload, dict) else None
        text = error.get("message") if isinstance(error, dict) else None
    except ValueError:
        text = None
    return (text or response.text).strip()[:300]


def parse_completion(payload: Any, requested_model: str) -> Completion:
    """Map an OpenAI-compatible body plus the Nightshift receipt block to a Completion."""
    try:
        text = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise MeterlessResponseError("Completion has no choices[0].message.content") from exc
    if not isinstance(text, str) or not text.strip():
        raise MeterlessResponseError("Completion content is empty")
    receipt = payload.get("meterless") if isinstance(payload.get("meterless"), dict) else {}
    route = receipt.get("winning_route") if isinstance(receipt.get("winning_route"), dict) else {}
    usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
    receipt_usage = receipt.get("usage") if isinstance(receipt.get("usage"), dict) else {}
    cross_check = payload.get("meterless_cross_check")
    return Completion(
        text=text,
        model_id=str(route.get("model") or receipt.get("routed_model") or payload.get("model") or ""),
        receipt_id=str(receipt.get("receipt_id") or ""),
        requested_model=str(receipt.get("requested_model") or requested_model),
        provider=str(route.get("provider") or ""),
        receipt_signed=bool(receipt.get("receipt_envelope")),
        from_cache=bool(receipt.get("from_cache")),
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
        latency_ms=receipt_usage.get("latency_ms") if isinstance(receipt_usage.get("latency_ms"), int) else None,
        cross_check=cross_check.get("status") if isinstance(cross_check, dict) else None,
    )


class MeterlessClient:
    """Status facade. Unconfigured, it reports `not_configured` and refuses to complete."""

    def __init__(self, config: MeterlessConfig | None = None, transport: httpx.BaseTransport | None = None) -> None:
        self._config = config
        self._transport = transport

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "MeterlessClient":
        return cls(MeterlessConfig.from_env(environ))

    def status(self) -> MeterlessStatus:
        if self._config is None:
            return MeterlessStatus()
        return MeterlessStatus(status="configured", nightshift="configured", reason=f"Nightshift at {self._config.base_url}")

    def complete(self, *, prompt: str, model_id: str) -> Completion:
        if self._config is None:
            raise IntegrationNotConfigured(self.status().reason)
        with NightshiftClient(replace(self._config, model=model_id or self._config.model), self._transport) as client:
            return client.chat([{"role": "user", "content": prompt}])
