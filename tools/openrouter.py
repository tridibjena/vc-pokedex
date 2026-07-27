"""
OpenRouter provider (OpenAI-compatible chat completions).

The primary generation provider. Its free tier is both larger and
longer-context than Gemini's (which caps at 20 requests/day *per model*), so
Gemini now sits behind it in the chain as a backstop.

Free-tier limits (verified): 20 requests/minute, 50 requests/day — rising to
1,000/day once any credits have been purchased.

Deliberately plain httpx rather than the `openai` SDK: the surface we need is one
endpoint, and httpx is already a dependency.

Embeddings stay on Gemini — the comps corpus is indexed with
gemini-embedding-001 at 3072 dims, and changing provider would mean re-embedding
all of it for no benefit.
"""
import json
from typing import AsyncIterator

import httpx
from loguru import logger

from config.settings import settings

BASE_URL = "https://openrouter.ai/api/v1/chat/completions"


def is_configured() -> bool:
    return bool(settings.openrouter_api_key)


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        # OpenRouter uses these for attribution on their leaderboard; harmless.
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "VC Pokedex",
    }


def _payload(
    model: str,
    prompt: str,
    system: str,
    json_mode: bool,
    stream: bool,
    reasoning: bool = True,
) -> dict:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    body: dict = {"model": model, "messages": messages}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if stream:
        body["stream"] = True

    # Reasoning models (nemotron, gpt-oss, ...) stream their chain-of-thought in
    # `delta.reasoning` and leave `delta.content` empty until the very end. For
    # background analysis that is fine and improves quality. For interactive
    # chat it means the UI sits dead for the whole reasoning phase, so callers
    # turn it off there.
    if not reasoning:
        body["reasoning"] = {"enabled": False}
    return body


def _extract(data: dict) -> str:
    """Pull the assistant text out of an OpenAI-shaped response."""
    choices = data.get("choices") or []
    if not choices:
        # OpenRouter reports upstream provider failures in-band with a 200.
        err = data.get("error")
        if err:
            raise RuntimeError(f"OpenRouter error: {err}")
        return ""
    return (choices[0].get("message") or {}).get("content") or ""


def generate(model: str, prompt: str, system: str = "", json_mode: bool = False) -> str:
    """Synchronous completion."""
    if not is_configured():
        raise RuntimeError("OPENROUTER_API_KEY is not set.")

    r = httpx.post(
        BASE_URL,
        headers=_headers(),
        json=_payload(model, prompt, system, json_mode, stream=False),
        timeout=settings.openrouter_timeout_s,
    )
    r.raise_for_status()
    return _extract(r.json())


async def agenerate(model: str, prompt: str, system: str = "", json_mode: bool = False) -> str:
    """Async completion."""
    if not is_configured():
        raise RuntimeError("OPENROUTER_API_KEY is not set.")

    async with httpx.AsyncClient(timeout=settings.openrouter_timeout_s) as client:
        r = await client.post(
            BASE_URL,
            headers=_headers(),
            json=_payload(model, prompt, system, json_mode, stream=False),
        )
        r.raise_for_status()
        return _extract(r.json())


async def stream(model: str, prompt: str, system: str = "") -> AsyncIterator[str]:
    """Async generator of text deltas, for SSE chat.

    Reasoning is disabled: a reasoning model would emit nothing to `content`
    until it finished thinking, leaving the chat panel frozen.
    """
    if not is_configured():
        raise RuntimeError("OPENROUTER_API_KEY is not set.")

    async with httpx.AsyncClient(timeout=settings.openrouter_timeout_s) as client:
        async with client.stream(
            "POST",
            BASE_URL,
            headers=_headers(),
            json=_payload(model, prompt, system, json_mode=False, stream=True,
                          reasoning=False),
        ) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    delta = (json.loads(payload).get("choices") or [{}])[0].get("delta") or {}
                except json.JSONDecodeError:
                    # OpenRouter emits ": OPENROUTER PROCESSING" keepalive comments.
                    continue
                chunk = delta.get("content")
                if chunk:
                    yield chunk


def is_quota_error(exc: Exception) -> bool:
    """429, or the 402 OpenRouter returns when a free-tier daily cap is hit."""
    if isinstance(exc, httpx.HTTPStatusError):
        if exc.response.status_code in (402, 429):
            return True
    s = str(exc)
    return "429" in s or "402" in s or "rate limit" in s.lower()


def log_config() -> None:
    if is_configured():
        logger.info("OpenRouter provider configured.")
    else:
        logger.info("OpenRouter provider not configured (OPENROUTER_API_KEY unset).")
