import json

from loguru import logger

from tools.calculator import compute_ratios
from tools.llm_client import agenerate, parse_json

SYSTEM = """You are a VC financial analyst. Assess the financial health and ratios of a target startup.
Return ONLY valid JSON. No preamble, no markdown formatting wrappers."""

FALLBACK = {
    "score": 5,
    "commentary": "Financial assessment unavailable — ratios could not be judged automatically.",
}


async def financials_node(state: dict) -> dict:
    """Compute deterministic ratios, then ask the model to judge them."""
    logger.info("Executing financials node...")
    financials_raw = state.get("financials_raw", {})
    ratios = compute_ratios(financials_raw)  # pure Python, never an LLM call

    meta = state.get("metadata", {})
    name = meta.get("company_name", "the startup")
    stage = meta.get("stage", "unknown stage")
    sector = meta.get("sector", "unknown sector")

    prompt = f"""Given these financial metrics and computed ratios for {name}:
{json.dumps(ratios, indent=2)}

Stage: {stage}
Sector: {sector}

Rate the financial health on a scale 1-10 and explain the key findings in 2 concise sentences.
Return JSON with exactly these keys: "score" (integer 1-10) and "commentary" (string description).
"""

    try:
        res = await agenerate(prompt, system=SYSTEM, json_mode=True)
        judgment = parse_json(res, default=FALLBACK) or FALLBACK
    except Exception as exc:
        logger.error(f"Financials assessment failed: {exc}")
        judgment = FALLBACK

    return {"ratios": {**ratios, **judgment}}
