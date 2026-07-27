"""
Tavily web search wrapper.

Degrades to an empty list when TAVILY_API_KEY is unset so the risk and research
agents stay runnable offline rather than raising.
"""
import asyncio
import os

from loguru import logger
from tavily import TavilyClient

from config.settings import settings

_client: TavilyClient | None = None


def _api_key() -> str:
    return settings.tavily_api_key or os.environ.get("TAVILY_API_KEY", "")


def is_configured() -> bool:
    return bool(_api_key())


def get_tavily_client() -> TavilyClient | None:
    global _client
    if _client is not None:
        return _client
    key = _api_key()
    if not key:
        return None
    try:
        _client = TavilyClient(api_key=key)
    except Exception as exc:
        logger.error(f"Error initializing TavilyClient: {exc}")
        return None
    return _client


def _normalize(raw: dict) -> list[dict]:
    return [
        {
            "title": x.get("title", ""),
            "url": x.get("url", ""),
            "content": x.get("content", ""),
            "score": x.get("score"),
            "published_date": x.get("published_date"),
        }
        for x in raw.get("results", [])
    ]


def search(
    query: str,
    max_results: int = 5,
    *,
    topic: str | None = None,
    days: int | None = None,
    search_depth: str | None = None,
) -> list[dict]:
    """Run one Tavily search. Returns [] when unconfigured or on failure."""
    client = get_tavily_client()
    if not client:
        logger.warning(f"Tavily search skipped (no API key): '{query}'")
        return []

    kwargs: dict = {"query": query, "max_results": max_results,
                    "timeout": settings.tavily_timeout_s}
    if topic:
        kwargs["topic"] = topic
    if days:
        kwargs["days"] = days
    if search_depth:
        kwargs["search_depth"] = search_depth

    logger.info(f"Tavily search: '{query}' (topic={topic or 'general'})")
    try:
        results = _normalize(client.search(**kwargs))
        logger.success(f"Tavily returned {len(results)} result(s).")
        return results
    except Exception as exc:
        logger.error(f"Tavily search failed for '{query}': {exc}")
        return []


def _merge(result_sets: list[list[dict]], n_queries: int) -> list[dict]:
    """Flatten result sets, de-duplicating by URL and preserving query order."""
    seen: set[str] = set()
    merged: list[dict] = []
    for results in result_sets:
        for r in results:
            url = r.get("url", "")
            if url and url in seen:
                continue
            if url:
                seen.add(url)
            merged.append(r)
    logger.info(f"search_many: {len(merged)} unique result(s) across {n_queries} queries.")
    return merged


def search_many(queries: list[str], max_results: int = 5, **kwargs) -> list[dict]:
    """Run several searches and merge, de-duplicating by URL.

    Company research needs several angles — product, funding, founders — and one
    query rarely covers all three. Synchronous variant, kept for callers already
    running in a worker thread.
    """
    return _merge([search(q, max_results=max_results, **kwargs) for q in queries], len(queries))


async def asearch_many(queries: list[str], max_results: int = 5, **kwargs) -> list[dict]:
    """Concurrent `search_many`.

    Tavily calls are pure network waits of ~1.5s each, so running them in
    sequence made a five-query dossier take ~8s for no reason. Fanning them out
    collapses that to roughly the slowest single call.
    """
    results = await asyncio.gather(
        *(asyncio.to_thread(search, q, max_results, **kwargs) for q in queries),
        return_exceptions=True,
    )
    clean: list[list[dict]] = []
    for q, r in zip(queries, results):
        if isinstance(r, BaseException):
            # One bad query must not sink the dossier.
            logger.error(f"Search failed for '{q}': {r}")
            continue
        clean.append(r)
    return _merge(clean, len(queries))


def as_context(results: list[dict], max_chars: int = 24000) -> str:
    """Flatten search results into a text blob for an LLM prompt."""
    parts = []
    used = 0
    for r in results:
        block = f"### {r.get('title', '')}\nURL: {r.get('url', '')}\n{r.get('content', '')}\n"
        if used + len(block) > max_chars:
            break
        parts.append(block)
        used += len(block)
    return "\n".join(parts)
