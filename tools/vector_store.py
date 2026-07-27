"""
ChromaDB persistent vector store with hybrid dense + sparse (BM25) retrieval
fused by Reciprocal Rank Fusion.

Two collections are kept deliberately separate:

  vc_comps      — the benchmark corpus of comparable deals (seeded once)
  vc_documents  — chunks of user-uploaded pitch decks and scraped reports

Mixing them means an uploaded deck is returned as a "comparable deal" for the
next upload, and a company ends up benchmarked against itself.
"""
import threading
from typing import Any

import chromadb
from loguru import logger
from rank_bm25 import BM25Okapi

from config.settings import settings
from tools.llm_client import embed

COMPS_COLLECTION = "vc_comps"
DOCS_COLLECTION = "vc_documents"

client = chromadb.PersistentClient(path=str(settings.chroma_path))

comps_col = client.get_or_create_collection(COMPS_COLLECTION)
docs_col = client.get_or_create_collection(DOCS_COLLECTION)

# Backwards-compatible alias used by the health check.
col = comps_col

# ── BM25 index cache ──────────────────────────────────────────────────────────
# Rebuilding BM25 over the entire corpus on every query is O(N) per request.
# Cache per collection and invalidate on write.
_bm25_cache: dict[str, tuple[list[str], list[str], BM25Okapi]] = {}
_cache_lock = threading.Lock()


def _invalidate(collection_name: str) -> None:
    with _cache_lock:
        _bm25_cache.pop(collection_name, None)


def _get_bm25(collection) -> tuple[list[str], list[str], BM25Okapi] | None:
    """Return (ids, documents, bm25) for a collection, building the index once."""
    name = collection.name
    with _cache_lock:
        cached = _bm25_cache.get(name)
        if cached is not None:
            return cached

    data = collection.get()
    ids = data.get("ids") or []
    docs = data.get("documents") or []
    if not ids or not docs:
        return None

    bm25 = BM25Okapi([d.split() for d in docs])
    entry = (ids, docs, bm25)
    with _cache_lock:
        _bm25_cache[name] = entry
    logger.info(f"Built BM25 index for '{name}' over {len(ids)} documents.")
    return entry


# ── Writes ────────────────────────────────────────────────────────────────────


def _upsert(collection, ids: list[str], texts: list[str], metadatas: list[dict]) -> int:
    """Embed and upsert a batch. Returns the number of records written."""
    if not ids:
        return 0

    vecs = embed(texts, task_type="RETRIEVAL_DOCUMENT")
    if len(vecs) != len(texts):
        logger.error(f"Embedding failed for batch into '{collection.name}'.")
        raise RuntimeError("Failed to generate embeddings for upsert batch.")

    # chromadb rejects empty metadata dicts outright, which would surface as a
    # 500 mid-ingestion. Guarantee at least one key.
    metadatas = [m if m else {"source": collection.name} for m in metadatas]

    collection.upsert(ids=ids, embeddings=vecs, documents=texts, metadatas=metadatas)
    _invalidate(collection.name)
    logger.success(f"Upserted {len(ids)} record(s) into '{collection.name}'.")
    return len(ids)


def upsert_comp(doc_id: str, text: str, metadata: dict) -> None:
    """Upsert a single comparable deal into the benchmark corpus."""
    _upsert(comps_col, [doc_id], [text], [metadata])


def upsert_comps(comps: list[tuple[str, str, dict]], batch_size: int = 100) -> int:
    """Batch-upsert comparable deals as (id, text, metadata) tuples.

    Writes to the COMPS collection — not the documents collection that
    `upsert_chunks` targets. Embeds in batches so a large seed is a handful of
    API calls rather than one per record.
    """
    if not comps:
        return 0
    written = 0
    for start in range(0, len(comps), batch_size):
        batch = comps[start : start + batch_size]
        written += _upsert(
            comps_col,
            [c[0] for c in batch],
            [c[1] for c in batch],
            [c[2] for c in batch],
        )
    return written


