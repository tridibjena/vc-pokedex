"""
Web research agent — turns a bare company name into a document.

The rest of the pipeline is built around a text blob (a parsed pitch deck). This
agent produces the same shape from Tavily search results, so a name-only lookup
reuses the existing extraction → comps → risk → score → memo graph unchanged.
"""
import asyncio

from loguru import logger

from tools.web_search import as_context, asearch_many

# Distinct angles: one query rarely covers product, funding and people at once.
QUERY_TEMPLATES = [
    "{name} startup company overview what it does product",
    "{name} funding round raised valuation investors",
    "{name} founders CEO co-founder team background",
    "{name} revenue customers traction growth",
]

NEWS_TEMPLATE = "{name} startup news"


async def research_company(
    name: str, max_results: int = 5
) -> tuple[str, list[dict], list[dict]]:
    """Search the web for a company.

    Returns (context_text, all_results, news_results). The news pass is kept
    separate so the dex profile can show recent coverage without paying for a
    second sweep — it is already fetched here.
    """
    queries = [t.format(name=name) for t in QUERY_TEMPLATES]

    # The four general angles and the recency-biased news pass are independent,
    # so run every query concurrently rather than one sweep after the other.
    results, news = await asyncio.gather(
        asearch_many(queries, max_results),
        asearch_many([NEWS_TEMPLATE.format(name=name)], max_results, topic="news", days=180),
    )

    seen = {r["url"] for r in results if r.get("url")}
    merged = results + [r for r in news if r.get("url") and r["url"] not in seen]

    if not merged:
        logger.warning(f"No web results for '{name}'.")
        return "", [], []

    header = (
        f"Web research dossier for the company '{name}'. "
        f"The following are search results gathered from the public web.\n\n"
    )
    context = header + as_context(merged)
    logger.success(
        f"Research for '{name}': {len(merged)} sources "
        f"({len(news)} news), {len(context)} chars."
    )
    return context, merged, news


def sources_from(results: list[dict], limit: int = 12) -> list[dict]:
    """Trim search results down to citable sources for the UI."""
    return [
        {"title": r.get("title", ""), "url": r.get("url", ""), "published": r.get("published_date")}
        for r in results[:limit]
        if r.get("url")
    ]


def news_from(results: list[dict], limit: int = 8) -> list[dict]:
    """Trim the news pass into displayable items, newest-looking first."""
    items = [
        {
            "title": (r.get("title") or "").strip(),
            "url": r.get("url", ""),
            "published": r.get("published_date"),
            "snippet": (r.get("content") or "").strip()[:220],
        }
        for r in results
        if r.get("url") and r.get("title")
    ]
    items.sort(key=lambda i: i.get("published") or "", reverse=True)
    return items[:limit]
