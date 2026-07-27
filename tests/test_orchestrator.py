"""
Execution tests for the LangGraph orchestrator.

These are the tests whose absence let the parallel fan-out ship broken: every
node returned {**state, ...}, so all three concurrent nodes wrote every channel
in one superstep and LangGraph raised InvalidUpdateError. Import smoke tests
could never catch that — the graph has to actually run.
"""
import json

import pytest

from tests.conftest import default_router

pytestmark = pytest.mark.asyncio

COMPS = [
    {"id": "c1", "text": "SaaS series-a subscription workspace, $3.2M ARR.",
     "meta": {"company_name": "FigmaClone", "sector": "SaaS", "stage": "series-a"}},
    {"id": "c2", "text": "AI seed legal contract analysis, $500k ARR.",
     "meta": {"company_name": "LexAI", "sector": "AI", "stage": "seed"}},
]


@pytest.fixture
def stub_comps(monkeypatch):
    """Stub the vector store so the graph test doesn't need a real Chroma index."""
    import agents.comps_agent as ca

    calls = []

    def _q(text, n=None):
        calls.append(text)
        return list(COMPS)

    monkeypatch.setattr(ca, "query_comps", _q)
    return calls


async def test_graph_runs_end_to_end(fake_gemini, stub_comps):
    """The full pipeline must execute without InvalidUpdateError and fill every output."""
    from agents.orchestrator import build_graph

    graph = build_graph()
    result = await graph.ainvoke({
        "company_name": "TestCo",
        "raw_text": "TestCo raised a Series A. ARR $5M, burn $200k/mo.",
        "file_id": "f1",
        "iteration": 0,
    })

    assert result["metadata"]["company_name"] == "TestCo"
    assert result["metadata"]["sector"] == "SaaS"
    assert result["comps"], "comps node did not populate state"
    assert result["ratios"]["score"] == 8, "financials node did not populate state"
    assert result["risk_flags"], "risk node did not populate state"
    assert result["scorecard"]["recommendation"] == "INVEST"
    assert result["memo"].startswith("# Investment Memo")


async def test_all_three_parallel_nodes_populate_state(fake_gemini, stub_comps):
    """Regression guard for the concurrent-write blocker.

    Each parallel node owns a disjoint set of keys. If any of them starts
    returning the whole state again, LangGraph raises InvalidUpdateError here.
    """
    from agents.orchestrator import build_graph

    result = await build_graph().ainvoke({
        "company_name": "TestCo", "raw_text": "text", "file_id": "f1", "iteration": 0,
    })

    # comps / ratios / risk_flags are written by three different concurrent nodes.
    assert result["comps"] and result["ratios"] and result["risk_flags"]


async def test_nodes_return_only_their_own_keys(fake_gemini, stub_comps):
    """Each parallel node must return a delta, not the whole state."""
    from agents.comps_agent import comps_node
    from agents.financials_agent import financials_node
    from agents.risk_agent import risk_node

    state = {
        "company_name": "TestCo",
        "metadata": {"company_name": "TestCo", "sector": "SaaS", "stage": "series-a"},
        "financials_raw": {"arr": 5_000_000, "prev_arr": 2_000_000, "burn": 200_000,
                           "cash": 3_000_000, "headcount": 25},
        "raw_text": "text",
    }

    assert set(await comps_node(state)) == {"comps"}
    assert set(await financials_node(state)) == {"ratios"}
    assert set(await risk_node(state)) == {"risk_flags"}


async def test_crag_rewrite_loop_triggers_then_terminates(fake_gemini, monkeypatch):
    """An irrelevant first retrieval must trigger rewrites and still terminate."""
    import agents.comps_agent as ca
    from agents.orchestrator import MAX_REWRITES, build_graph

    queries = []

    def _q(text, n=None):
        queries.append(text)
        return list(COMPS)

    monkeypatch.setattr(ca, "query_comps", _q)

    # Always grade irrelevant, so only the iteration cap can stop the loop.
    def router(prompt, system):
        if "are these comps relevant" in prompt.lower():
            return json.dumps({"grade": "irrelevant", "reason": "wrong sector"})
        return default_router(prompt, system)

    fake_gemini.router = router

    result = await build_graph().ainvoke({
        "company_name": "TestCo", "raw_text": "text", "file_id": "f1", "iteration": 0,
    })

    # Initial retrieval + one per rewrite, and the pipeline still reaches the memo.
    assert len(queries) == MAX_REWRITES + 1
    assert result["iteration"] == MAX_REWRITES + 1
    assert result["memo"], "graph did not reach the memo node after the rewrite loop"


async def test_rewrite_query_is_used_on_retry(fake_gemini, monkeypatch):
    """The rewritten query must actually reach the comps node."""
    import agents.comps_agent as ca
    from agents.orchestrator import build_graph

    queries = []
    monkeypatch.setattr(ca, "query_comps", lambda text, n=None: (queries.append(text), [])[1])

    await build_graph().ainvoke({
        "company_name": "TestCo", "raw_text": "text", "file_id": "f1", "iteration": 0,
    })

    assert queries[0] == "SaaS series-a Subscription"
    assert queries[1] == "SaaS series-a subscription comps", "rewritten query was ignored"


async def test_graph_survives_total_extraction_failure(fake_gemini, stub_comps):
    """A model returning junk must not crash the graph — fallbacks fill in."""
    fake_gemini.router = lambda prompt, system: "not json at all"

    result = await build_graph_and_run()
    assert result["metadata"]["company_name"] == "SeedCo"  # falls back to the passed-in name
    assert result["scorecard"]["recommendation"] == "CONSIDER"
    assert result["scorecard"]["overall_score"] == 5.0


