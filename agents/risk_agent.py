import asyncio
import json

from loguru import logger

from tools.llm_client import agenerate, parse_json
from tools.web_search import search

SYSTEM = """You are a VC risk analyst. Identify potential risks, red flags, legal disputes, or market controversies for a target startup.
Return ONLY valid JSON. No preamble, no markdown formatting wrappers."""

GENERIC_FLAGS = [
    "Regulatory and compliance challenges",
    "Market competition and consolidation",
    "Execution and scale risks",
]


async def risk_node(state: dict) -> dict:
    """Search the web for red flags, then classify them into investor risk flags."""
    logger.info("Executing risk node...")
    meta = state.get("metadata", {})
    name = meta.get("company_name", "")

    if not name or name == "Unknown Startup":
        logger.warning("No company name in metadata for risk search. Skipping web search.")
        results = []
    else:
        results = await asyncio.to_thread(
            search, f"{name} controversy lawsuit funding news"
        )

    prompt = f"""Company: {name}
Web findings:
{json.dumps(results, indent=2)}

Existing risk flags from pitch deck:
{meta.get('key_risks', [])}

Identify 3-5 specific risk flags an investor should investigate based on the web findings and the deck's key risks.
Return JSON with exactly one key "flags" containing a list of strings.
"""

    try:
        res = await agenerate(prompt, system=SYSTEM, json_mode=True)
        parsed = parse_json(res, default={}) or {}
        risk_flags = parsed.get("flags") or meta.get("key_risks") or GENERIC_FLAGS
    except Exception as exc:
        logger.error(f"Risk flag generation failed: {exc}")
        risk_flags = meta.get("key_risks") or GENERIC_FLAGS

    logger.info(f"Identified {len(risk_flags)} risk flags.")
    return {"risk_flags": risk_flags}
