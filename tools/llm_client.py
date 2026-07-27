"""
Gemini client wrapper (google-genai SDK).

Model IDs are pinned exactly — never use `latest` aliases, Google hot-swaps them.
The SDK client is created lazily so that importing this module (e.g. during tests)
does not require an API key to be present.
"""
import asyncio
import collections
import json
import os
import re
import threading
import time
from typing import Any

from google import genai
from google.genai import types
from loguru import logger

from config.settings import settings
from tools import openrouter

# Pinned exactly — never a `latest` alias, providers hot-swap those. Note
# Gemini's 2.5 generation is retired for keys created after its deprecation, so
# any Gemini leg must name a currently-served model.
#
# Used when every configured leg is unusable (e.g. OpenRouter is primary but has
# no key and the fallback list names only OpenRouter models).
LAST_RESORT_MODEL = "gemini-3.6-flash"

PRIMARY = settings.primary_model or LAST_RESORT_MODEL
EMBED = settings.gemini_embed_model or "gemini-embedding-001"

_client: genai.Client | None = None


class _RateLimiter:
    """Sliding-window limiter over a rolling 60s window.

    The Gemini free tier meters embeddings per input item, not per batched call,
    so a single 200-chunk document blows the 100/min cap and the SDK's internal
    retries exhaust before the window clears. Pace the items instead.
    """

    def __init__(self, per_minute: int):
        # 0 or negative disables pacing entirely — used on paid plans, and by the
        # test suite, which fakes the SDK and must not actually sleep.
        self.per_minute = per_minute
        self._events: collections.deque[float] = collections.deque()
        self._lock = threading.Lock()

    def acquire(self, count: int) -> None:
        if self.per_minute <= 0:
            return
        while True:
            with self._lock:
                now = time.monotonic()
                while self._events and now - self._events[0] >= 60.0:
                    self._events.popleft()

                if len(self._events) + count <= self.per_minute or not self._events:
                    self._events.extend([now] * count)
                    return

                sleep_for = 60.0 - (now - self._events[0]) + 0.05

            logger.info(f"Rate limit reached; pausing {sleep_for:.1f}s")
            time.sleep(max(0.1, sleep_for))


_embed_limiter = _RateLimiter(settings.embed_items_per_minute)
_generate_limiter = _RateLimiter(settings.generate_requests_per_minute)


def _api_key() -> str:
    return settings.gemini_api_key or os.environ.get("GEMINI_API_KEY", "")


def get_client() -> genai.Client:
    """Return a cached genai.Client, creating it on first use."""
    global _client
    if _client is None:
        key = _api_key()
        if not key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Add it to .env or the environment "
                "before calling the Gemini API."
            )
        _client = genai.Client(api_key=key)
        logger.info(f"Initialized Gemini client (embed={EMBED})")
    return _client


def is_configured() -> bool:
    """True if an API key is available. Does not make a network call."""
    return bool(_api_key())


# ── Generation ────────────────────────────────────────────────────────────────

PROVIDER_SEP = ":"


def split_model(entry: str) -> tuple[str, str]:
    """Split a chain entry into (provider, model).

    Model ids themselves contain colons — "openrouter/free" is fine but
    "nvidia/nemotron-3-super-120b-a12b:free" is not — so split only once.
    """
    if entry.startswith("openrouter" + PROVIDER_SEP):
        return "openrouter", entry.split(PROVIDER_SEP, 1)[1]
    return "gemini", entry


def usable_chain() -> list[str]:
    """The model chain with unusable legs dropped.

    An OpenRouter leg with no API key would raise on every call and burn the
    failover, so filter it out rather than discovering it at request time.
    """
    chain = []
    for entry in settings.model_chain:
        provider, _ = split_model(entry)
        if provider == "openrouter" and not openrouter.is_configured():
            continue
        chain.append(entry)
    if chain:
        return chain
    # Everything was filtered out — fall back to a model that needs no extra key.
    logger.warning(
        f"No usable model in the chain (is OPENROUTER_API_KEY set?); "
        f"falling back to {LAST_RESORT_MODEL}."
    )
    return [LAST_RESORT_MODEL]


def _is_quota_error(exc: Exception) -> bool:
    """True for a spent quota on either provider."""
    if openrouter.is_quota_error(exc):
        return True
    s = str(exc)
    return "429" in s or "RESOURCE_EXHAUSTED" in s


def generate(prompt: str, system: str = "", json_mode: bool = False) -> str:
    """Synchronous generation. Blocking — use `agenerate` from async code."""
    cfg = types.GenerateContentConfig(
        system_instruction=system or None,
        response_mime_type="application/json" if json_mode else None,
    )
    chain = usable_chain()
    last: Exception | None = None

    for i, entry in enumerate(chain):
        provider, model = split_model(entry)
        # Only Gemini needs local pacing; OpenRouter's own limits are far looser.
        if provider == "gemini":
            _generate_limiter.acquire(1)
        logger.info(f"Generating with {entry} (json_mode={json_mode})")
        try:
            if provider == "openrouter":
                return openrouter.generate(model, prompt, system, json_mode)
            r = get_client().models.generate_content(model=model, contents=prompt, config=cfg)
            return r.text or ""
        except Exception as exc:
            last = exc
            if not _is_quota_error(exc) or i == len(chain) - 1:
                raise
            logger.warning(f"{entry} quota exhausted; failing over to {chain[i + 1]}")

    raise last if last else RuntimeError("no model available")