async def build_graph_and_run():
    from agents.orchestrator import build_graph

    return await build_graph().ainvoke({
        "company_name": "SeedCo", "raw_text": "text", "file_id": "f1", "iteration": 0,
    })


async def test_founders_and_competitors_populate_state(fake_gemini, stub_comps, monkeypatch):
    """The two research agents must fill their own channels, concurrently."""
    import agents.competitors_agent as ca
    import agents.founders_agent as fa
    from agents.orchestrator import build_graph

    # Stub the web layer; the point here is graph wiring, not Tavily.
    async def _founder_search(q, n=5, **kw):
        return [{"title": "Ada Lovelace profile", "url": "https://x.test/ada",
                 "content": "Ada led engines."}]

    async def _market_search(q, n=5, **kw):
        return [{"title": "Design tool market", "url": "https://x.test/mkt",
                 "content": "Figma dominates."}]

    monkeypatch.setattr(fa, "asearch_many", _founder_search)
    monkeypatch.setattr(ca, "asearch_many", _market_search)

    result = await build_graph().ainvoke({
        "company_name": "TestCo", "raw_text": "text", "file_id": "f1", "iteration": 0,
    })

    assert result["founder_profiles"]["team_score"] == 9
    assert result["founder_profiles"]["profiles"][0]["name"] == "Ada Lovelace"
    assert result["competitors"]["moat_score"] == 6
    assert {c["name"] for c in result["competitors"]["competitors"]} == {"Figma", "Penpot"}


async def test_new_nodes_return_only_their_own_keys(fake_gemini, monkeypatch):
    """Five nodes now share a superstep; each must own a disjoint channel."""
    import agents.competitors_agent as ca
    import agents.founders_agent as fa
    from agents.competitors_agent import competitors_node
    from agents.founders_agent import founders_node

    async def _stub(q, n=5, **kw):
        return [{"title": "t", "url": "https://x.test/1", "content": "c"}]

    monkeypatch.setattr(fa, "asearch_many", _stub)
    monkeypatch.setattr(ca, "asearch_many", _stub)

    state = {"metadata": {"company_name": "TestCo", "sector": "SaaS",
                          "founders": ["Ada Lovelace"], "product_description": "design tool"}}

    assert set(await founders_node(state)) == {"founder_profiles"}
    assert set(await competitors_node(state)) == {"competitors"}


async def test_founders_node_without_founders_is_a_noop(fake_gemini):
    """No founders extracted → no web calls, empty profile, no crash."""
    from agents.founders_agent import founders_node

    out = await founders_node({"metadata": {"company_name": "TestCo", "founders": []}})
    assert out["founder_profiles"]["profiles"] == []
    assert fake_gemini.generate_calls == []


async def test_searches_run_concurrently(monkeypatch):
    """The five dossier queries are network waits; running them in series made a
    scan ~8s slower for nothing."""
    import time

    from tools import web_search

    started: list[float] = []

    def slow_search(query, max_results=5, **kw):
        started.append(time.monotonic())
        time.sleep(0.25)
        return [{"title": query, "url": f"https://x.test/{query}", "content": "c"}]

    monkeypatch.setattr(web_search, "search", slow_search)

    t0 = time.monotonic()
    out = await web_search.asearch_many([f"q{i}" for i in range(5)], 3)
    elapsed = time.monotonic() - t0

    assert len(out) == 5
    # Sequential would be ~1.25s; concurrent should land near one call.
    assert elapsed < 0.7, f"searches did not overlap (took {elapsed:.2f}s)"


async def test_one_failing_search_does_not_sink_the_dossier(monkeypatch):
    from tools import web_search

    def flaky(query, max_results=5, **kw):
        if query == "bad":
            raise RuntimeError("tavily timeout")
        return [{"title": query, "url": f"https://x.test/{query}", "content": "c"}]

    monkeypatch.setattr(web_search, "search", flaky)
    out = await web_search.asearch_many(["good", "bad", "other"], 3)
    assert {r["title"] for r in out} == {"good", "other"}


async def test_start_does_not_index_or_analyze(monkeypatch, fake_gemini):
    """POST /research must return as soon as the company is known."""
    import agents.research_agent as ra
    from pipelines.research_pipeline import research_pipeline
    from tools import vector_store

    async def fake_research(name, max_results=5):
        hit = [{"title": "t", "url": "https://x.test/1", "content": "c"}]
        return "dossier text", hit, hit

    monkeypatch.setattr(ra, "research_company", fake_research)
    import pipelines.research_pipeline as rp
    monkeypatch.setattr(rp, "research_company", fake_research)

    saved = {}
    async def _save_file(fid, doc): saved["file"] = fid
    async def _save_meta(doc): saved["meta"] = doc.get("file_id")
    monkeypatch.setattr(rp.mongo_client, "save_file", _save_file)
    monkeypatch.setattr(rp.mongo_client, "save_document_metadata", _save_meta)

    embedded = []
    monkeypatch.setattr(vector_store, "upsert_chunks", lambda p: embedded.append(p) or len(p))
    monkeypatch.setattr(rp, "upsert_chunks", lambda p: embedded.append(p) or len(p))

    res = await research_pipeline.start("TestCo")

    assert res["company_name"] == "TestCo"
    assert res["chunks_stored"] == 0
    assert embedded == [], "start() must not index — that belongs in the background"
    assert saved["file"] == saved["meta"] == res["file_id"]
