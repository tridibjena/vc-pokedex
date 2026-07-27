"""
Unit tests for the VC Pokedex tools layer and individual agent nodes.
"""
import pytest

from tools.calculator import compute_ratios, parse_number


class TestParseNumber:
    """The model emits numbers in many shapes; all of them must survive."""

    @pytest.mark.parametrize("raw,expected", [
        (5_000_000, 5_000_000.0),
        (2.5, 2.5),
        ("5000000", 5_000_000.0),
        ("$5,000,000", 5_000_000.0),
        ("$5M", 5_000_000.0),
        ("5m", 5_000_000.0),
        ("1.2B", 1_200_000_000.0),
        ("3.5 bn", 3_500_000_000.0),
        ("750K", 750_000.0),
        ("78%", 78.0),
        ("(500,000)", -500_000.0),
        ("-250000", -250_000.0),
        ("€1.5M", 1_500_000.0),
    ])
    def test_parses(self, raw, expected):
        assert parse_number(raw) == expected

    @pytest.mark.parametrize("raw", [None, "", "  ", "N/A", "unknown", "abc", [], {}, True, False])
    def test_rejects(self, raw):
        assert parse_number(raw) is None


class TestCalculator:
    """tools/calculator.py — pure deterministic arithmetic, never an LLM call."""

    def test_compute_ratios_full(self):
        r = compute_ratios({
            "arr": 5_000_000, "prev_arr": 2_000_000, "burn": 200_000,
            "cash": 3_000_000, "headcount": 25,
            "revenue": 4_000_000, "cogs": 1_000_000,
        })

        # Burn multiple compares like periods: annualized burn (200k x 12 = 2.4M)
        # against net new ARR (5M - 2M = 3M) => 0.8. Dividing the MONTHLY burn by
        # the ANNUAL ARR delta would give 0.07, which understates it 12x.
        assert r["burn_multiple"] == 0.8
        assert r["annual_burn"] == 2_400_000.0
        assert r["net_new_arr"] == 3_000_000.0

        assert r["runway_months"] == 15.0           # 3M / 200k
        assert r["yoy_growth"] == 150.0             # (5M - 2M) / 2M
        assert r["gross_margin"] == 75.0            # (4M - 1M) / 4M
        assert r["arr_per_head"] == 200_000.0       # 5M / 25

    def test_string_values_with_suffixes(self):
        r = compute_ratios({
            "arr": "$5M", "prev_arr": "$2M", "burn": "200k",
            "cash": "3M", "headcount": "25",
            "revenue": "$4M", "cogs": "1M",
        })
        assert r["runway_months"] == 15.0
        assert r["yoy_growth"] == 150.0
        assert r["burn_multiple"] == 0.8
        assert r["gross_margin"] == 75.0

    def test_missing_keys_yield_none(self):
        r = compute_ratios({})
        for key in ("burn_multiple", "runway_months", "yoy_growth", "gross_margin", "arr_per_head"):
            assert r[key] is None

    def test_zero_denominators_yield_none(self):
        r = compute_ratios({
            "arr": 1_000_000, "prev_arr": 0, "burn": 0,
            "cash": 500_000, "headcount": 0, "revenue": 0, "cogs": 0,
        })
        assert r["runway_months"] is None
        assert r["gross_margin"] is None
        assert r["arr_per_head"] is None
        assert r["yoy_growth"] is None

    def test_flat_arr_gives_no_burn_multiple(self):
        """Zero net new ARR must not divide by zero."""
        r = compute_ratios({"arr": 1_000_000, "prev_arr": 1_000_000, "burn": 50_000})
        assert r["burn_multiple"] is None
        assert r["net_new_arr"] == 0.0

    def test_shrinking_arr_keeps_negative_sign(self):
        r = compute_ratios({"arr": 1_000_000, "prev_arr": 2_000_000, "burn": 100_000})
        assert r["net_new_arr"] == -1_000_000.0
        assert r["burn_multiple"] == -1.2
        assert r["yoy_growth"] == -50.0

    def test_missing_cogs_treated_as_zero(self):
        r = compute_ratios({"revenue": 1_000_000})
        assert r["gross_margin"] == 100.0

    def test_never_raises_on_garbage(self):
        r = compute_ratios({k: "not a number" for k in
                            ("arr", "prev_arr", "burn", "cash", "headcount", "revenue", "cogs")})
        assert all(v is None for v in r.values())



