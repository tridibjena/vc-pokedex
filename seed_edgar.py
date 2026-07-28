"""
Seed the comparable-deals corpus from real SEC EDGAR Form D filings.

    python seed_edgar.py                    # 2 most recent quarters, 200 comps
    python seed_edgar.py --quarters 4 --limit 400
    python seed_edgar.py --dry-run          # parse and print, no embedding calls

Form D is the notice filed for a Regulation D exempt offering — effectively
every US private round — so this gives real issuers, sectors and round sizes
rather than the synthetic placeholders in seed_comps.py. See SEEDING.md.

SEC fair-access rules require a declared User-Agent with a real contact address
(SEC_USER_AGENT in .env) and no more than 10 requests/second. This script makes
one request per quarter, and caches archives under data/edgar/.
"""
import argparse
import sys
import time
from pathlib import Path

import httpx
from loguru import logger

from config.settings import settings
from tools.chroma_guard import ensure_exclusive_access
from tools.edgar import DATASET_URL, extract_comps, recent_quarters
from tools.vector_store import comps_col, upsert_comps

CACHE_DIR = Path("data/edgar")
# SEC allows 10 req/s; one per quarter is nowhere near it, but be polite anyway.
REQUEST_DELAY_S = 0.5


def fetch_quarter(quarter: str, *, force: bool = False) -> bytes | None:
    """Download (or read from cache) one Form D quarterly archive."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = CACHE_DIR / f"{quarter}_d.zip"

    if cached.exists() and not force:
        logger.info(f"Using cached {cached}")
        return cached.read_bytes()

    url = DATASET_URL.format(quarter=quarter)
    ua = settings.sec_user_agent
    if "example.com" in ua:
        logger.warning(
            "SEC_USER_AGENT is still the placeholder. SEC fair-access policy "
            "expects a real contact address; set it in .env."
        )

    logger.info(f"Downloading {url}")
    try:
        r = httpx.get(url, headers={"User-Agent": ua}, timeout=120, follow_redirects=True)
        if r.status_code == 404:
            logger.warning(f"{quarter} not published yet (404).")
            return None
        r.raise_for_status()
    except Exception as exc:
        logger.error(f"Failed to download {quarter}: {exc}")
        return None

    cached.write_bytes(r.content)
    logger.success(f"Cached {len(r.content) / 1e6:.1f} MB -> {cached}")
    return r.content


def main() -> int:
    ap = argparse.ArgumentParser(description="Seed comps from SEC EDGAR Form D filings.")
    ap.add_argument("--quarters", type=int, default=2, help="how many recent quarters (default 2)")
    ap.add_argument("--limit", type=int, default=200, help="max comps to index (default 200)")
    ap.add_argument("--year", type=int, default=2026, help="latest year to start from")
    ap.add_argument("--q", type=int, default=1, help="latest quarter to start from")
    ap.add_argument("--dry-run", action="store_true", help="parse only; no embeddings, no writes")
    ap.add_argument("--force", action="store_true", help="re-download even if cached")
    ap.add_argument("--allow-running-api", action="store_true",
                    help="seed even if the API server is running (leaves it stale)")
    args = ap.parse_args()

    # Writing to Chroma under a live server leaves it with a stale index.
    if not args.dry_run:
        ensure_exclusive_access(force=args.allow_running_api)

    quarters = recent_quarters(args.quarters, args.year, args.q)
    logger.info(f"Quarters: {', '.join(quarters)}")

    comps = []
    for i, quarter in enumerate(quarters):
        if i:
            time.sleep(REQUEST_DELAY_S)
        blob = fetch_quarter(quarter, force=args.force)
        if not blob:
            continue
        remaining = args.limit - len(comps)
        if remaining <= 0:
            break
        comps.extend(extract_comps(blob, limit=remaining))

    if not comps:
        logger.error("No comps extracted. Nothing to do.")
        return 1

    # De-duplicate: an issuer amending a filing appears more than once.
    seen, unique = set(), []
    for c in comps:
        key = c.meta["company_name"].lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)
    logger.info(f"{len(unique)} unique issuers ({len(comps) - len(unique)} duplicates dropped)")

    sectors: dict[str, int] = {}
    stages: dict[str, int] = {}
    for c in unique:
        sectors[c.meta["sector"]] = sectors.get(c.meta["sector"], 0) + 1
        stages[c.meta["stage"]] = stages.get(c.meta["stage"], 0) + 1
    logger.info(f"Sectors: {dict(sorted(sectors.items(), key=lambda kv: -kv[1]))}")
    logger.info(f"Stages : {dict(sorted(stages.items(), key=lambda kv: -kv[1]))}")

    if args.dry_run:
        print(f"\n--- DRY RUN: {len(unique)} comps, first 5 ---\n")
        for c in unique[:5]:
            print(f"[{c.id}] {c.meta['sector']} / {c.meta['stage']}")
            print(f"  {c.text}\n")
        return 0

    before = comps_col.count()
    stored = upsert_comps([(c.id, c.text, c.meta) for c in unique])
    after = comps_col.count()
    logger.success(
        f"Indexed {stored} comps into '{comps_col.name}' "
        f"({before} -> {after}, +{after - before} new)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
