"""Replaceable LLM adapter.

The LLM is only ever asked for JSON matching a schema the application supplies,
and every result is validated by the caller before use. It is never asked to
score, rank, select questions or decide anything about the survey design.

Adapters:
  NullLLM       - no model; every caller falls back to deterministic behaviour.
  StubLLM       - canned responses for tests and demos.
  AnthropicLLM  - Claude via the official SDK, enabled only when credentials are
                  present in the environment.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Callable, Protocol

from .config import env_flag

log = logging.getLogger("dissdisc.llm")

DEFAULT_MODEL = "claude-opus-5-5"


class LLMAdapter(Protocol):
    name: str
    enabled: bool

    def complete_json(self, *, system: str, user: str, schema: dict[str, Any], max_tokens: int = 16000,
                      effort: str = "medium") -> dict[str, Any] | None:
        """Return parsed JSON, or None on any failure (caller must then fall back)."""
        ...


class NullLLM:
    name = "none"
    enabled = False

    def complete_json(self, **_: Any) -> dict[str, Any] | None:
        return None


class StubLLM:
    """Deterministic stand-in. `responder` receives (system, user, schema) and returns any object."""

    name = "stub"
    enabled = True

    def __init__(self, responder: Callable[[str, str, dict[str, Any]], Any]):
        self.responder = responder
        self.calls: list[dict[str, Any]] = []

    def complete_json(self, *, system: str, user: str, schema: dict[str, Any], max_tokens: int = 16000,
                      effort: str = "medium") -> dict[str, Any] | None:
        self.calls.append({"system": system, "user": user, "schema": schema})
        try:
            out = self.responder(system, user, schema)
        except Exception:
            return None
        if isinstance(out, str):
            try:
                out = json.loads(out)
            except json.JSONDecodeError:
                return None
        return out if isinstance(out, dict) else None


class AnthropicLLM:
    name = "anthropic"
    enabled = True

    def __init__(self, model: str | None = None, timeout: float = 90.0):
        import anthropic

        self._anthropic = anthropic
        # Credentials are resolved by the SDK from the environment; never passed in code.
        self.client = anthropic.Anthropic(timeout=timeout, max_retries=1)
        self.model = model or os.environ.get("DD_LLM_MODEL", DEFAULT_MODEL)

    def complete_json(self, *, system: str, user: str, schema: dict[str, Any], max_tokens: int = 16000,
                      effort: str = "medium") -> dict[str, Any] | None:
        a = self._anthropic
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            )
        except a.AuthenticationError:
            log.warning("LLM call failed: authentication error; using deterministic fallback")
            return None
        except a.RateLimitError:
            log.warning("LLM call failed: rate limited; using deterministic fallback")
            return None
        except a.BadRequestError as exc:
            log.warning("LLM call rejected (400: %s); using deterministic fallback", getattr(exc, "message", ""))
            return None
        except a.APIStatusError as exc:
            log.warning("LLM call failed (HTTP %s); using deterministic fallback", exc.status_code)
            return None
        except a.APIConnectionError:
            log.warning("LLM call failed: connection error; using deterministic fallback")
            return None
        # A refusal or truncated output is not usable JSON: fall back rather than guess.
        if response.stop_reason in ("refusal", "max_tokens"):
            log.warning("LLM stopped with %s; using deterministic fallback", response.stop_reason)
            return None
        text = next((b.text for b in response.content if b.type == "text"), None)
        if not text:
            return None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None


def credentials_present() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def get_llm() -> LLMAdapter:
    """Demo mode (NullLLM) unless credentials exist and the LLM is not disabled."""
    if env_flag("DD_DISABLE_LLM") or not credentials_present():
        return NullLLM()
    try:
        return AnthropicLLM()
    except Exception:  # SDK missing or misconfigured: the app must still run
        log.warning("Could not initialise the Anthropic client; running in demo mode")
        return NullLLM()
