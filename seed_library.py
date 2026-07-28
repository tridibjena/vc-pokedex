"""
Load the sample VC documents into the reference library for RAG chat.

    python seed_library.py                  # index everything in samples/
    python seed_library.py --dir ~/decks    # index your own directory
    python seed_library.py --dry-run        # parse and report, no embedding calls
    python seed_library.py --replace        # re-index documents already present

Writes to the `vc_documents` Chroma collection and the `library` Mongo
collection — the same path an upload takes through POST /library/documents, so
what you get here is exactly what the UI produces.

This is NOT the comps corpus. Comparable-deal retrieval runs against real SEC
Form D filings in `vc_comps`; see seed_edgar.py and SEEDING.md. Every company
in samples/ is fictional and must never be used as a benchmark.
"""
import argparse
import asyncio
import sys
import uuid
from pathlib import Path

from loguru import logger

from config.settings import settings
from tools.chroma_guard import ensure_exclusive_access
from tools.chunking import chunk_text
from tools.documents import (
    SUPPORTED_SUFFIXES,
    UnreadableDocument,
    UnsupportedDocument,
    extract,
)
from tools.mongo_client import STATUS_COMPLETE, db, mongo_client
from tools.vector_store import delete_by_file_id, docs_col, upsert_chunks

SAMPLES_DIR = Path(__file__).parent / "samples"
# samples/README.md documents the corpus rather than being part of it.
SKIP_NAMES = {"readme.md"}


def discover(directory: Path) -> list[Path]:
    """Every supported document in a directory, sorted for stable dex order."""
    if not directory.is_dir():
        raise SystemExit(f"Not a directory: {directory}")
    return sorted(
        p
        for p in directory.iterdir()
        if p.is_file()
        and p.suffix.lower() in SUPPORTED_SUFFIXES
        and p.name.lower() not in SKIP_NAMES
    )


async def index_one(path: Path, *, replace: bool, dry_run: bool) -> dict | None:
    """Extract, chunk and index one file. Returns a summary, or None if skipped."""
    try:
        text = extract(path.name, path.read_bytes())
    except (UnsupportedDocument, UnreadableDocument) as exc:
        logger.error(f"{path.name}: {exc}")
        return None

    chunks = chunk_text(text)

    existing = await db.library.find_one({"filename": path.name})
    if existing and not replace:
        logger.info(f"{path.name}: already in the library, skipping (--replace to redo)")
        return None

    if dry_run:
        logger.info(f"{path.name}: {len(text)} chars -> {len(chunks)} chunk(s)")
        return {"filename": path.name, "chunks": len(chunks), "chars": len(text)}

    # Replacing means dropping the old chunks first — upsert alone would leave
    # orphans behind whenever the new text produces fewer chunks than the old.
    if existing:
        old_id = existing.get("file_id")
        if old_id:
            await asyncio.to_thread(delete_by_file_id, old_id)
        await db.library.delete_one({"_id": existing["_id"]})

    file_id = str(uuid.uuid4())
    try:
        (settings.upload_path / f"{file_id}.txt").write_text(text, encoding="utf-8")
    except OSError as exc:
        logger.warning(f"{path.name}: could not cache text ({exc})")

    payload = [
        (
            f"{file_id}_{i}",
            chunk,
            {
                "file_id": file_id,
                "company_name": path.name,
                "source": "library",
                "kind": "library",
            },
        )
        for i, chunk in enumerate(chunks)
    ]

    stored = await asyncio.to_thread(upsert_chunks, payload)
    await mongo_client.save_library_doc(
        {
            "file_id": file_id,
            "filename": path.name,
            "size_bytes": path.stat().st_size,
            "chars": len(text),
            "status": STATUS_COMPLETE,
            "chunks": stored,
            "seeded": True,
        }
    )
    logger.success(f"{path.name}: {stored} chunk(s) indexed")
    return {"filename": path.name, "chunks": stored, "chars": len(text)}


async def run(directory: Path, *, replace: bool, dry_run: bool) -> int:
    files = discover(directory)
    if not files:
        logger.warning(f"No supported documents in {directory}")
        return 1

    logger.info(f"Found {len(files)} document(s) in {directory}")

    before = docs_col.count()
    results = []
    for path in files:
        # Sequential on purpose: embedding is metered per item on the free tier
        # (100/min), so parallelism here only queues behind the rate limiter.
        result = await index_one(path, replace=replace, dry_run=dry_run)
        if result:
            results.append(result)

    if dry_run:
        total = sum(r["chunks"] for r in results)
        print(f"\n--- DRY RUN: {len(results)} document(s), {total} chunk(s) ---\n")
        for r in results:
            print(f"  {r['filename']:<44} {r['chars']:>7,} chars  {r['chunks']:>3} chunks")
        return 0

    after = docs_col.count()
    logger.success(
        f"Indexed {len(results)} document(s) into '{docs_col.name}' "
        f"({before} -> {after}, +{after - before} chunks)"
    )
    if results:
        logger.info("Open RAG Chat and pick one under Sources to scope a question to it.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, default=SAMPLES_DIR,
                        help="directory to index (default: samples/)")
    parser.add_argument("--replace", action="store_true",
                        help="re-index documents whose filename is already present")
    parser.add_argument("--dry-run", action="store_true",
                        help="parse and report without embedding or writing")
    parser.add_argument("--allow-running-api", action="store_true",
                        help="seed even if the API server is running (leaves it stale)")
    args = parser.parse_args()

    if not args.dry_run:
        ensure_exclusive_access(force=args.allow_running_api)

    return asyncio.run(run(args.dir, replace=args.replace, dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
