"""
Tests for hybrid retrieval: RRF fusion, result ordering, and corpus separation.
"""
import chromadb
import pytest

from tools import vector_store as vs


@pytest.fixture
def temp_collection(tmp_path, request):
    """A real (empty) Chroma collection backed by a temp dir."""
    client = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
    name = f"testcol-{abs(hash(request.node.name)) % 100000}"
    col = client.get_or_create_collection(name)
    yield col
    vs._invalidate(col.name)


class TestRRF:
    def test_documents_in_both_lists_rank_highest(self):
        merged = vs.rrf(["a", "b", "c"], ["b", "c", "d"])
        assert "b" in merged[:2]
        assert "c" in merged[:3]

    def test_returns_union_of_both_lists(self):
        assert set(vs.rrf(["a", "b"], ["c"])) == {"a", "b", "c"}

    def test_rank_one_in_both_wins(self):
        assert vs.rrf(["x", "y", "z"], ["x", "q"])[0] == "x"

    def test_empty_inputs(self):
        assert vs.rrf([], []) == []


class TestChromaGetOrdering:
    """The bug this guards: chromadb's get() ignores the requested id order."""

    def test_chroma_get_does_not_preserve_requested_order(self, temp_collection):
        col = temp_collection
        col.upsert(
            ids=[f"id{i}" for i in range(6)],
            embeddings=[[float(i), 0.0] for i in range(6)],
            documents=[f"doc{i}" for i in range(6)],
            metadatas=[{"k": "v"} for _ in range(6)],
        )
        requested = ["id4", "id1", "id5", "id0"]
        returned = col.get(ids=requested)["ids"]

        # If this ever starts passing, chromadb changed its contract — but the
        # reindex-by-id in _hybrid_query stays correct either way.
        assert returned != requested, "chromadb now preserves order; assumption changed"


class TestHybridQueryOrdering:
    def test_results_follow_rrf_rank_not_chroma_order(self, temp_collection, fake_gemini):
        col = temp_collection
        docs = [
            "series-a saas subscription collaborative workspace",
            "seed biotech gene editing therapeutics pipeline",
            "series-b fintech cross border payments api",
            "seed saas developer security scanning tool",
            "growth consumer marketplace refurbished electronics",
        ]
        col.upsert(
            ids=[f"d{i}" for i in range(len(docs))],
            embeddings=vs.embed(docs),
            documents=docs,
            metadatas=[{"i": i} for i in range(len(docs))],
        )
        vs._invalidate(col.name)

        results = vs._hybrid_query(col, "saas subscription workspace", n=3, filter_dict=None)

        assert results, "hybrid query returned nothing"
        assert [r["id"] for r in results] == sorted(
            [r["id"] for r in results],
            key=lambda i: [r["id"] for r in results].index(i),
        )
        # The strongest lexical + dense match must come first, not whichever id
        # chromadb happens to store first.
        assert results[0]["id"] == "d0"
        assert all("text" in r and "meta" in r for r in results)

    def test_metadata_filter_excludes_other_files(self, temp_collection, fake_gemini):
        col = temp_collection
        docs = ["alpha revenue growth metrics", "beta revenue growth metrics"]
        col.upsert(
            ids=["a1", "b1"],
            embeddings=vs.embed(docs),
            documents=docs,
            metadatas=[{"file_id": "A"}, {"file_id": "B"}],
        )
        vs._invalidate(col.name)

        results = vs._hybrid_query(col, "revenue growth", n=5, filter_dict={"file_id": "A"})

        assert [r["id"] for r in results] == ["a1"]

    def test_empty_collection_returns_empty(self, temp_collection, fake_gemini):
        assert vs._hybrid_query(temp_collection, "anything", n=5, filter_dict=None) == []


class TestCorpusSeparation:
    """Uploaded decks must not be returned as comparable deals."""

    def test_comps_and_documents_are_distinct_collections(self):
        assert vs.COMPS_COLLECTION != vs.DOCS_COLLECTION
        assert vs.comps_col.name == vs.COMPS_COLLECTION
        assert vs.docs_col.name == vs.DOCS_COLLECTION

    def test_query_comps_targets_the_comps_collection(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(vs, "_hybrid_query",
                            lambda c, t, n, f: seen.update(name=c.name, filter=f) or [])
        vs.query_comps("saas seed")
        assert seen["name"] == vs.COMPS_COLLECTION

    def test_query_documents_targets_the_docs_collection(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(vs, "_hybrid_query",
                            lambda c, t, n, f: seen.update(name=c.name, filter=f) or [])
        vs.query_documents("arr", file_id="f1")
        assert seen["name"] == vs.DOCS_COLLECTION
        assert seen["filter"] == {"file_id": "f1"}


class TestBM25Cache:
    def test_index_is_built_once_and_reused(self, temp_collection, fake_gemini):
        col = temp_collection
        col.upsert(
            ids=["x1", "x2"],
            embeddings=vs.embed(["alpha beta", "gamma delta"]),
            documents=["alpha beta", "gamma delta"],
            metadatas=[{"k": 1}, {"k": 2}],
        )
        vs._invalidate(col.name)

        first = vs._get_bm25(col)
        second = vs._get_bm25(col)
        assert first is second, "BM25 index was rebuilt instead of cached"

    def test_write_invalidates_the_cache(self, temp_collection, fake_gemini):
        col = temp_collection
        col.upsert(ids=["x1"], embeddings=vs.embed(["alpha"]),
                   documents=["alpha"], metadatas=[{"k": 1}])
        vs._invalidate(col.name)

        first = vs._get_bm25(col)
        vs._invalidate(col.name)          # what _upsert does after writing
        assert vs._get_bm25(col) is not first


class TestEmbeddingTaskTypes:
    """Gemini retrieval embeddings are asymmetric: queries and documents differ."""

    def test_query_uses_retrieval_query_task_type(self, temp_collection, fake_gemini, monkeypatch):
        col = temp_collection
        col.upsert(ids=["d1"], embeddings=vs.embed(["hello world"]),
                   documents=["hello world"], metadatas=[{"k": 1}])
        vs._invalidate(col.name)

        seen = []
        real_embed = vs.embed
        monkeypatch.setattr(vs, "embed",
                            lambda texts, task_type="RETRIEVAL_DOCUMENT": (
                                seen.append(task_type), real_embed(texts, task_type))[1])

        vs._hybrid_query(col, "hello", n=1, filter_dict=None)
        assert seen == ["RETRIEVAL_QUERY"]

    def test_upsert_uses_retrieval_document_task_type(self, monkeypatch):
        seen = []
        monkeypatch.setattr(vs, "embed",
                            lambda texts, task_type="RETRIEVAL_DOCUMENT": (
                                seen.append(task_type), [[0.1, 0.2]] * len(texts))[1])

        class _Col:
            name = "fake-collection"
            def upsert(self, **kw): pass

        vs._upsert(_Col(), ["i1"], ["text"], [{}])
        assert seen == ["RETRIEVAL_DOCUMENT"]
