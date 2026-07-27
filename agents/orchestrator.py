"""
LangGraph StateGraph orchestrating the VC analysis agents.

Node contract: every node returns ONLY the state keys it owns. Returning the
whole state ({**state, ...}) makes each of the parallel nodes write every
channel in the same superstep, which LangGraph rejects with InvalidUpdateError
("Can receive only one value per step"). See tests/test_orchestrator.py.
"""
from typing import List, Optional, TypedDict

from langgraph.graph import END, StateGraph
from loguru import logger

from agents.competitors_agent import competitors_node
from agents.comps_agent import comps_node
from agents.financials_agent import financials_node
from agents.founders_agent import founders_node
from agents.ingestion_agent import ingest_node
from agents.memo_agent import memo_node, score_node
from agents.risk_agent import risk_node
from tools.llm_client import agenerate, parse_json

# Maximum CRAG rewrite loops before forcing the pipeline forward.
MAX_REWRITES = 2

# ── 1. LangGraph State Schema ──────────────────────────────────────────


class VCState(TypedDict, total=False):
    company_name: str
    raw_text: str            # Web research dossier for the company
    file_id: str             # MongoDB reference ID

    # Ingestion outputs
    metadata: dict           # Sector, stage, founding year, founders, etc.
    financials_raw: dict     # ARR, burn, headcount, runway as raw values
    extraction_ok: bool      # False when structured extraction failed entirely

    # Parallel node outputs
    comps: List[dict]        # Retrieved comparable deals (Form D corpus)
    ratios: dict             # Computed financial ratios & ratings
    risk_flags: List[str]    # Tavily web search risk flags
    founder_profiles: dict   # Founder track record + team score
    competitors: dict        # Competitive landscape + moat score

    # Final outputs
    scorecard: dict          # Assessment dimensions 1-10
    memo: str                # Synthesized Markdown Investment Memo

    # Routing and loop control
    retrieval_grade: str     # "relevant" | "irrelevant"
    iteration: int           # Iteration counter for query rewrite loop
    error: Optional[str]


# ── 2. CRAG Grade & Rewrite Nodes ──────────────────────────────────────


async def grade_node(state: VCState) -> dict:
    """Evaluate whether the retrieved comps are relevant for benchmarking."""
    logger.info("Executing retrieval grade node...")

    iteration = state.get("iteration", 0)
    if iteration >= MAX_REWRITES:
        logger.info("Maximum rewrite iterations reached. Forcing relevance route.")
        return {"retrieval_grade": "relevant", "iteration": iteration + 1}

    comps = state.get("comps", [])
    if not comps:
        logger.warning("No comps retrieved. Marking irrelevant to trigger a rewrite.")
        return {"retrieval_grade": "irrelevant", "iteration": iteration + 1}

    meta = state.get("metadata", {})
    comps_text = "\n".join(f"- {c.get('text', '')[:250]}" for c in comps)

    prompt = f"""Target Company sector: {meta.get('sector')}, stage: {meta.get('stage')}
Retrieved comps:
{comps_text}

Are these comps relevant for benchmarking the target company?
Return JSON in exactly this structure:
{{"grade": "relevant" or "irrelevant", "reason": "str"}}
"""

    try:
        res = await agenerate(
            prompt,
            system="You are a VC research associate checking document relevance. Output ONLY valid JSON.",
            json_mode=True,
        )
        parsed = parse_json(res, default={}) or {}
        grade = parsed.get("grade", "relevant")
        logger.info(f"Grade: {grade}. Reason: {parsed.get('reason', '')}")
    except Exception as exc:
        logger.error(f"Failed to grade retrieval: {exc}. Defaulting to relevant.")
        grade = "relevant"

    if grade not in ("relevant", "irrelevant"):
        grade = "relevant"

    return {"retrieval_grade": grade, "iteration": iteration + 1}


