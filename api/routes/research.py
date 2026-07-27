from fastapi import APIRouter, BackgroundTasks, HTTPException
from loguru import logger

from api.schemas import IngestStatusResponse, ResearchRequest, ResearchResponse
from pipelines.research_pipeline import research_pipeline
from tools.mongo_client import STATUS_PROCESSING, db, mongo_client
from tools.firms import get_firms
from tools.ticker import get_ticker
from tools.vector_store import delete_by_file_id
from tools.web_search import is_configured as tavily_configured

router = APIRouter(prefix="/research", tags=["research"])


@router.post("", response_model=ResearchResponse, status_code=202)
async def research_company_endpoint(request: ResearchRequest, background: BackgroundTasks):
    """Look a startup up by name: research it on the web, then score it.

    Returns 202 immediately; poll /ingest/status/{file_id} for the analysis.
    """
    if not tavily_configured():
        raise HTTPException(
            status_code=503,
            detail="Web research needs TAVILY_API_KEY. Set it in .env and restart.",
        )

    try:
        res = await research_pipeline.start(request.company_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception(f"Research failed for '{request.company_name}': {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

    background.add_task(
        research_pipeline.analyze_in_background,
        res["file_id"],
        res["text"],
        res["company_name"],
    )

    return ResearchResponse(
        success=True,
        file_id=res["file_id"],
        company_name=res["company_name"],
        chunks_stored=res["chunks_stored"],
        sources=res["sources"],
        status=STATUS_PROCESSING,
        message=f"Researched {len(res['sources'])} sources. Scoring in progress.",
    )


@router.get("/ticker")
async def funding_ticker(force: bool = False):
    """Recent notable startup raises worldwide, for the ticker bar."""
    try:
        return await get_ticker(force=force)
    except Exception as exc:
        logger.error(f"Ticker failed: {exc}")
        return {"raises": [], "cached": False, "age_s": 0}


@router.get("/firms")
async def firm_watch(force: bool = False):
    """Recent investments by the largest global venture funds (6h cache)."""
    if not tavily_configured():
        return {"firms": [], "cached": False, "age_s": 0}
    try:
        return await get_firms(force=force)
    except Exception as exc:
        logger.error(f"Firm watch failed: {exc}")
        return {"firms": [], "cached": False, "age_s": 0}


# ── Registered entries ────────────────────────────────────────────────────
# These moved here from the old /ingest router when deck upload was removed:
# the Dex needs the document list for silhouettes and the status endpoint for
# polling, but there is no longer any file ingestion to hang them off.


@router.get("/status/{file_id}", response_model=IngestStatusResponse)
async def research_status_endpoint(file_id: str):
    """Poll a background research job."""
    doc = await mongo_client.get_file_status(file_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Unknown file_id.")
    return IngestStatusResponse(
        file_id=file_id,
        status=doc.get("status", STATUS_PROCESSING),
        company_name=doc.get("company_name"),
        filename=doc.get("filename"),
        deal_id=doc.get("deal_id"),
        report_id=doc.get("report_id"),
        error=doc.get("error"),
    )


@router.get("/documents")
async def list_documents_endpoint():
    """Every registered dex entry, including ones still being analyzed."""
    try:
        documents = await mongo_client.list_documents()
        return {"documents": documents, "total": len(documents)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/documents/{doc_id}")
async def delete_document_endpoint(doc_id: str):
    """Remove a dex entry: chunks, document record, deal and reports."""
    from tools.mongo_client import _as_id

    doc_record = await db.documents.find_one({"file_id": doc_id})
    if not doc_record:
        doc_record = await db.documents.find_one({"_id": _as_id(doc_id)})
    if not doc_record:
        raise HTTPException(status_code=404, detail="Entry not found.")

    file_id = doc_record.get("file_id")
    if file_id:
        try:
            delete_by_file_id(file_id)
        except Exception as exc:
            logger.error(f"Failed to delete chunks: {exc}")

    await db.documents.delete_one({"_id": doc_record["_id"]})

    if file_id:
        await db.files.delete_one({"_id": file_id})
        deal = await db.deals.find_one({"file_id": file_id})
        if deal:
            await db.deals.delete_one({"_id": deal["_id"]})
            await db.reports.delete_many({"deal_id": str(deal["_id"])})
        await db.reports.delete_many({"file_id": file_id})

    return {"status": "success", "message": "Deleted dex entry and its analysis."}
