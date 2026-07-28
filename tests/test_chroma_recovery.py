"""
Concurrent-writer hazard: ChromaDB's PersistentClient is single-process.

Seeding while the API is live leaves the server with a stale index. It fails
hard (`InternalError: Error finding id`, 500 on every chat request until
restart) or soft (cached BM25 ids point at deleted rows, so retrieval quietly
returns fewer results). Both are covered here.
"""
import pytest

from tools import chroma_guard, vector_store


class TestGuard:
    def test_allows_seeding_when_the_api_is_down(self, monkeypatch):
        monkeypatch.setattr(chroma_guard, "api_is_running", lambda url=None: False)
        chroma_guard.ensure_exclusive_access()  # must not raise

    def test_aborts_when_the_api_is_live(self, monkeypatch):
        monkeypatch.setattr(chroma_guard, "api_is_running", lambda url=None: True)
        with pytest.raises(SystemExit) as exc:
            chroma_guard.ensure_exclusive_access()
        message = str(exc.value)
        # The message has to say what to actually do, not just refuse.
        assert "pkill" in message
        # And the override it names must be the flag the seeders really accept.
        assert chroma_guard.OVERRIDE_FLAG in message

    def test_the_advertised_override_flag_is_what_the_seeders_accept(self):
        """Regression: the message said --force while the flag was
        --allow-running-api, so following the instructions did nothing."""
        import subprocess
        import sys

        for script in ("seed_library.py", "seed_edgar.py"):
            help_text = subprocess.run(
                [sys.executable, script, "--help"], capture_output=True, text=True
            ).stdout
            assert chroma_guard.OVERRIDE_FLAG in help_text, script

    def test_force_downgrades_the_abort_to_a_warning(self, monkeypatch):
        monkeypatch.setattr(chroma_guard, "api_is_running", lambda url=None: True)
        chroma_guard.ensure_exclusive_access(force=True)  # must not raise

    def test_unreachable_host_is_treated_as_not_running(self):
        # A closed port must not block seeding on a machine with no server.
        assert chroma_guard.api_is_running("http://127.0.0.1:9/health") is False


class _FakeCollection:
    def __init__(self, name, fail_times=0):
        self.name = name
        self.fail_times = fail_times
        self.queries = 0

    def get(self, **kwargs):
        return {
            "ids": ["a", "b"],
            "documents": ["burn multiple text", "runway text"],
            "metadatas": [{"file_id": "f"}, {"file_id": "f"}],
        }

    def query(self, **kwargs):
        self.queries += 1
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("Error executing plan: Internal error: Error finding id")
        return {"ids": [["a", "b"]]}


class TestRetry:
    @pytest.fixture(autouse=True)
    def _fake_embed(self, monkeypatch):
        monkeypatch.setattr(vector_store, "embed", lambda texts, task_type=None: [[1.0, 0.0]])

    def test_stale_handle_recovers_on_a_fresh_one(self, monkeypatch):
        stale = _FakeCollection("vc_documents", fail_times=1)
        fresh = _FakeCollection("vc_documents")
        monkeypatch.setattr(vector_store.client, "get_collection", lambda name: fresh)

        results = vector_store._hybrid_query(stale, "burn multiple", 2, None)

        assert [r["id"] for r in results] == ["a", "b"]
        assert stale.queries == 1 and fresh.queries == 1

    def test_reopen_rebinds_the_module_handle(self, monkeypatch):
        """Otherwise every later query pays a failure before retrying."""
        original = vector_store.docs_col
        fresh = _FakeCollection("vc_documents")
        monkeypatch.setattr(vector_store.client, "get_collection", lambda name: fresh)
        try:
            vector_store._reopen(_FakeCollection("vc_documents", fail_times=1))
            assert vector_store.docs_col is fresh
        finally:
            vector_store.docs_col = original

    def test_reopen_keeps_the_health_alias_in_sync(self, monkeypatch):
        original_comps, original_col = vector_store.comps_col, vector_store.col
        fresh = _FakeCollection("vc_comps")
        monkeypatch.setattr(vector_store.client, "get_collection", lambda name: fresh)
        try:
            vector_store._reopen(_FakeCollection("vc_comps"))
            assert vector_store.comps_col is fresh
            assert vector_store.col is fresh
        finally:
            vector_store.comps_col, vector_store.col = original_comps, original_col

    def test_persistent_failure_returns_empty_rather_than_raising(self, monkeypatch):
        """Chat degrades to answering without context; it must not 500."""
        stale = _FakeCollection("vc_documents", fail_times=99)
        monkeypatch.setattr(
            vector_store.client, "get_collection",
            lambda name: _FakeCollection("vc_documents", fail_times=99),
        )
        assert vector_store._hybrid_query(stale, "burn multiple", 2, None) == []
