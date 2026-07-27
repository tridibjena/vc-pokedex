"""
Firm watch — recent investments by the world's largest venture funds.

One Tavily sweep per firm plus a single structured-extraction call, cached in
process. The cache is not optional: this is rendered on a tab load, and a
refresh costs ten searches plus an LLM call, which on a free tier is most of a
day's budget.
"""
import asyncio
import time

from loguru import logger

from tools.calculator import parse_number
from tools.llm_client import agenerate, parse_json
from tools.web_search import as_context, asearch_many

CACHE_TTL_S = 60 * 60 * 6  # 6 hours

# Ten of the most active global venture firms. Ordering is presentational only.
TOP_FIRMS = [
    "Sequoia Capital",
    "Andreessen Horowitz",
    "Accel",
    "Index Ventures",
    "Lightspeed Venture Partners",
    "Benchmark",
    "Greylock Partners",
    "Kleiner Perkins",
    "Founders Fund",
    "Thrive Capital",
]

SYSTEM = """You extract venture capital investments into strict JSON.
Only report deals you can actually see in the provided sources, and only ones
where the named firm participated. Never invent a company, an amount, or a firm.
Return ONLY valid JSON."""

PROMPT = """From these news search results, extract recent investments made by
the venture firm "{firm}".

{context}

Return JSON with one key "deals", a list of up to 5 objects, each with:
- company: string (the startup that raised)
- round: string like "Seed", "Series A", "Series B" or null
- amount_usd: number in USD (e.g. 15000000) or null
- valuation_usd: number in USD or null
- sector: short string like "AI", "FinTech", "Biotech" or null
- lead: true if {firm} led the round, false if it merely participated, null if unclear
- date: string like "2026-05" or null
- url: the source URL this came from

Order most recent first. Omit anything that is not a venture investment by this
firm. If the sources show none, return an empty list."""

_cache: dict = {"at": 0.0, "data": []}
_lock = asyncio.Lock()


def _clean_deals(raw: list) -> list[dict]:
    out = []
    for d in raw or []:
        if not isinstance(d, dict):
            continue
        company = (d.get("company") or "").strip()
        if not company:
            continue
        lead = d.get("lead")
        out.append(
            {
                "company": company,
                "round": (d.get("round") or "").strip() or None,
                "amount_usd": parse_number(d.get("amount_usd")),
                "valuation_usd": parse_number(d.get("valuation_usd")),
                "sector": (d.get("sector") or "").strip() or None,
                "lead": lead if isinstance(lead, bool) else None,
                "date": (d.get("date") or "").strip() or None,
                "url": (d.get("url") or "").strip() or None,
            }
        )
    return out[:5]


async def _fetch_firm(firm: str) -> dict:
    """Research one firm's recent deals. Never raises — a failure is a firm with
    no deals, not a broken page."""
    try:
        results = await asearch_many(
            [
                f"{firm} led investment round startup",
                f"{firm} portfolio new investment announced",
            ],
            5,
            topic="news",
            days=90,
        )
        if not results:
            return {"firm": firm, "deals": [], "sources": 0}

        raw = await agenerate(
            PROMPT.format(firm=firm, context=as_context(results, max_chars=12000)),
            system=SYSTEM,
            json_mode=True,
        )
        parsed = parse_json(raw, default={}) or {}
        deals = _clean_deals(parsed.get("deals", []))
        logger.info(f"Firm watch: {firm} -> {len(deals)} deal(s)")
        return {"firm": firm, "deals": deals, "sources": len(results)}
    except Exception as exc:
        logger.error(f"Firm watch failed for {firm}: {exc}")
        return {"firm": firm, "deals": [], "sources": 0, "error": str(exc)}


async def _fetch_all() -> list[dict]:
    # Firms are independent, so research them concurrently. The generation
    # limiter still paces the LLM leg underneath.
    return list(await asyncio.gather(*(_fetch_firm(f) for f in TOP_FIRMS)))


async def get_firms(force: bool = False) -> dict:
    """Cached firm watch. Refreshes only when stale or forced."""
    now = time.monotonic()
    fresh = _cache["data"] and now - _cache["at"] < CACHE_TTL_S
    if fresh and not force:
        return {"firms": _cache["data"], "cached": True, "age_s": int(now - _cache["at"])}

    async with _lock:
        now = time.monotonic()
        if _cache["data"] and now - _cache["at"] < CACHE_TTL_S and not force:
            return {"firms": _cache["data"], "cached": True, "age_s": int(now - _cache["at"])}

        data = await _fetch_all()
        if any(f["deals"] for f in data):
            _cache["data"] = data
            _cache["at"] = time.monotonic()
        # Serve the last good payload rather than blanking the tab on a bad run.
        return {
            "firms": data if any(f["deals"] for f in data) else (_cache["data"] or data),
            "cached": False,
            "age_s": 0,
        }
