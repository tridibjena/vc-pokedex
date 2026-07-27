import json

from loguru import logger

from tools.llm_client import agenerate, parse_json

SCORE_SYSTEM = """You are a senior VC investment partner. Analyze the opportunity and return a scorecard in valid JSON. No preamble, no markdown code block wraps."""

SCORE_PROMPT = """Evaluate this investment opportunity and rate it:

Company: {name}
Sector: {sector} | Stage: {stage}
Product Description: {product}
Target Market: {market}

Financial Health & Ratios:
{ratios}

Comparable Deals:
{comps}

Risk Flags:
{risks}

Founding Team:
{team}

Competitive Landscape:
{competition}

Generate a structured scorecard JSON with EXACTLY these keys:
- market_size_score: integer (1-10)
- team_score: integer (1-10)
- traction_score: integer (1-10)
- competitive_moat_score: integer (1-10)
- financial_health_score: integer (1-10)
- overall_score: float (weighted average, 1.0-10.0)
- key_strengths: list of 3 strings
- key_risks: list of 3 strings
- recommendation: string ("PASS", "CONSIDER", or "INVEST")
- analysis_summary: string (3-4 sentences of clear summary)
"""

MEMO_PROMPT = """Write a professional VC investment memo in Markdown for:

Company: {name}
Sector: {sector} | Stage: {stage} | Founded: {year}
Product: {product}
Target Market: {market}

Financial Metrics:
{ratios}

Comparable Deals:
{comps}

Risk Flags:
{risks}

Founding Team:
{team}

Competitive Landscape:
{competition}

Scorecard:
{scorecard}

Structure:
## Executive Summary
## Market Opportunity
## Business Model
## Financial Analysis
## Comparable Deals
## Team
## Competitive Landscape
## Risk Assessment
## Investment Recommendation

Include specific numbers and metrics where available. End the memo with a clear conviction score 1-10 and a one-line verdict.
"""

SCORE_KEYS = (
    "market_size_score",
    "team_score",
    "traction_score",
    "competitive_moat_score",
    "financial_health_score",
)

FALLBACK_SCORECARD = {
    "market_size_score": 5,
    "team_score": 5,
    "traction_score": 5,
    "competitive_moat_score": 5,
    "financial_health_score": 5,
    "overall_score": 5.0,
    "key_strengths": [],
    "key_risks": [],
    "recommendation": "CONSIDER",
    "analysis_summary": "Scorecard could not be generated automatically; this record is a neutral placeholder.",
}


def _summarize_comps(comps: list[dict], include_stage: bool = False) -> str:
    lines = []
    for c in comps[:3]:
        meta = c.get("meta") or {}
        name = meta.get("company_name") or meta.get("company") or "Unknown Startup"
        label = f"{name} ({meta.get('stage', 'Unknown')})" if include_stage else f"{name} in sector {meta.get('sector', 'Unknown')}"
        lines.append(f"- {label}: {c.get('text', '')[:200]}")
    return "\n".join(lines) or "No comparable deals found."


def _summarize_team(fp: dict) -> str:
    profiles = (fp or {}).get("profiles") or []
    if not profiles:
        return "No founder research available."
    lines = [
        f"- {p.get('name', 'Unknown')}"
        + (f" ({p.get('role')})" if p.get("role") else "")
        + f": {p.get('background', '')} [signal: {p.get('signal', 'unknown')}]"
        for p in profiles
    ]
    if fp.get("team_summary"):
        lines.append(f"Summary: {fp['team_summary']}")
    if fp.get("team_score") is not None:
        lines.append(f"Team score from research: {fp['team_score']}/10")
    return "\n".join(lines)


def _summarize_competition(c: dict) -> str:
    rivals = (c or {}).get("competitors") or []
    lines = [f"- {r.get('name', 'Unknown')} ({r.get('tier', 'unknown')}): {r.get('note', '')}" for r in rivals]
    if c.get("differentiation"):
        lines.append(f"Differentiation: {c['differentiation']}")
    if c.get("moat_assessment"):
        lines.append(f"Moat: {c['moat_assessment']}")
    if c.get("moat_score") is not None:
        lines.append(f"Moat score from research: {c['moat_score']}/10")
    return "\n".join(lines) or "No competitive research available."