async def agenerate(prompt: str, system: str = "", json_mode: bool = False) -> str:
    """Async generation. Keeps the event loop free during the API round-trip."""
    cfg = types.GenerateContentConfig(
        system_instruction=system or None,
        response_mime_type="application/json" if json_mode else None,
    )
    chain = usable_chain()
    last: Exception | None = None

    for i, entry in enumerate(chain):
        provider, model = split_model(entry)
        if provider == "gemini":
            # Blocking sleep inside the limiter would stall the event loop, so
            # wait in a worker thread. Nodes run concurrently, sharing one budget.
            await asyncio.to_thread(_generate_limiter.acquire, 1)
        logger.info(f"Generating (async) with {entry} (json_mode={json_mode})")
        try:
            if provider == "openrouter":
                return await openrouter.agenerate(model, prompt, system, json_mode)
            r = await get_client().aio.models.generate_content(
                model=model, contents=prompt, config=cfg
            )
            return r.text or ""
        except Exception as exc:
            last = exc
            if not _is_quota_error(exc) or i == len(chain) - 1:
                raise
            logger.warning(f"{entry} quota exhausted; failing over to {chain[i + 1]}")

    raise last if last else RuntimeError("no model available")


async def stream(prompt: str, system: str = ""):
    """Async generator yielding response text chunks, for SSE.

    Fails over like `agenerate`, but only before the first token — once bytes
    have reached the client we cannot silently switch models mid-answer.
    """
    cfg = types.GenerateContentConfig(system_instruction=system or None)
    chain = usable_chain()
    last: Exception | None = None

    for i, entry in enumerate(chain):
        provider, model = split_model(entry)
        if provider == "gemini":
            await asyncio.to_thread(_generate_limiter.acquire, 1)
        logger.info(f"Streaming with {entry}")

        started = False
        try:
            if provider == "openrouter":
                async for chunk in openrouter.stream(model, prompt, system):
                    started = True
                    yield chunk
            else:
                async for chunk in await get_client().aio.models.generate_content_stream(
                    model=model, contents=prompt, config=cfg
                ):
                    if chunk.text:
                        started = True
                        yield chunk.text
            return
        except Exception as exc:
            last = exc
            if started or not _is_quota_error(exc) or i == len(chain) - 1:
                raise
            logger.warning(f"{entry} quota exhausted; failing over to {chain[i + 1]}")

    if last:
        raise last


# ── Embeddings ────────────────────────────────────────────────────────────────

def embed(texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    """
    Embed a list of texts, batching to respect the per-request input cap.

    Use task_type="RETRIEVAL_QUERY" when embedding a search query — Gemini's
    retrieval embeddings are asymmetric, and using the document task type for
    queries measurably degrades recall.
    """
    if not texts:
        return []

    client = get_client()
    cfg = types.EmbedContentConfig(task_type=task_type)
    vectors: list[list[float]] = []
    batch_size = max(1, settings.embed_batch_size)

    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        _embed_limiter.acquire(len(batch))
        logger.info(
            f"Embedding {len(batch)} text(s) with {EMBED} ({task_type}) "
            f"[{start + len(batch)}/{len(texts)}]"
        )
        r = client.models.embed_content(model=EMBED, contents=batch, config=cfg)
        for e in r.embeddings or []:
            if e.values is None:
                logger.error("Embedding response contained an entry with no values.")
                return []
            vectors.append(list(e.values))

    if len(vectors) != len(texts):
        logger.error(f"Embedding count mismatch: got {len(vectors)}, want {len(texts)}")
        return []

    return vectors


async def aembed(texts: list[str], task_type: str = "RETRIEVAL_DOCUMENT") -> list[list[float]]:
    """Async wrapper around `embed`, offloaded to a worker thread."""
    return await asyncio.to_thread(embed, texts, task_type)


# ── JSON response parsing ─────────────────────────────────────────────────────

_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*\n(.*?)\n?\s*```\s*$", re.DOTALL)


def parse_json(raw: str, default: Any = None) -> Any:
    """
    Parse a JSON response from the model, tolerating markdown code fences.

    Gemini occasionally wraps output in ```json ... ``` even with
    response_mime_type set, so strip fences before parsing. Returns `default`
    on failure rather than raising, so callers can fall back cleanly.
    """
    if not raw:
        return default

    text = raw.strip()
    m = _FENCE_RE.match(text)
    if m:
        text = m.group(1).strip()

    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.error(f"Failed to parse model JSON output: {exc}. Raw: {raw[:300]!r}")
        return default