def upsert_chunks(chunks: list[tuple[str, str, dict]]) -> int:
    """Upsert document chunks as (id, text, metadata) tuples.

    Embeds in one batched call rather than one API round-trip per chunk.
    """
    if not chunks:
        return 0
    ids = [c[0] for c in chunks]
    texts = [c[1] for c in chunks]
    metas = [c[2] for c in chunks]
    return _upsert(docs_col, ids, texts, metas)


def delete_by_file_id(file_id: str) -> int:
    """Delete every document chunk belonging to a file. Returns count deleted."""
    data = docs_col.get(where={"file_id": file_id})
    ids = data.get("ids") or []
    if ids:
        docs_col.delete(ids=ids)
        _invalidate(DOCS_COLLECTION)
        logger.info(f"Deleted {len(ids)} chunk(s) for file_id={file_id}.")
    return len(ids)


# ── Retrieval ─────────────────────────────────────────────────────────────────


def rrf(dense_ids: list[str], sparse_ids: list[str], k: int = 60) -> list[str]:
    """Reciprocal Rank Fusion over two ranked ID lists."""
    scores: dict[str, float] = {}
    for rank, id_ in enumerate(dense_ids):
        scores[id_] = scores.get(id_, 0.0) + 1.0 / (k + rank)
    for rank, id_ in enumerate(sparse_ids):
        scores[id_] = scores.get(id_, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda i: scores[i], reverse=True)


def _hybrid_query(collection, text: str, n: int, filter_dict: dict | None) -> list[dict]:
    logger.info(f"Querying '{collection.name}': '{text[:80]}' (n={n}, filter={filter_dict})")

    index = _get_bm25(collection)
    if index is None:
        logger.warning(f"Collection '{collection.name}' is empty. Returning no results.")
        return []
    all_ids, all_docs, bm25 = index

    # Dense leg — note the query task type differs from the document task type.
    vecs = embed([text], task_type="RETRIEVAL_QUERY")
    if not vecs:
        logger.error("Failed to embed query text.")
        return []

    dense = collection.query(
        query_embeddings=[vecs[0]],
        n_results=min(n * 2, len(all_ids)),
        where=filter_dict or None,
    )
    dense_ids = (dense.get("ids") or [[]])[0]

    # Sparse leg.
    sparse_scores = bm25.get_scores(text.split())
    top_sparse = sorted(
        range(len(sparse_scores)), key=lambda i: sparse_scores[i], reverse=True
    )[: min(n * 2, len(all_ids))]
    sparse_ids = [all_ids[i] for i in top_sparse]

    # The BM25 index spans the whole collection, so drop anything the metadata
    # filter excludes before fusing.
    if filter_dict:
        allowed = set((collection.get(where=filter_dict).get("ids") or []))
        sparse_ids = [i for i in sparse_ids if i in allowed]

    merged_ids = rrf(dense_ids, sparse_ids)[:n]
    if not merged_ids:
        return []

    # chromadb's get() returns rows in its own internal order, NOT the order of
    # the requested ids — reindex by id to preserve the RRF ranking.
    fetched = collection.get(ids=merged_ids)
    by_id = {
        i: {"id": i, "text": d, "meta": m or {}}
        for i, d, m in zip(
            fetched.get("ids") or [],
            fetched.get("documents") or [],
            fetched.get("metadatas") or [],
        )
    }

    results = [by_id[i] for i in merged_ids if i in by_id]
    logger.success(f"Retrieved {len(results)} document(s) from '{collection.name}'.")
    return results


def query_comps(text: str, n: int | None = None) -> list[dict]:
    """Search the comparable-deals benchmark corpus."""
    return _hybrid_query(comps_col, text, n or settings.top_k_results, None)


def query_documents(
    text: str, n: int | None = None, file_id: str | None = None
) -> list[dict]:
    """Search uploaded document chunks, optionally scoped to one file."""
    return _hybrid_query(
        docs_col,
        text,
        n or settings.top_k_results,
        {"file_id": file_id} if file_id else None,
    )


def health() -> dict[str, int]:
    """Return record counts per collection. Used by /health."""
    return {COMPS_COLLECTION: comps_col.count(), DOCS_COLLECTION: docs_col.count()}
