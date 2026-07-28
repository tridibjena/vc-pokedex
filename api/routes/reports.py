from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from api.schemas import DealCard, DealsListResponse, ReportRequest, ReportResponse
from pipelines.analysis_pipeline import analysis_pipeline
from tools.mongo_client import db, mongo_client

router = APIRouter(prefix="/reports", tags=["reports"])

DIMENSION_KEYS = (
    "market_size_score",
    "team_score",
    "traction_score",
    "competitive_moat_score",
    "financial_health_score",
)


def _dimension_scores(scorecard: dict | None) -> dict | None:
    """Pull just the five dimensions out of a scorecard for the Dex grid."""
    if not scorecard:
        return None
    out = {k: scorecard.get(k) for k in DIMENSION_KEYS if scorecard.get(k) is not None}
    return out or None


# NOTE: the literal paths below MUST stay declared before "/{report_id}",
# otherwise that catch-all swallows /deals, /list and /trends.


@router.get("/deals", response_model=DealsListResponse)
async def list_deals_endpoint(
    sector: Optional[str] = Query(None),
    stage: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    skip: int = Query(0, ge=0),
):
    """List analyzed startup deals with filtering and pagination."""
    filter_dict = {}
    if sector:
        filter_dict["sector"] = sector
    if stage:
        filter_dict["stage"] = stage

    try:
        deals = await mongo_client.list_deals(filter_dict, limit=limit, skip=skip)
        total = await mongo_client.count_deals(filter_dict)

        formatted = [
            DealCard(
                deal_id=d.get("_id"),
                company_name=d.get("company_name") or "Unknown Startup",
                sector=d.get("sector") or "Unknown",
                stage=d.get("stage") or "Unknown",
                round_size=(d.get("metadata") or {}).get("round_size"),
                lead_investor=(d.get("metadata") or {}).get("lead_investor"),
                overall_score=d.get("overall_score"),
                recommendation=d.get("recommendation"),
                created_at=d.get("created_at") or datetime.now(timezone.utc),
                file_id=d.get("file_id"),
                scores=_dimension_scores(d.get("scorecard")),
                last_round=(d.get("metadata") or {}).get("last_round"),
                round_amount=(d.get("metadata") or {}).get("last_round_amount"),
                valuation=(d.get("metadata") or {}).get("valuation"),
            )
            for d in deals
        ]
        return DealsListResponse(deals=formatted, total=total)
    except Exception as exc:
        logger.exception(f"Failed to list deals: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/deals/{deal_id}")
async def get_deal_endpoint(deal_id: str):
    """Full detail for one deal, including scorecard and ratios."""
    deal = await mongo_client.get_deal(deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found.")
    return deal


@router.get("/deals/{deal_id}/memo")
async def get_deal_memo_endpoint(deal_id: str):
    """Latest investment memo for a deal, so the Dex can show it inline."""
    doc = await db.reports.find_one({"deal_id": deal_id}, sort=[("created_at", -1)])
    if not doc:
        raise HTTPException(status_code=404, detail="No memo for this deal yet.")
    return {
        "report_id": str(doc["_id"]),
        "company_name": doc.get("company_name"),
        "content": doc.get("content") or "",
        "created_at": doc.get("created_at"),
    }


@router.get("/deals/{deal_id}/news")
async def get_deal_news_endpoint(deal_id: str):
    """Recent coverage for a deal.

    Read back from the dossier captured at scan time — the news pass already
    ran then, so showing it costs no extra Tavily calls.
    """
    deal = await mongo_client.get_deal(deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail="Deal not found.")

    file_id = deal.get("file_id")
    doc = await db.files.find_one({"_id": file_id}, {"metadata": 1}) if file_id else None
    meta = (doc or {}).get("metadata") or {}
    news = meta.get("news") or []

    # Entries scanned before news was captured separately fall back to sources.
    if not news:
        news = [
            {"title": s.get("title"), "url": s.get("url"), "published": s.get("published")}
            for s in (meta.get("sources") or [])[:6]
            if s.get("url")
        ]

    return {"deal_id": deal_id, "company_name": deal.get("company_name"), "news": news}


@router.get("/list")
async def list_reports_endpoint():
    """Metadata for all generated reports."""
    try:
        reports = await mongo_client.list_reports()
        return {"reports": reports, "total": len(reports)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/trends")
async def get_market_trends_endpoint():
    """Aggregated sector, stage and monthly deal counts for the dashboard charts."""
    try:
        sectors = await mongo_client.get_sector_distribution()
        stages = await mongo_client.get_stage_distribution()

        pipeline = [
            {
                "$group": {
                    "_id": {
                        "year": {"$year": "$created_at"},
                        "month": {"$month": "$created_at"},
                    },
                    "count": {"$sum": 1},
                }
            },
            {"$sort": {"_id.year": 1, "_id.month": 1}},
        ]

        monthly_counts = []
        async for r in db.deals.aggregate(pipeline):
            year, month = r["_id"].get("year"), r["_id"].get("month")
            if year and month:
                monthly_counts.append({"date": f"{year}-{month:02d}", "count": r["count"]})

        return {
            "sector_distribution": sectors,
            "stage_distribution": stages,
            "monthly_deal_counts": monthly_counts,
        }
    except Exception as exc:
        logger.exception(f"Failed to fetch market trends: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/generate", response_model=ReportResponse)
async def generate_report_endpoint(request: ReportRequest):
    """Re-run the analysis graph for an already-ingested company."""
    deal = await db.deals.find_one({"company_name": request.company_name})
    if not deal:
        raise HTTPException(
            status_code=404,
            detail=f"No deal record found for '{request.company_name}'. Scan it first via POST /research.",
        )

    file_id = deal.get("file_id")
    file_doc = await db.files.find_one({"_id": file_id}) if file_id else None
    if not file_doc or not file_doc.get("text"):
        raise HTTPException(
            status_code=400,
            detail=f"No raw source text found for deal '{request.company_name}'.",
        )

    res = await analysis_pipeline.analyze_company(
        text=file_doc["text"], file_id=file_id, company_name=request.company_name
    )
    if not res.get("success"):
        raise HTTPException(status_code=500, detail=res.get("error", "Analysis failed."))

    report_id = res.get("report_id")
    if not report_id:
        raise HTTPException(status_code=500, detail="Failed to retrieve generated report ID.")

    return ReportResponse(
        report_id=report_id,
        company_name=request.company_name,
        report_type=request.report_type,
        content=res.get("memo") or "",
        created_at=datetime.now(timezone.utc),
    )


@router.get("/{report_id}")
async def get_report_endpoint(report_id: str):
    """Full Markdown content of one report."""
    report = await mongo_client.get_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")
    return report
