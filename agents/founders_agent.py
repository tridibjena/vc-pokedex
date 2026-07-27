"""
Founder track-record agent.

With deck parsing gone, "who are these people and what have they shipped" is
something only the web can answer — and for early-stage deals it is often the
single highest-signal input. This node searches each named founder and profiles
the team.
"""
import asyncio
import json

from loguru import logger

from tools.llm_client import agenerate, parse_json
from tools.web_search import as_context, asearch_many

SYSTEM = """You are a VC talent analyst assessing founding teams.
Ground every claim in the provided sources. If a founder's background is not in
the sources, say so rather than inventing one. Return ONLY valid JSON."""

PROMPT = """Company: {company}
Known founders: {founders}

Web research on these people:
{context}

Profile the founding team. Return JSON with:
- "profiles": list of objects, each with
    - "name": string
    - "role": string or null
    - "background": one sentence on prior companies/roles, or "Not found in sources"
    - "signal": "strong" | "moderate" | "unproven"
- "team_summary": 2 sentences on the team's collective strength
- "team_score": integer 1-10

Base "signal" on evidence: prior exits or senior roles at relevant companies are
strong; relevant domain experience is moderate; no findable track record is
unproven."""

MAX_FOUNDERS = 4


async def founders_node(state: dict) -> dict:
    """Research the founding team and score it."""
    logger.info("Executing founders node...")
    meta = state.get("metadata", {})
    company = meta.get("company_name", "")
    founders = [f for f in (meta.get("founders") or []) if isinstance(f, str)][:MAX_FOUNDERS]

    if not founders or not company:
        logger.warning("No founders identified; skipping founder research.")
        return {"founder_profiles": {"profiles": [], "team_summary": "", "team_score": None}}

    queries = [f"{name} {company} founder background previous company" for name in founders]
    results = await asearch_many(queries, 3)

    if not results:
        return {
            "founder_profiles": {
                "profiles": [
                    {"name": n, "role": None, "background": "Not found in sources", "signal": "unproven"}
                    for n in founders
                ],
                "team_summary": "No web sources found for the founding team.",
                "team_score": None,
            }
        }

    try:
        raw = await agenerate(
            PROMPT.format(
                company=company,
                founders=json.dumps(founders),
                context=as_context(results, max_chars=12000),
            ),
            system=SYSTEM,
            json_mode=True,
        )
        parsed = parse_json(raw, default={}) or {}
    except Exception as exc:
        logger.error(f"Founder profiling failed: {exc}")
        parsed = {}

    profiles = parsed.get("profiles")
    if not isinstance(profiles, list):
        profiles = []

    score = parsed.get("team_score")
    try:
        score = max(1, min(10, int(round(float(score)))))
    except (TypeError, ValueError):
        score = None

    logger.info(f"Profiled {len(profiles)} founder(s); team score {score}.")
    return {
        "founder_profiles": {
            "profiles": profiles,
            "team_summary": parsed.get("team_summary", ""),
            "team_score": score,
        }
    }
