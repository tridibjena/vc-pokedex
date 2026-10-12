"""
Geocoding for the Dex map.

Nominatim is faked at the HTTP boundary (httpx.MockTransport) and Mongo with
in-memory collections, so the real pacing, caching and fallback logic runs.
"""
from datetime import datetime, timezone

import httpx
import pytest

from tools import geocode


class FakeCollection:
    def __init__(self, docs=None):
        self.docs = {d["_id"]: dict(d) for d in (docs or [])}

    async def find_one(self, query, projection=None):
        return self.docs.get(query.get("_id"))

    async def update_one(self, query, update, upsert=False):
        doc = self.docs.get(query["_id"])
        if doc is None:
            if not upsert:
                return
            doc = self.docs[query["_id"]] = {"_id": query["_id"]}
        doc.update(update["$set"])

    def find(self, query, projection=None):
        unchecked = [d for d in self.docs.values() if "geo_checked_at" not in d]

        class _Cursor:
            async def to_list(self, n):
                return unchecked[:n]

        return _Cursor()


class FakeDB:
    def __init__(self, deals=None):
        self.geocache = FakeCollection()
        self.deals = FakeCollection(deals)


@pytest.fixture
def fake_db(monkeypatch):
    db = FakeDB()
    monkeypatch.setattr(geocode, "db", db)
    return db


@pytest.fixture
def enabled(monkeypatch):
    from config.settings import settings

    monkeypatch.setattr(settings, "geocoding_enabled", True)


