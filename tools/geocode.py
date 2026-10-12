"""
Geocoding for the Dex map — turns a company's HQ into a pin.

Nominatim (OpenStreetMap) rather than a keyed provider: it is free, needs no
key, and the volume is tiny — one lookup per scanned company, cached forever in
Mongo. Its usage policy is what shapes this module:

  * at most one request per second, across the whole process
  * a User-Agent that identifies the application
  * results cached rather than re-requested

https://operations.osmfoundation.org/policies/nominatim/

The extractor supplies `hq_address` when a source states one and `hq_location`
("Bengaluru, Karnataka, India") otherwise. An address pins the building; a city
pins the city centre. The pin records which, so the map never claims more
precision than it has.
"""
import asyncio
import time
from datetime import datetime, timezone

import httpx
from loguru import logger

from config.settings import settings
from tools.mongo_client import db

# Nominatim allows one request per second; keep a little headroom.
MIN_INTERVAL_S = 1.1

# What the extractor writes when it doesn't know. Geocoding "Unknown" returns a
# real place somewhere, which would put a confident pin on the wrong continent.
UNKNOWN = {"", "unknown", "n/a", "na", "none", "null", "remote", "global", "worldwide", "stealth"}

# Nominatim `addresstype` → how precise the pin is.
_PRECISION = {
    "country": "country",
    "state": "region",
    "region": "region",
    "province": "region",
    "county": "region",
    "state_district": "region",
    "city": "city",
    "town": "city",
    "village": "city",
    "municipality": "city",
    "hamlet": "city",
    "city_district": "area",
    "borough": "area",
    "suburb": "area",
    "quarter": "area",
    "neighbourhood": "area",
    "postcode": "area",
}

_lock = asyncio.Lock()
_last_call = 0.0


class GeocoderUnavailable(Exception):
    """The lookup could not be made (network, 5xx, rate limit) — retry later.

    Distinct from "no such place": that answer is cached, this one must not be,
    or one flaky minute would leave a company unpinned forever.
    """


def _key(query: str) -> str:
    return " ".join(query.lower().split())


def is_usable(query) -> bool:
    return isinstance(query, str) and len(query.strip()) >= 2 and _key(query) not in UNKNOWN


def precision_of(kind: str | None) -> str:
    """Anything finer than a neighbourhood (a building, a road) is an address."""
    return _PRECISION.get((kind or "").lower(), "address")


async def _fetch(query: str) -> dict | None:
    """One Nominatim lookup, paced process-wide."""
    global _last_call
    async with _lock:
        wait = MIN_INTERVAL_S - (time.monotonic() - _last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        try:
            async with httpx.AsyncClient(timeout=settings.geocoder_timeout_s) as client:
                r = await client.get(
                    settings.geocoder_url,
                    params={"q": query, "format": "jsonv2", "limit": 1},
                    headers={
                        "User-Agent": settings.geocoder_user_agent,
                        "Accept-Language": "en",
                    },
                )
                r.raise_for_status()
                hits = r.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise GeocoderUnavailable(str(exc)) from exc
        finally:
            _last_call = time.monotonic()

    if not isinstance(hits, list) or not hits:
        return None
    h = hits[0]
    try:
        lat, lng = float(h["lat"]), float(h["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    return {
        "lat": lat,
        "lng": lng,
        "label": h.get("display_name") or "",
        "kind": h.get("addresstype") or h.get("type") or "",
    }


async def geocode(query: str) -> dict | None:
    """Cached lookup. None means "no such place"; raises GeocoderUnavailable on
    a transient failure."""
    if not settings.geocoding_enabled or not is_usable(query):
        return None

    key = _key(query)
    try:
        cached = await db.geocache.find_one({"_id": key})
    except Exception as exc:
        logger.warning(f"Geocode cache read failed: {exc}")
        cached = None
    if cached is not None:
        return cached.get("hit")

    hit = await _fetch(query)
    try:
        await db.geocache.update_one(
            {"_id": key},
            {"$set": {"hit": hit, "at": datetime.now(timezone.utc)}},
            upsert=True,
        )
    except Exception as exc:
        logger.warning(f"Geocode cache write failed: {exc}")

    logger.info(f"Geocoded '{query}' -> {'no match' if hit is None else (hit['lat'], hit['lng'])}")
    return hit


async def locate(meta: dict) -> dict | None:
    """Pin a company from its extracted metadata: address first, then city.

    Returns {"lat", "lng", "precision", "query", "label"} or None when neither
    field resolves. Raises GeocoderUnavailable if the service can't be reached.
    """
    for field in ("hq_address", "hq_location"):
        query = meta.get(field)
        if not is_usable(query):
            continue
        hit = await geocode(query)
        if hit:
            return {
                "lat": hit["lat"],
                "lng": hit["lng"],
                "precision": precision_of(hit.get("kind")),
                "query": query,
                "label": hit.get("label", ""),
            }
    return None


def geo_update(geo: dict | None) -> dict:
    """The fields a deal stores once a lookup has been answered (hit or miss)."""
    return {"geo": geo, "geo_checked_at": datetime.now(timezone.utc)}


async def backfill(limit: int = 500) -> int:
    """Pin deals that were scanned before the map existed. Returns pins added.

    Stops at the first transient failure rather than marking the rest as
    checked — they will be retried on the next start.
    """
    if not settings.geocoding_enabled:
        return 0

    pending = await db.deals.find(
        {"geo_checked_at": {"$exists": False}}, {"metadata": 1, "company_name": 1}
    ).to_list(limit)
    if not pending:
        return 0

    logger.info(f"Geocoding {len(pending)} deal(s) for the map…")
    pinned = 0
    for deal in pending:
        try:
            geo = await locate(deal.get("metadata") or {})
        except GeocoderUnavailable as exc:
            logger.warning(f"Geocoder unavailable ({exc}); will retry on next start.")
            break
        await db.deals.update_one({"_id": deal["_id"]}, {"$set": geo_update(geo)})
        pinned += geo is not None
    logger.info(f"Map backfill: pinned {pinned} of {len(pending)} deal(s).")
    return pinned


async def backfill_quietly() -> None:
    """Startup task wrapper: a missing Mongo or network must never crash the app."""
    try:
        await backfill()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        logger.warning(f"Map backfill skipped: {exc}")