async def rewrite_node(state: VCState) -> dict:
    """Rewrite the retrieval query to search for better comps."""
    logger.info("Executing query rewrite node...")
    meta = state.get("metadata", {})

    prompt = f"""The initial RAG query for company '{meta.get('company_name')}' returned irrelevant comps.
Sector: {meta.get('sector')}
Stage: {meta.get('stage')}
Business Model: {meta.get('business_model')}

Write a better search query targeting comparable deals in the right sector, stage, or business model.
Return JSON with exactly one key "query" containing the rewritten string.
"""

    fallback = " ".join(
        p for p in (meta.get("sector"), meta.get("stage"), "deal comps") if p
    )

    try:
        res = await agenerate(
            prompt,
            system="You are a VC search optimizer. Return ONLY valid JSON.",
            json_mode=True,
        )
        parsed = parse_json(res, default={}) or {}
        rewritten_query = parsed.get("query") or fallback
        logger.info(f"Rewritten query: '{rewritten_query}'")
    except Exception as exc:
        logger.error(f"Failed to rewrite query: {exc}")
        rewritten_query = fallback

    # Inject the rewritten query into metadata for comps_node to pick up.
    return {"metadata": {**meta, "_rewrite_query": rewritten_query}}


# ── 3. Route Function ──────────────────────────────────────────────────


def route_after_grade(state: VCState) -> str:
    """Decide whether to proceed to scoring or rewrite the query."""
    grade = state.get("retrieval_grade", "relevant")
    iteration = state.get("iteration", 1)

    if grade == "relevant" or iteration > MAX_REWRITES:
        logger.info("Routing: proceeding to scoring stage.")
        return "relevant"

    logger.info(f"Routing: rewrite loop {iteration}/{MAX_REWRITES}.")
    return "rewrite"


# ── 4. Build and Compile Graph ─────────────────────────────────────────


def build_graph():
    g = StateGraph(VCState)

    g.add_node("ingest", ingest_node)
    g.add_node("retrieve_comps", comps_node)
    g.add_node("compute_financials", financials_node)
    g.add_node("run_risk", risk_node)
    g.add_node("profile_founders", founders_node)
    g.add_node("map_competitors", competitors_node)
    g.add_node("grade_retrieval", grade_node)
    g.add_node("rewrite_query", rewrite_node)
    g.add_node("score", score_node)
    g.add_node("memo", memo_node)

    g.set_entry_point("ingest")

    # Fan-out from ingest — these five run concurrently.
    g.add_edge("ingest", "retrieve_comps")
    g.add_edge("ingest", "compute_financials")
    g.add_edge("ingest", "run_risk")
    g.add_edge("ingest", "profile_founders")
    g.add_edge("ingest", "map_competitors")

    # Fan-in into the CRAG grade.
    g.add_edge("retrieve_comps", "grade_retrieval")
    g.add_edge("compute_financials", "grade_retrieval")
    g.add_edge("run_risk", "grade_retrieval")
    g.add_edge("profile_founders", "grade_retrieval")
    g.add_edge("map_competitors", "grade_retrieval")

    g.add_conditional_edges(
        "grade_retrieval",
        route_after_grade,
        {"relevant": "score", "rewrite": "rewrite_query"},
    )

    # Loop from rewrite back to retrieval.
    g.add_edge("rewrite_query", "retrieve_comps")

    g.add_edge("score", "memo")
    g.add_edge("memo", END)

    return g.compile()


class VCOrchestrator:
    """Lazily compiles the graph so importing this module stays side-effect free."""

    def __init__(self):
        self._graph = None

    @property
    def graph(self):
        if self._graph is None:
            self._graph = build_graph()
        return self._graph

    async def run(
        self,
        raw_text: str,
        file_id: str,
        company_name: str = "Unknown Startup",
    ) -> dict:
        initial_state: VCState = {
            "company_name": company_name,
            "raw_text": raw_text,
            "file_id": file_id,
            "metadata": {},
            "financials_raw": {},
            "comps": [],
            "ratios": {},
            "risk_flags": [],
            "founder_profiles": {},
            "competitors": {},
            "scorecard": {},
            "memo": "",
            "retrieval_grade": "relevant",
            "iteration": 0,
            "error": None,
        }
        logger.info(f"Invoking VCOrchestrator for {company_name} (file_id: {file_id})")
        return await self.graph.ainvoke(initial_state)


orchestrator = VCOrchestrator()
