"""
Global funding ticker — recent notable startup raises worldwide.

Backed by a Tavily news sweep plus one structured-extraction call, cached in
process with a TTL. The cache matters: this is rendered on every dashboard load,
and re-running the sweep per request would burn both Tavily credits and the
free-tier Gemini quota within minutes.
"""
import asyncio
import time

from loguru import logger

from tools.calculator import parse_number
from tools.llm_client import agenerate, parse_json
from tools.web_search import as_context, search_many

CACHE_TTL_S = 60 * 60 * 3  # 3 hours

QUERIES = [
    "startup raises Series A funding round announced this week",
    "startup raises Series B Series C funding round valuation",
    "seed round funding announced startup million",
]

SYSTEM = """You extract startup funding announcements into strict JSON.
Only include rounds you can actually see in the provided sources.
Never invent a company, an amount or an investor. Return ONLY valid JSON."""

PROMPT = """From these news search results, extract the most recent and notable
startup funding rounds.

{context}

Return JSON with one key "raises", a list of up to 12 objects, each with:
- company: string
- amount_usd: number in USD (e.g. 15000000) or null
- round: string like "Seed", "Series A", "Series B" or null
- valuation_usd: number in USD or null
- sector: short string like "AI", "FinTech", "Biotech" or null
- country: short string or null
- url: the source URL this came from
- headline: a short phrase (max 8 words)

Order by how recent and notable they are. Omit anything that is not a startup
funding round. Omit entries where you cannot identify the company name."""

_cache: dict = {"at": 0.0, "data": []}
_lock = asyncio.Lock()


def _clean(raw: list) -> list[dict]:
    """Normalize and drop entries missing the essentials."""
    out = []
    for r in raw or []:
        if not isinstance(r, dict):
            continue
        company = (r.get("company") or "").strip()
        if not company:
            continue
        out.append(
            {
                "company": company,
                "amount_usd": parse_number(r.get("amount_usd")),
                "round": (r.get("round") or "").strip() or None,
                "valuation_usd": parse_number(r.get("valuation_usd")),
                "sector": (r.get("sector") or "").strip() or None,
                "country": (r.get("country") or "").strip() or None,
                "url": (r.get("url") or "").strip() or None,
                "headline": (r.get("headline") or "").strip() or None,
            }
        )
    return out[:12]


async def _fetch() -> list[dict]:
    results = await asyncio.to_thread(
        search_many, QUERIES, 6, topic="news", days=21
    )
    if not results:
        logger.warning("Ticker: no news results (Tavily unconfigured or empty).")
        return []

    try:
        raw = await agenerate(
            PROMPT.format(context=as_context(results, max_chars=16000)),
            system=SYSTEM,
            json_mode=True,
        )
        parsed = parse_json(raw, default={}) or {}
        raises = _clean(parsed.get("raises", []))
        logger.success(f"Ticker: extracted {len(raises)} raise(s).")
        return raises
    except Exception as exc:
        logger.error(f"Ticker extraction failed: {exc}")
        return []


async def get_ticker(force: bool = False) -> dict:
    """Return cached ticker entries, refreshing when stale."""
    now = time.monotonic()
    if not force and _cache["data"] and now - _cache["at"] < CACHE_TTL_S:
        return {"raises": _cache["data"], "cached": True, "age_s": int(now - _cache["at"])}

    async with _lock:
        # Another caller may have refreshed while we waited on the lock.
        now = time.monotonic()
        if not force and _cache["data"] and now - _cache["at"] < CACHE_TTL_S:
            return {"raises": _cache["data"], "cached": True, "age_s": int(now - _cache["at"])}

        data = await _fetch()
        if data:
            _cache["data"] = data
            _cache["at"] = time.monotonic()
        # On failure keep serving the last good payload rather than blanking the bar.
        return {"raises": data or _cache["data"], "cached": False, "age_s": 0}