class TestJSONParsing:
    """tools/llm_client.parse_json — tolerates the fences Gemini adds anyway."""

    def test_plain_json(self):
        from tools.llm_client import parse_json
        assert parse_json('{"a": 1}') == {"a": 1}

    def test_fenced_json(self):
        from tools.llm_client import parse_json
        assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}

    def test_bare_fence(self):
        from tools.llm_client import parse_json
        assert parse_json('```\n{"a": 1}\n```') == {"a": 1}

    def test_fence_with_surrounding_whitespace(self):
        from tools.llm_client import parse_json
        assert parse_json('\n  ```json\n{"a": 1}\n```  \n') == {"a": 1}

    def test_invalid_returns_default(self):
        from tools.llm_client import parse_json
        sentinel = {"fallback": True}
        assert parse_json("not json", default=sentinel) is sentinel
        assert parse_json("", default=sentinel) is sentinel


class TestScorecardNormalization:
    """Scores drive UI colour thresholds and ranking, so they must be sane."""

    def test_clamps_out_of_range_dimensions(self):
        from agents.memo_agent import _normalize_scorecard

        sc = _normalize_scorecard({
            "market_size_score": 99, "team_score": -4, "traction_score": "7",
            "competitive_moat_score": None, "financial_health_score": 8,
            "overall_score": 42, "recommendation": "invest",
        })
        assert sc["market_size_score"] == 10
        assert sc["team_score"] == 1
        assert sc["traction_score"] == 7
        assert sc["competitive_moat_score"] == 5
        assert sc["recommendation"] == "INVEST"

    def test_recomputes_nonsensical_overall(self):
        from agents.memo_agent import _normalize_scorecard

        sc = _normalize_scorecard({
            "market_size_score": 8, "team_score": 8, "traction_score": 8,
            "competitive_moat_score": 8, "financial_health_score": 8,
            "overall_score": 99,
        })
        assert sc["overall_score"] == 8.0

    def test_unknown_recommendation_falls_back(self):
        from agents.memo_agent import _normalize_scorecard
        assert _normalize_scorecard({"recommendation": "MAYBE"})["recommendation"] == "CONSIDER"

    def test_non_list_strengths_coerced(self):
        from agents.memo_agent import _normalize_scorecard
        sc = _normalize_scorecard({"key_strengths": "a string", "key_risks": None})
        assert sc["key_strengths"] == [] and sc["key_risks"] == []


class TestAgentNodeImports:
    """Smoke tests that every node is importable and awaitable."""

    def test_all_nodes_are_coroutines(self):
        import inspect

        from agents.comps_agent import comps_node
        from agents.financials_agent import financials_node
        from agents.ingestion_agent import ingest_node
        from agents.memo_agent import memo_node, score_node
        from agents.orchestrator import grade_node, rewrite_node
        from agents.risk_agent import risk_node

        from agents.competitors_agent import competitors_node
        from agents.founders_agent import founders_node

        for fn in (ingest_node, comps_node, financials_node, risk_node,
                   founders_node, competitors_node,
                   grade_node, rewrite_node, score_node, memo_node):
            assert inspect.iscoroutinefunction(fn), f"{fn.__name__} must be async"


class TestModelPins:
    """Plan section 12: exact model strings, no `latest` aliases anywhere."""

    def test_model_ids_pinned(self):
        from tools.llm_client import EMBED, LAST_RESORT_MODEL, PRIMARY
        assert PRIMARY == "openrouter:google/gemini-3.1-flash-lite"
        assert LAST_RESORT_MODEL == "gemini-3.6-flash"
        assert EMBED == "gemini-embedding-001"

    def test_no_latest_aliases_in_source(self):
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        offenders = []
        # Skip tests/ — this file necessarily contains the forbidden strings.
        for path in root.rglob("*.py"):
            if {"venv", "node_modules", "tests"} & set(path.parts):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            # 2.5 ids are retired for new API keys; `latest` aliases hot-swap under you.
            for pattern in ("gemini-flash-latest", "gemini-pro-latest", "gemini-1.5",
                            "gemini-2.0", "gemini-2.5"):
                if pattern in text:
                    offenders.append(f"{path.name}: {pattern}")
        assert not offenders, f"Forbidden model aliases found: {offenders}"


class TestModelFailover:
    """Free tier caps generate at 20/day PER MODEL, so one model can be spent
    while its siblings still have headroom. A quota 429 must fail over, not fail."""

    def test_falls_over_to_the_next_model_on_429(self, monkeypatch):
        import tools.llm_client as llm

        calls = []

        class _Models:
            def generate_content(self, *, model, contents, config=None):
                calls.append(model)
                if model == "gemini-3.6-flash":
                    raise RuntimeError("429 RESOURCE_EXHAUSTED quota exceeded")
                return type("R", (), {"text": "recovered"})()

        monkeypatch.setattr(llm, "get_client", lambda: type("C", (), {"models": _Models()})())
        assert llm.generate("hi") == "recovered"
        assert calls == ["gemini-3.6-flash", "gemini-3.1-flash-lite"]

    def test_non_quota_errors_are_not_retried(self, monkeypatch):
        import tools.llm_client as llm

        calls = []

        class _Models:
            def generate_content(self, *, model, contents, config=None):
                calls.append(model)
                raise RuntimeError("400 INVALID_ARGUMENT")

        monkeypatch.setattr(llm, "get_client", lambda: type("C", (), {"models": _Models()})())
        with pytest.raises(RuntimeError, match="INVALID_ARGUMENT"):
            llm.generate("hi")
        assert len(calls) == 1, "a non-quota error must not burn the whole chain"

    def test_model_chain_is_deduped_and_primary_first(self):
        from config.settings import Settings

        s = Settings(primary_model="a", fallback_models="b, a ,c,")
        assert s.model_chain == ["a", "b", "c"]