def _normalize_scorecard(sc: dict) -> dict:
    """Clamp dimension scores into 1-10 and recompute overall_score if absent or out of range.

    The model occasionally returns an overall_score inconsistent with its own
    dimensions, which then drives the UI colour thresholds and the deal ranking.
    """
    out = dict(sc)
    dims = []
    for k in SCORE_KEYS:
        v = out.get(k)
        try:
            v = int(round(float(v)))
        except (TypeError, ValueError):
            v = 5
        v = max(1, min(10, v))
        out[k] = v
        dims.append(v)

    try:
        overall = float(out.get("overall_score"))
    except (TypeError, ValueError):
        overall = None

    if overall is None or not (1.0 <= overall <= 10.0):
        overall = sum(dims) / len(dims)
    out["overall_score"] = round(float(overall), 2)

    rec = str(out.get("recommendation", "")).strip().upper()
    out["recommendation"] = rec if rec in ("PASS", "CONSIDER", "INVEST") else "CONSIDER"

    for k in ("key_strengths", "key_risks"):
        if not isinstance(out.get(k), list):
            out[k] = []

    return out


async def score_node(state: dict) -> dict:
    """Synthesize comps, ratios and risk flags into a dimension scorecard."""
    logger.info("Executing score node...")
    meta = state.get("metadata", {})
    risks_list = state.get("risk_flags", [])

    prompt = SCORE_PROMPT.format(
        name=meta.get("company_name", "Unknown"),
        sector=meta.get("sector", "Unknown"),
        stage=meta.get("stage", "Unknown"),
        product=meta.get("product_description", ""),
        market=meta.get("target_market", ""),
        ratios=json.dumps(state.get("ratios", {}), indent=2),
        comps=_summarize_comps(state.get("comps", [])),
        risks="\n".join(f"- {r}" for r in risks_list) or "No specific risk flags.",
        team=_summarize_team(state.get("founder_profiles", {})),
        competition=_summarize_competition(state.get("competitors", {})),
    )

    try:
        res = await agenerate(prompt, system=SCORE_SYSTEM, json_mode=True)
        scorecard = parse_json(res, default=None)
        if not isinstance(scorecard, dict):
            logger.error("Scorecard response was not a JSON object. Using fallback.")
            scorecard = dict(FALLBACK_SCORECARD)
    except Exception as exc:
        logger.error(f"Scorecard generation failed: {exc}. Using fallback.")
        scorecard = dict(FALLBACK_SCORECARD)

    return {"scorecard": _normalize_scorecard(scorecard)}


async def memo_node(state: dict) -> dict:
    """Write the final Markdown investment memo."""
    logger.info("Executing memo node...")
    meta = state.get("metadata", {})
    risks_list = state.get("risk_flags", [])

    prompt = MEMO_PROMPT.format(
        name=meta.get("company_name", "Unknown Startup"),
        sector=meta.get("sector", "Unknown"),
        stage=meta.get("stage", "Unknown"),
        year=meta.get("founding_year", "Unknown"),
        product=meta.get("product_description", ""),
        market=meta.get("target_market", ""),
        ratios=json.dumps(state.get("ratios", {}), indent=2),
        comps=_summarize_comps(state.get("comps", []), include_stage=True),
        risks="\n".join(f"- {r}" for r in risks_list) or "No specific risk flags identified.",
        team=_summarize_team(state.get("founder_profiles", {})),
        competition=_summarize_competition(state.get("competitors", {})),
        scorecard=json.dumps(state.get("scorecard", {}), indent=2),
    )

    try:
        memo = await agenerate(
            prompt,
            system="You are an expert VC Analyst who writes concise and data-rich investment memos.",
        )
    except Exception as exc:
        logger.error(f"Memo generation failed: {exc}")
        return {
            "memo": f"# Investment Memo for {meta.get('company_name', 'Unknown Startup')}\n\n"
                    f"Memo generation failed: {exc}",
            "error": f"memo_generation_failed: {exc}",
        }

    return {"memo": memo}