@pytest.fixture
def nominatim(monkeypatch):
    """Route httpx to a fake Nominatim and record what it was asked."""
    calls: list[httpx.Request] = []
    answers: dict[str, list] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        q = request.url.params.get("q", "")
        if q == "boom":
            return httpx.Response(503, text="overloaded")
        return httpx.Response(200, json=answers.get(q, []))

    real = httpx.AsyncClient

    def client(*args, **kwargs):
        return real(*args, transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(geocode.httpx, "AsyncClient", client)

    # Real pacing would sleep ~1s between calls; record instead.
    slept: list[float] = []

    async def _sleep(s):
        slept.append(s)

    monkeypatch.setattr(geocode.asyncio, "sleep", _sleep)
    monkeypatch.setattr(geocode, "_last_call", 0.0)

    calls_ns = type("N", (), {"calls": calls, "answers": answers, "slept": slept})
    return calls_ns


BLR = [{"lat": "12.9716", "lon": "77.5946", "display_name": "Bengaluru, Karnataka, India",
        "addresstype": "city"}]
OFFICE = [{"lat": "12.9352", "lon": "77.6245", "display_name": "80 Feet Rd, Koramangala",
           "addresstype": "road"}]


class TestHelpers:
    @pytest.mark.parametrize("q", ["Unknown", "  unknown ", "N/A", "", None, "Remote", 42])
    def test_placeholders_are_not_geocoded(self, q):
        assert not geocode.is_usable(q)

    def test_real_places_are(self):
        assert geocode.is_usable("Bengaluru, India")

    @pytest.mark.parametrize("kind,expected", [
        ("city", "city"), ("town", "city"), ("state", "region"), ("country", "country"),
        ("suburb", "area"), ("road", "address"), ("building", "address"), (None, "address"),
    ])
    def test_precision(self, kind, expected):
        assert geocode.precision_of(kind) == expected


@pytest.mark.asyncio
class TestGeocode:
    async def test_parses_nominatim_and_identifies_itself(self, fake_db, enabled, nominatim):
        nominatim.answers["Bengaluru, India"] = BLR
        hit = await geocode.geocode("Bengaluru, India")

        assert hit == {"lat": 12.9716, "lng": 77.5946,
                       "label": "Bengaluru, Karnataka, India", "kind": "city"}
        req = nominatim.calls[0]
        assert req.url.params["format"] == "jsonv2"
        assert req.headers["user-agent"].startswith("VCPokedex"), \
            "Nominatim's usage policy requires an identifying User-Agent"

    async def test_hits_and_misses_are_cached(self, fake_db, enabled, nominatim):
        nominatim.answers["Bengaluru, India"] = BLR
        await geocode.geocode("Bengaluru, India")
        await geocode.geocode("  bengaluru,   INDIA ")   # same key once normalized
        assert await geocode.geocode("Atlantis") is None
        assert await geocode.geocode("Atlantis") is None

        assert len(nominatim.calls) == 2, "each place is looked up once, ever"

    async def test_transient_failure_raises_and_is_not_cached(self, fake_db, enabled, nominatim):
        with pytest.raises(geocode.GeocoderUnavailable):
            await geocode.geocode("boom")
        assert "boom" not in fake_db.geocache.docs, \
            "caching a 503 would leave the company unpinned forever"

    async def test_requests_are_paced(self, fake_db, enabled, nominatim):
        await geocode.geocode("first place")
        await geocode.geocode("second place")
        # The first call has nothing to wait for; the second, issued immediately
        # after, must wait out (almost) the whole interval.
        assert len(nominatim.slept) == 1
        assert 0.9 * geocode.MIN_INTERVAL_S < nominatim.slept[0] <= geocode.MIN_INTERVAL_S

    async def test_disabled_makes_no_calls(self, fake_db, nominatim):
        assert await geocode.geocode("Bengaluru, India") is None
        assert nominatim.calls == []


@pytest.mark.asyncio
class TestLocate:
    async def test_address_wins_over_city(self, fake_db, enabled, nominatim):
        nominatim.answers["80 Feet Rd, Koramangala"] = OFFICE
        nominatim.answers["Bengaluru, India"] = BLR
        geo = await geocode.locate({"hq_address": "80 Feet Rd, Koramangala",
                                    "hq_location": "Bengaluru, India"})
        assert (geo["lat"], geo["precision"]) == (12.9352, "address")

    async def test_falls_back_to_city_when_address_misses(self, fake_db, enabled, nominatim):
        nominatim.answers["Bengaluru, India"] = BLR
        geo = await geocode.locate({"hq_address": "Suite 9, Nowhere Plaza",
                                    "hq_location": "Bengaluru, India"})
        assert geo["precision"] == "city"
        assert geo["query"] == "Bengaluru, India"

    async def test_unknown_location_is_not_pinned(self, fake_db, enabled, nominatim):
        assert await geocode.locate({"hq_location": "Unknown"}) is None
        assert nominatim.calls == []


@pytest.mark.asyncio
class TestBackfill:
    async def test_pins_unchecked_deals_and_marks_misses(self, monkeypatch, enabled, nominatim):
        db = FakeDB(deals=[
            {"_id": "a", "metadata": {"hq_location": "Bengaluru, India"}},
            {"_id": "b", "metadata": {"hq_location": "Atlantis"}},
            {"_id": "c", "metadata": {}, "geo_checked_at": datetime.now(timezone.utc)},
        ])
        monkeypatch.setattr(geocode, "db", db)
        nominatim.answers["Bengaluru, India"] = BLR

        assert await geocode.backfill() == 1
        assert db.deals.docs["a"]["geo"]["lat"] == 12.9716
        assert db.deals.docs["b"]["geo"] is None and "geo_checked_at" in db.deals.docs["b"], \
            "a confirmed miss is recorded so it is not retried every start"

    async def test_stops_without_marking_on_outage(self, monkeypatch, enabled, nominatim):
        db = FakeDB(deals=[
            {"_id": "a", "metadata": {"hq_location": "boom"}},
            {"_id": "b", "metadata": {"hq_location": "Bengaluru, India"}},
        ])
        monkeypatch.setattr(geocode, "db", db)

        assert await geocode.backfill() == 0
        assert all("geo_checked_at" not in d for d in db.deals.docs.values())

    async def test_quiet_wrapper_swallows_errors(self, monkeypatch, enabled):
        async def broken():
            raise RuntimeError("mongo is down")

        monkeypatch.setattr(geocode, "backfill", broken)
        await geocode.backfill_quietly()  # must not raise


@pytest.mark.asyncio
class TestPipelineIntegration:
    """Geocoding is a side-car to the analysis — it can add a pin, never fail it."""

    @pytest.fixture
    def pipeline(self, monkeypatch):
        import pipelines.analysis_pipeline as ap

        stored: dict = {}

        async def run(**kwargs):
            return {"metadata": {"company_name": "Acme", "hq_location": "Bengaluru, India"},
                    "scorecard": {"overall_score": 7.0}, "memo": "m"}

        async def insert_deal(data):
            stored.update(data)
            return "deal1"

        async def save_report(data):
            return "rep1"

        monkeypatch.setattr(ap.orchestrator, "run", run)
        monkeypatch.setattr(ap.mongo_client, "insert_deal", insert_deal)
        monkeypatch.setattr(ap.mongo_client, "save_report", save_report)
        # Motor hands out a fresh Collection per attribute access, so patching
        # a method on `db.deals` would not stick — replace the database instead.
        monkeypatch.setattr(ap, "db", FakeDB())
        return ap, stored

    async def test_pin_is_stored_on_the_deal(self, pipeline, monkeypatch):
        ap, stored = pipeline

        async def locate(meta):
            return {"lat": 1.0, "lng": 2.0, "precision": "city", "query": "q", "label": ""}

        monkeypatch.setattr(ap, "locate", locate)
        res = await ap.analysis_pipeline.analyze_company("text", "f1", "Acme")

        assert res["success"]
        assert stored["geo"]["lat"] == 1.0 and "geo_checked_at" in stored

    async def test_geocoder_outage_does_not_fail_the_analysis(self, pipeline, monkeypatch):
        ap, stored = pipeline

        async def locate(meta):
            raise geocode.GeocoderUnavailable("down")

        monkeypatch.setattr(ap, "locate", locate)
        res = await ap.analysis_pipeline.analyze_company("text", "f1", "Acme")

        assert res["success"]
        assert "geo_checked_at" not in stored, "left unchecked so the backfill retries it"


class TestDealCard:
    def test_card_carries_pin_and_case(self):
        from api.routes.reports import _deal_card

        card = _deal_card({
            "_id": "d1", "company_name": "Acme", "sector": "SaaS", "stage": "seed",
            "metadata": {"hq_location": "Bengaluru, India", "product_description": "Ledgers."},
            "scorecard": {"key_strengths": ["Team", "", 3, "Growth"], "key_risks": ["Churn"],
                          "team_score": 8},
            "geo": {"lat": 12.97, "lng": 77.59, "precision": "city"},
        })
        assert (card.lat, card.lng, card.geo_precision) == (12.97, 77.59, "city")
        assert card.hq_location == "Bengaluru, India"
        assert card.product == "Ledgers."
        assert card.strengths == ["Team", "Growth"], "blanks and non-strings are dropped"
        assert card.risks == ["Churn"]
        assert card.scores == {"team_score": 8}

    def test_unpinned_deal_has_no_coordinates(self):
        from api.routes.reports import _deal_card

        card = _deal_card({"_id": "d2", "company_name": "Ghost", "geo": None})
        assert card.lat is None and card.lng is None
        assert card.strengths == [] and card.risks == []
