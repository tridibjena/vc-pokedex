from loguru import logger

from config.settings import settings
from tools.calculator import parse_number
from tools.llm_client import agenerate, parse_json

SYSTEM = """You are a VC analyst. Extract structured data from web research about a company.
Return ONLY valid JSON. No preamble, no markdown formatting blocks (like ```json). Just the raw JSON string."""

PROMPT = """Extract from this research dossier:
{text}

Return JSON with keys:
company_name, sector, stage (pre-seed/seed/series-a/series-b/growth),
founding_year, founders (list of full names), hq_location,
arr (number or null), burn_monthly (number or null),
cash (number or null), headcount (number or null),
revenue (number or null), cogs (number or null), prev_arr (number or null),
product_description (1 sentence), target_market (1 sentence),
business_model (1 sentence), key_risks (list of 3 strings),
last_round (string like "Series B" or null),
last_round_amount (number in USD or null),
last_round_date (string like "2025-11" or null),
valuation (number in USD, post-money if stated, or null),
lead_investors (list of firm names, may be empty),
notable_investors (list of firm names, may be empty)

"sector" MUST be exactly one of:
AI, DevTools, SaaS, FinTech, InsurTech, Biotech, HealthTech, Consumer,
Marketplace, Logistics, CleanTech, AgTech, Security, Data, Hardware,
Robotics, Gaming, EdTech, PropTech, Industrials, Telecom, Other
Pick the single closest match. Do not invent a new label or combine two.

Use null when a value is not stated. Do not invent numbers."""


async def ingest_node(state: dict) -> dict:
    """Extract structured metadata and raw financials from the document text.

    Returns only the keys this node owns — LangGraph rejects a node that writes
    a key another node writes in the same superstep.
    """
    logger.info("Executing ingestion node...")
    raw = state.get("raw_text", "")[: settings.max_extract_chars]

    try:
        result = await agenerate(PROMPT.format(text=raw), system=SYSTEM, json_mode=True)
        parsed = parse_json(result, default={}) or {}
    except Exception as exc:
        logger.error(f"Ingestion extraction failed: {exc}")
        parsed = {}

    # Fall back to the filename-derived name the pipeline passed in, rather than
    # collapsing every failed extraction onto a shared "Unknown Startup" record.
    fallback_name = state.get("company_name") or "Unknown Startup"

    metadata = {
        "company_name": parsed.get("company_name") or fallback_name,
        "sector": parsed.get("sector") or "Unknown Sector",
        "stage": parsed.get("stage") or "Unknown Stage",
        "founding_year": parsed.get("founding_year"),
        "founders": parsed.get("founders", []),
        "hq_location": parsed.get("hq_location") or "Unknown",
        "product_description": parsed.get("product_description", ""),
        "target_market": parsed.get("target_market", ""),
        "business_model": parsed.get("business_model", ""),
        "key_risks": parsed.get("key_risks", []),
        # Funding facts — surfaced on the dex card, so keep them on metadata.
        "last_round": parsed.get("last_round"),
        "last_round_amount": parse_number(parsed.get("last_round_amount")),
        "last_round_date": parsed.get("last_round_date"),
        "valuation": parse_number(parsed.get("valuation")),
        "lead_investors": parsed.get("lead_investors") or [],
        "notable_investors": parsed.get("notable_investors") or [],
    }

    financials_raw = {
        "arr": parsed.get("arr"),
        "burn": parsed.get("burn_monthly") if parsed.get("burn_monthly") is not None else parsed.get("burn"),
        "cash": parsed.get("cash"),
        "headcount": parsed.get("headcount"),
        "revenue": parsed.get("revenue"),
        "cogs": parsed.get("cogs"),
        "prev_arr": parsed.get("prev_arr"),
    }

    logger.info(f"Ingested metadata for {metadata['company_name']}")
    return {
        "company_name": metadata["company_name"],
        "metadata": metadata,
        "financials_raw": financials_raw,
        "extraction_ok": bool(parsed),
    }
