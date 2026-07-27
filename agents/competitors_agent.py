"""
Competitive-landscape agent.

The comps agent answers "what did similar deals price at" from the Form D
corpus. This one answers a different question: "who else is actually building
this, and why would a customer pick this company over them?" — which is what
determines the moat score.
"""
import asyncio

from loguru import logger

from tools.llm_client import agenerate, parse_json
from tools.web_search import as_context, asearch_many

SYSTEM = """You are a VC market analyst mapping competitive landscapes.
Ground every competitor in the provided sources. Do not invent companies.
Return ONLY valid JSON."""

PROMPT = """Target company: {company}
Sector: {sector}
What it does: {product}

Web research on this market:
{context}

Map the competitive landscape. Return JSON with:
- "competitors": list of up to 5 objects, each with
    - "name": string
    - "note": one short phrase on how they overlap (max 12 words)
    - "tier": "incumbent" | "direct" | "adjacent"
- "differentiation": one sentence on what separates the target, or
  "No clear differentiation found in sources"
- "moat_assessment": 2 sentences on defensibility
- "moat_score": integer 1-10

Score the moat low when the market is crowded and the product is easily
replicated; high when there is proprietary data, real switching costs, or
distribution advantage evidenced in the sources."""


async def competitors_node(state: dict) -> dict:
    """Map the competitive landscape and assess defensibility."""
    logger.info("Executing competitors node...")
    meta = state.get("metadata", {})
    company = meta.get("company_name", "")
    sector = meta.get("sector", "")
    product = meta.get("product_description", "")

    if not company:
        return {"competitors": {"competitors": [], "differentiation": "", "moat_score": None}}

    queries = [
        f"{company} competitors alternatives vs",
        f"{sector} startups competing with {company}",
    ]
    if product:
        queries.append(f"companies building {product[:80]}")

    results = await asearch_many(queries, 4)

    if not results:
        return {
            "competitors": {
                "competitors": [],
                "differentiation": "No sources found for competitive analysis.",
                "moat_assessment": "",
                "moat_score": None,
            }
        }

    try:
        raw = await agenerate(
            PROMPT.format(
                company=company,
                sector=sector or "unknown",
                product=product or "unknown",
                context=as_context(results, max_chars=12000),
            ),
            system=SYSTEM,
            json_mode=True,
        )
        parsed = parse_json(raw, default={}) or {}
    except Exception as exc:
        logger.error(f"Competitor mapping failed: {exc}")
        parsed = {}

    competitors = parsed.get("competitors")
    if not isinstance(competitors, list):
        competitors = []

    score = parsed.get("moat_score")
    try:
        score = max(1, min(10, int(round(float(score)))))
    except (TypeError, ValueError):
        score = None

    logger.info(f"Mapped {len(competitors)} competitor(s); moat score {score}.")
    return {
        "competitors": {
            "competitors": competitors[:5],
            "differentiation": parsed.get("differentiation", ""),
            "moat_assessment": parsed.get("moat_assessment", ""),
            "moat_score": score,
        }
    }
