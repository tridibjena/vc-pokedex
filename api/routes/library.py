"""
The reference library: user-uploaded documents that RAG chat can search.

Distinct from the Dex. A Dex entry is a company the agents researched and
scored; a library document is source material you brought yourself — a data
room export, a term sheet, an LP update, a market report. Both are chunked into
the same `vc_documents` Chroma collection, so chat can be scoped to either, but
only the Dex carries scorecards and memos.

Uploads return 202. Embedding is rate-limited (100 items/min on the free tier),
so a 40-page PDF is 60-odd chunks and well over a second of pacing; holding the
request open for that would time out the browser on a large file.
"""
import asyncio
import uuid

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from loguru import logger

from config.settings import settings
from tools.chunking import chunk_text
from tools.documents import (
    SUPPORTED_SUFFIXES,
    UnreadableDocument,
    UnsupportedDocument,
    extract,
)
from tools.mongo_client import (
    STATUS_COMPLETE,
    STATUS_FAILED,
    STATUS_PROCESSING,
    mongo_client,
)
from tools.vector_store import delete_by_file_id, upsert_chunks

router = APIRouter(prefix="/library", tags=["library"])

READ_CHUNK = 1024 * 1024


async def _read_capped(upload: UploadFile) -> bytes:
    """Read an upload, aborting past the configured cap.

    Streamed rather than `await upload.read()`: the unbounded form would pull a
    2 GB file fully into memory before we ever got to check its size.
    """
    limit = settings.max_upload_bytes
    buf = bytearray()
    while chunk := await upload.read(READ_CHUNK):
        buf.extend(chunk)
        if len(buf) > limit:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds the {settings.max_upload_size_mb} MB limit.",
            )
    return bytes(buf)


async def _index(file_id: str, filename: str, text: str) -> None:
    """Chunk, embed and record the outcome. Runs as a background task."""
    payload = [
        (
            f"{file_id}_{i}",
            chunk,
            {
                "file_id": file_id,
                "company_name": filename,
                "source": "library",
                "kind": "library",
            },
        )
        for i, chunk in enumerate(chunk_text(text))
    ]
    try:
        stored = await asyncio.to_thread(upsert_chunks, payload)
        await mongo_client.set_library_status(
            file_id, STATUS_COMPLETE, chunks=stored
        )
        logger.success(f"[Library] Indexed {stored} chunk(s) from '{filename}'.")
    except Exception as exc:
        logger.exception(f"[Library] Indexing failed for '{filename}': {exc}")
        await mongo_client.set_library_status(file_id, STATUS_FAILED, error=str(exc))


@router.post("/documents", status_code=202)
async def upload_document(background: BackgroundTasks, file: UploadFile = File(...)):
    """Upload a reference document and index it for RAG chat."""
    filename = (file.filename or "").strip() or "untitled"
    data = await _read_capped(file)

    try:
        text = extract(filename, data)
    except UnsupportedDocument as exc:
        raise HTTPException(status_code=415, detail=str(exc))
    except UnreadableDocument as exc:
        # 422: the type is accepted, this particular file just has no text.
        raise HTTPException(status_code=422, detail=str(exc))

    file_id = str(uuid.uuid4())

    # Keep the extracted text on disk rather than in Mongo: a long report is
    # comfortably under the 16 MB document cap but there is no reason to carry
    # it in every list query.
    try:
        (settings.upload_path / f"{file_id}.txt").write_text(text, encoding="utf-8")
    except OSError as exc:
        logger.error(f"[Library] Could not persist text for '{filename}': {exc}")

    await mongo_client.save_library_doc(
        {
            "file_id": file_id,
            "filename": filename,
            "size_bytes": len(data),
            "chars": len(text),
            "status": STATUS_PROCESSING,
            "chunks": 0,
        }
    )

    background.add_task(_index, file_id, filename, text)

    return {
        "success": True,
        "file_id": file_id,
        "filename": filename,
        "chars": len(text),
        "status": STATUS_PROCESSING,
        "message": "Uploaded. Indexing for chat in the background.",
    }


@router.get("/documents")
async def list_documents():
    """Every uploaded reference document, newest first."""
    try:
        docs = await mongo_client.list_library_docs()
        return {
            "documents": docs,
            "total": len(docs),
            "accepted": sorted(SUPPORTED_SUFFIXES),
            "max_mb": settings.max_upload_size_mb,
        }
    except Exception as exc:
        logger.error(f"[Library] List failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/documents/{file_id}")
async def delete_document(file_id: str):
    """Remove a reference document and every chunk embedded from it."""
    doc = await mongo_client.get_library_doc(file_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    try:
        removed = await asyncio.to_thread(delete_by_file_id, file_id)
    except Exception as exc:
        logger.error(f"[Library] Failed to delete chunks for {file_id}: {exc}")
        removed = 0

    # file_id is a server-minted UUID, never the client's filename, so this
    # cannot be steered outside the upload directory.
    cached = settings.upload_path / f"{file_id}.txt"
    if cached.is_file():
        cached.unlink(missing_ok=True)

    await mongo_client.delete_library_doc(file_id)

    return {
        "status": "success",
        "message": f"Removed '{doc.get('filename')}' and {removed} chunk(s).",
    }