class TestProviderChain:
    """Chain entries may name a provider; model ids themselves contain colons."""

    @pytest.mark.parametrize("entry,expected", [
        ("gemini-3.6-flash", ("gemini", "gemini-3.6-flash")),
        ("openrouter:openrouter/free", ("openrouter", "openrouter/free")),
        # The id has its own ":free" suffix — split must happen once, not greedily.
        ("openrouter:nvidia/nemotron-3-super-120b-a12b:free",
         ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free")),
        ("openrouter:openai/gpt-oss-20b:free", ("openrouter", "openai/gpt-oss-20b:free")),
    ])
    def test_split_model(self, entry, expected):
        from tools.llm_client import split_model

        assert split_model(entry) == expected

    def test_openrouter_legs_dropped_without_a_key(self, monkeypatch):
        """An unusable leg would raise on every call and waste the failover."""
        import tools.llm_client as llm
        from tools import openrouter

        monkeypatch.setattr(openrouter, "is_configured", lambda: False)
        assert all(not e.startswith("openrouter:") for e in llm.usable_chain())

    def test_openrouter_legs_kept_with_a_key(self, monkeypatch):
        import tools.llm_client as llm
        from tools import openrouter

        monkeypatch.setattr(openrouter, "is_configured", lambda: True)
        assert any(e.startswith("openrouter:") for e in llm.usable_chain())

    def test_chain_never_empties(self, monkeypatch):
        import tools.llm_client as llm
        from config.settings import settings
        from tools import openrouter

        monkeypatch.setattr(openrouter, "is_configured", lambda: False)
        monkeypatch.setattr(settings, "primary_model", "openrouter:a/b:free")
        monkeypatch.setattr(settings, "fallback_models", "openrouter:c/d:free")
        assert llm.usable_chain() == [llm.LAST_RESORT_MODEL]

    def test_gemini_quota_fails_over_to_openrouter(self, monkeypatch):
        """The whole point: a spent Gemini day continues on another vendor."""
        import tools.llm_client as llm
        from tools import openrouter

        monkeypatch.setattr(openrouter, "is_configured", lambda: True)
        monkeypatch.setattr(openrouter, "generate",
                            lambda model, prompt, system="", json_mode=False: f"via {model}")

        class _Models:
            def generate_content(self, *, model, contents, config=None):
                raise RuntimeError("429 RESOURCE_EXHAUSTED")

        monkeypatch.setattr(llm, "get_client", lambda: type("C", (), {"models": _Models()})())
        out = llm.generate("hi")
        assert out.startswith("via "), f"expected an OpenRouter answer, got {out!r}"

    def test_openrouter_402_counts_as_quota(self):
        """OpenRouter returns 402 when a free-tier daily cap is hit, not 429."""
        import httpx

        from tools.openrouter import is_quota_error

        resp = httpx.Response(402, request=httpx.Request("POST", "https://x.test"))
        assert is_quota_error(httpx.HTTPStatusError("payment required", request=resp.request, response=resp))


class TestOpenRouterPayload:
    """Reasoning models stream chain-of-thought in `delta.reasoning` and leave
    `delta.content` empty until they finish, which freezes an interactive UI."""

    def test_streaming_disables_reasoning(self):
        from tools.openrouter import _payload

        body = _payload("m", "p", "", json_mode=False, stream=True, reasoning=False)
        assert body["reasoning"] == {"enabled": False}
        assert body["stream"] is True

    def test_background_calls_keep_reasoning(self):
        from tools.openrouter import _payload

        body = _payload("m", "p", "", json_mode=True, stream=False)
        assert "reasoning" not in body, "background analysis should keep reasoning on"
        assert body["response_format"] == {"type": "json_object"}

    def test_system_prompt_becomes_a_message(self):
        from tools.openrouter import _payload

        body = _payload("m", "hello", "be terse", json_mode=False, stream=False)
        assert body["messages"] == [
            {"role": "system", "content": "be terse"},
            {"role": "user", "content": "hello"},
        ]

    def test_inband_error_raises(self):
        """OpenRouter reports upstream provider failures with HTTP 200."""
        from tools.openrouter import _extract

        with pytest.raises(RuntimeError, match="OpenRouter error"):
            _extract({"choices": [], "error": {"message": "upstream is down"}})
