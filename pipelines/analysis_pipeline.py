import time

from loguru import logger

from agents.orchestrator import orchestrator
from tools.mongo_client import db, mongo_client


class AnalysisPipeline:
    """Runs the LangGraph orchestrator and persists the deal + memo."""

    async def analyze_company(
        self, text: str, file_id: str, company_name: str = "Unknown Startup"
    ) -> dict:
        start_time = time.perf_counter()
        logger.info(f"[AnalysisPipeline] Analyzing '{company_name}' (file_id: {file_id})")

        try:
            result = await orchestrator.run(
                raw_text=text, file_id=file_id, company_name=company_name
            )

            meta = result.get("metadata", {})
            ratios = result.get("ratios", {})
            scorecard = result.get("scorecard", {})
            memo = result.get("memo", "")

            resolved_name = meta.get("company_name") or company_name

            deal_data = {
                "company_name": resolved_name,
                "sector": meta.get("sector", "Unknown"),
                "stage": meta.get("stage", "Unknown"),
                "overall_score": scorecard.get("overall_score"),
                "recommendation": scorecard.get("recommendation"),
                "scorecard": scorecard,
                "ratios": ratios,
                "risk_flags": result.get("risk_flags", []),
                "founder_profiles": result.get("founder_profiles", {}),
                "competitors": result.get("competitors", {}),
                "comps": [
                    {"id": c.get("id"), "meta": c.get("meta", {})}
                    for c in result.get("comps", [])
                ],
                "metadata": meta,
                "file_id": file_id,
            }

            # Key the upsert on file_id, not company_name: re-analyzing the same
            # file should update its deal, while two different uploads that both
            # failed extraction must not collapse into one shared record.
            existing = await db.deals.find_one({"file_id": file_id})
            if existing:
                await mongo_client.update_deal(str(existing["_id"]), deal_data)
                deal_id = str(existing["_id"])
                logger.info(f"Updated existing deal record {deal_id}.")
            else:
                deal_id = await mongo_client.insert_deal(deal_data)
                logger.info(f"Created new deal record {deal_id}.")

            report_id = await mongo_client.save_report(
                {
                    "company_name": resolved_name,
                    "deal_id": deal_id,
                    "file_id": file_id,
                    "report_type": "investment_memo",
                    "content": memo,
                }
            )

            elapsed = (time.perf_counter() - start_time) * 1000
            logger.success(f"[AnalysisPipeline] Completed '{resolved_name}' in {elapsed:.0f}ms")

            return {
                "success": True,
                "deal_id": deal_id,
                "report_id": report_id,
                "scorecard": scorecard,
                "memo": memo,
                "metadata": meta,
                "ratios": ratios,
                "processing_time_ms": elapsed,
            }

        except Exception as exc:
            elapsed = (time.perf_counter() - start_time) * 1000
            logger.exception(f"[AnalysisPipeline] Failed for {company_name}: {exc}")
            return {
                "success": False,
                "error": str(exc),
                "processing_time_ms": elapsed,
            }


analysis_pipeline = AnalysisPipeline()
