"""
Shared test fixtures.

The Gemini SDK is faked at the client boundary rather than by patching each
agent's imported `agenerate`, so tests exercise the real prompt construction,
real JSON parsing and real graph wiring.
"""
import json
import os
import sys
import zlib

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class FakeEmbedding:
    def __init__(self, values):
        self.values = values


class FakeEmbedResponse:
    def __init__(self, embeddings):
        self.embeddings = embeddings


class FakeGenerateResponse:
    def __init__(self, text):
        self.text = text


def _deterministic_vector(text: str, dims: int = 8) -> list[float]:
    """Cheap stand-in for a real embedding: stable, and similar strings collide.

    Uses crc32 rather than hash(): Python salts string hashing per process, so
    hash() made this vector — and therefore the retrieval-ordering test —
    silently non-deterministic across runs.
    """
    vec = [0.0] * dims
    for token in text.lower().split():
        vec[zlib.crc32(token.encode()) % dims] += 1.0
    norm = sum(v * v for v in vec) ** 0.5
    return [v / norm for v in vec] if norm else [1.0] + [0.0] * (dims - 1)


def default_router(prompt: str, system: str) -> str:
    """Return a plausible response for whichever agent issued the prompt."""
    p = prompt.lower()
    if "return json with keys" in p and "company_name, sector, stage" in p:
        return json.dumps({
            "company_name": "TestCo",
            "sector": "SaaS",
            "stage": "series-a",
            "founding_year": 2021,
            "founders": ["Ada Lovelace"],
            "hq_location": "Berlin",
            "arr": 5_000_000,
            "burn_monthly": 200_000,
            "cash": 3_000_000,
            "headcount": 25,
            "revenue": 4_000_000,
            "cogs": 1_000_000,
            "prev_arr": 2_000_000,
            "product_description": "A collaborative workspace.",
            "target_market": "Mid-market product teams.",
            "business_model": "Subscription",
            "key_risks": ["Churn", "Competition", "Concentration"],
        })
    if "rate the financial health" in p:
        return json.dumps({"score": 8, "commentary": "Healthy growth, sane burn."})
    if '"flags"' in p:
        return json.dumps({"flags": ["Pending litigation", "Key-man risk"]})
    if '"profiles"' in p and "founding team" in p:
        return json.dumps({
            "profiles": [
                {"name": "Ada Lovelace", "role": "CEO",
                 "background": "Previously led analytical engines at Babbage Co.",
                 "signal": "strong"},
            ],
            "team_summary": "Technical founder with a prior exit.",
            "team_score": 9,
        })
    if '"competitors"' in p and "competitive landscape" in p:
        return json.dumps({
            "competitors": [
                {"name": "Figma", "note": "incumbent design suite", "tier": "incumbent"},
                {"name": "Penpot", "note": "open-source alternative", "tier": "direct"},
            ],
            "differentiation": "Real-time multiplayer with offline support.",
            "moat_assessment": "Moderate. Network effects but replicable core.",
            "moat_score": 6,
        })
    if "are these comps relevant" in p:
        return json.dumps({"grade": "relevant", "reason": "Same sector and stage."})
    if "write a better search query" in p:
        return json.dumps({"query": "SaaS series-a subscription comps"})
    if "generate a structured scorecard" in p:
        return json.dumps({
            "market_size_score": 8,
            "team_score": 7,
            "traction_score": 9,
            "competitive_moat_score": 6,
            "financial_health_score": 8,
            "overall_score": 7.6,
            "key_strengths": ["Growth", "Margins", "Team"],
            "key_risks": ["Churn", "Competition", "Concentration"],
            "recommendation": "INVEST",
            "analysis_summary": "Strong series-a profile.",
        })
    if "write a professional vc investment memo" in p:
        return "# Investment Memo: TestCo\n\n## Executive Summary\nStrong.\n\nConviction: 8/10."
    return "ok"


class FakeGeminiClient:
    """Stands in for google.genai.Client."""

    def __init__(self, router=None):
        self.router = router or default_router
        self.generate_calls: list[tuple[str, str]] = []
        self.embed_calls: list[list[str]] = []
        self.models = _SyncModels(self)
        self.aio = _Aio(self)


class _SyncModels:
    def __init__(self, parent):
        self._p = parent

    def embed_content(self, *, model, contents, config=None):
        items = [contents] if isinstance(contents, str) else list(contents)
        self._p.embed_calls.append(items)
        return FakeEmbedResponse([FakeEmbedding(_deterministic_vector(t)) for t in items])

    def generate_content(self, *, model, contents, config=None):
        system = getattr(config, "system_instruction", "") or ""
        self._p.generate_calls.append((contents, system))
        return FakeGenerateResponse(self._p.router(contents, system))


class _AsyncModels:
    def __init__(self, parent):
        self._p = parent

    async def generate_content(self, *, model, contents, config=None):
        system = getattr(config, "system_instruction", "") or ""
        self._p.generate_calls.append((contents, system))
        return FakeGenerateResponse(self._p.router(contents, system))

    async def generate_content_stream(self, *, model, contents, config=None):
        system = getattr(config, "system_instruction", "") or ""
        text = self._p.router(contents, system)

        async def gen():
            for word in text.split(" "):
                yield FakeGenerateResponse(word + " ")

        return gen()


class _Aio:
    def __init__(self, parent):
        self.models = _AsyncModels(parent)


@pytest.fixture(autouse=True)
def _offline_and_unthrottled(monkeypatch):
    """Keep the suite offline and fast.

    Two things would otherwise reach the network or sleep:

    1. Rate limiting — the free tier allows 5 generate requests/minute, so the
       real limiter would make the graph tests sleep for minutes against a faked
       SDK that never calls out anyway.
    2. OpenRouter — it now leads the model chain, so once OPENROUTER_API_KEY is
       set in .env the faked Gemini client is never reached and every test hits
       the live API. Force the chain back to Gemini-only; the few tests that
       exercise OpenRouter opt back in explicitly.
    """
    import tools.llm_client as llm
    from tools import openrouter

    monkeypatch.setattr(llm._generate_limiter, "per_minute", 0, raising=False)
    monkeypatch.setattr(llm._embed_limiter, "per_minute", 0, raising=False)
    monkeypatch.setattr(openrouter, "is_configured", lambda: False)


@pytest.fixture
def fake_gemini(monkeypatch):
    """Patch tools.llm_client.get_client to return a FakeGeminiClient."""
    import tools.llm_client as llm

    fake = FakeGeminiClient()
    monkeypatch.setattr(llm, "get_client", lambda: fake)
    monkeypatch.setattr(llm, "_client", fake, raising=False)
    return fake
