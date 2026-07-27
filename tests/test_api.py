"""
Tests for the FastAPI layer — schemas, routing, CORS and upload handling.
"""
from datetime import datetime

import pytest
from pydantic import ValidationError


class TestSchemas:
    def test_chat_request_defaults(self):
        from api.schemas import ChatRequest

        req = ChatRequest(query="What is the ARR?")
        assert req.stream is False
        assert req.file_id is None
        assert len(req.session_id) > 0

    def test_chat_request_rejects_empty_query(self):
        from api.schemas import ChatRequest

        with pytest.raises(ValidationError):
            ChatRequest(query="")


    def test_health_response(self):
        from api.schemas import HealthResponse

        hr = HealthResponse(status="ok", gemini=True, openrouter=False,
                            mongodb=True, chromadb=True,
                            primary_model="openrouter:nvidia/nemotron-3-super-120b-a12b:free")
        assert hr.version == "1.0.0"
        # Gemini stays required even when it is not the primary generator:
        # embeddings, and therefore all retrieval, run on it.
        assert hr.gemini is True and hr.openrouter is False

    def test_deal_card_and_list(self):
        from api.schemas import DealCard, DealsListResponse

        dc = DealCard(deal_id="x", company_name="A", sector="AI", stage="seed",
                      created_at=datetime(2025, 6, 1))
        resp = DealsListResponse(deals=[dc], total=1)
        assert resp.total == 1

    def test_research_request_requires_a_name(self):
        from api.schemas import ResearchRequest

        with pytest.raises(ValidationError):
            ResearchRequest(company_name="")

    def test_research_response_reports_job_status(self):
        from api.schemas import ResearchResponse

        r = ResearchResponse(success=True, file_id="f1", company_name="A",
                             chunks_stored=3, sources=[], status="processing",
                             message="ok")
        assert r.status == "processing"



class TestChunking:
    def test_overlap_larger_than_size_does_not_hang(self):
        """A stride <= 0 would loop forever; the guard must clamp it."""
        from tools.chunking import chunk_text

        chunks = chunk_text("x" * 5000, size=100, overlap=500)
        assert 0 < len(chunks) < 1000

    def test_normal_chunking_overlaps(self):
        from tools.chunking import chunk_text

        text = "".join(str(i % 10) for i in range(2500))
        chunks = chunk_text(text, size=1000, overlap=200)
        assert len(chunks) == 4          # stride 800 over 2500 chars
        assert chunks[0][800:] == chunks[1][:200]

    def test_short_text_is_one_chunk(self):
        from tools.chunking import chunk_text

        assert chunk_text("hello", size=1000, overlap=200) == ["hello"]

    def test_empty_text_yields_no_chunks(self):
        from tools.chunking import chunk_text

        assert chunk_text("", size=1000, overlap=200) == []


def _flatten_paths(router) -> list[str]:
    """FastAPI wraps included routers in _IncludedRouter, so walk into them."""
    paths = []
    for r in getattr(router, "routes", []):
        if hasattr(r, "path"):
            paths.append(r.path)
        elif hasattr(r, "original_router"):
            paths.extend(_flatten_paths(r.original_router))
        else:
            paths.extend(_flatten_paths(r))
    return paths


class TestApp:
    def test_app_import(self):
        from api.main import app

        assert app.title == "VC Pokedex API"

    def test_routes_registered(self):
        from api.main import app

        routes = set(_flatten_paths(app))
        for expected in ("/health", "/chat", "/chat/stream",
                         "/research", "/research/ticker",
                         "/research/status/{file_id}", "/research/documents",
                         "/reports/deals", "/reports/trends", "/reports/list"):
            assert expected in routes, f"missing route {expected}"

    def test_literal_report_routes_precede_the_catch_all(self):
        """/reports/{report_id} must not shadow /reports/deals, /list or /trends."""
        from api.main import app

        paths = [p for p in _flatten_paths(app) if p.startswith("/reports")]
        catch_all = paths.index("/reports/{report_id}")
        for literal in ("/reports/deals", "/reports/list", "/reports/trends"):
            assert paths.index(literal) < catch_all, f"{literal} is shadowed"


class TestSPACatchAll:
    """The dist catch-all previously fell through to `return None` for API
    prefixes, answering 200 with a null body instead of a real 404."""

    def test_api_prefix_under_catch_all_is_not_200_null(self):
        from pathlib import Path

        from fastapi.testclient import TestClient

        from api.main import DIST_DIR, app

        if not Path(DIST_DIR).exists():
            pytest.skip("dashboard/dist not built; catch-all is not registered")

        client = TestClient(app)
        r = client.get("/health/bogus-subpath")
        assert r.status_code != 200, f"catch-all answered 200 with {r.text[:80]!r}"
        assert r.json() != None  # noqa: E711 — the old bug returned literal null

    def test_unknown_client_route_serves_the_spa(self):
        from pathlib import Path

        from fastapi.testclient import TestClient

        from api.main import DIST_DIR, app

        if not Path(DIST_DIR).exists():
            pytest.skip("dashboard/dist not built; catch-all is not registered")

        client = TestClient(app)
        r = client.get("/some/client/route")
        assert r.status_code == 200
        assert "<div id=\"app\">" in r.text


class TestCORS:
    def test_wildcard_origin_is_not_reflected(self):
        """`*` + credentials makes Starlette echo any origin; config must be explicit."""
        from fastapi.testclient import TestClient

        from api.main import app

        client = TestClient(app)
        r = client.get("/health", headers={"Origin": "https://evil.example"})
        assert r.headers.get("access-control-allow-origin") != "https://evil.example"

    def test_configured_origin_is_allowed(self):
        from fastapi.testclient import TestClient

        from api.main import app

        client = TestClient(app)
        r = client.get("/health", headers={"Origin": "http://localhost:5173"})
        assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


class TestHealthCost:
    def test_health_does_not_call_the_gemini_api(self, fake_gemini):
        """The dashboard polls /health on a timer — it must never cost a token."""
        from fastapi.testclient import TestClient

        from api.main import app

        client = TestClient(app)
        client.get("/health")

        assert fake_gemini.generate_calls == [], "health check made a generate() call"
        assert fake_gemini.embed_calls == [], "health check made an embed() call"
