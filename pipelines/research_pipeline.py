"""
Name → Dex entry.

The only way into the Dex. Researches a company on the web, then runs the
analysis graph over the resulting dossier to produce a full entry: profile,
funding, comps, founders, competitors, risk, scorecard and memo.

Concurrency shape:

    POST /research
      └─ research: 5 Tavily queries, all concurrent          ~2s   in-request
      └─ persist the dossier (2 writes, concurrent)          ~0s
      └─ 202 returned here, with the sources
         └─ background:
              ├─ index chunks into Chroma  ┐ independent, so both
              └─ run the analysis graph    ┘ start at the same time
                   └─ 5 agents concurrent inside the graph

Indexing only powers RAG chat over the document; the graph reads the raw
dossier. Nothing downstream waits on it, so it has no business blocking either
the request or the analysis.
"""
import asyncio
import time
import uuid

from loguru import logger

from agents.research_agent import news_from, research_company, sources_from
from pipelines.analysis_pipeline import analysis_pipeline
from tools.chunking import chunk_text
from tools.mongo_client import STATUS_COMPLETE, STATUS_FAILED, mongo_client
from tools.vector_store import upsert_chunks


class ResearchPipeline:
    async def start(self, company_name: str) -> dict:
        """Research a company and persist the dossier. Returns fast.

        Deliberately does NOT index or analyze — both happen in the background,
        so the caller gets its 202 as soon as we know the company exists.
        """
        started = time.perf_counter()
        name = company_name.strip()
        if not name:
            raise ValueError("company_name is required")

        logger.info(f"[ResearchPipeline] Researching '{name}'")
        context, results, news_results = await research_company(name)
        if not context:
            raise ValueError(
                f"No web results found for '{name}'. Check the spelling, or set "
                f"TAVILY_API_KEY if it is missing."
            )

        file_id = str(uuid.uuid4())
        sources = sources_from(results)
        news = news_from(news_results)
        record = {
            "filename": f"{name} (web research)",
            "source_type": "research",
            "metadata": {"query": name, "sources": sources, "news": news},
            "company_name": name,
        }

        # Independent writes — no reason to await them in series.
        await asyncio.gather(
            mongo_client.save_file(file_id, {**record, "text": context}),
            mongo_client.save_document_metadata({**record, "file_id": file_id}),
        )

        elapsed = (time.perf_counter() - started) * 1000
        logger.success(f"[ResearchPipeline] '{name}': {len(sources)} sources in {elapsed:.0f}ms")
        return {
            "file_id": file_id,
            "company_name": name,
            "text": context,
            "chunks_stored": 0,  # indexing runs in the background
            "sources": sources,
            "news": news,
            "processing_time_ms": elapsed,
        }

    async def _index(self, file_id: str, text: str, company_name: str) -> int:
        """Chunk and embed the dossier so RAG chat can search it."""
        payload = [
            (
                f"{file_id}_{i}",
                chunk,
                {"company_name": company_name, "file_id": file_id, "source": "web research"},
            )
            for i, chunk in enumerate(chunk_text(text))
        ]
        try:
            stored = await asyncio.to_thread(upsert_chunks, payload)
            logger.info(f"[ResearchPipeline] Indexed {stored} chunk(s) for {company_name}.")
            return stored
        except Exception as exc:
            # Indexing only powers chat; its failure must not fail the analysis.
            logger.error(f"[ResearchPipeline] Indexing failed for {company_name}: {exc}")
            return 0

    async def process(self, file_id: str, text: str, company_name: str) -> None:
        """Index and analyze concurrently, then record the outcome."""
        started = time.perf_counter()
        try:
            _, result = await asyncio.gather(
                self._index(file_id, text, company_name),
                analysis_pipeline.analyze_company(
                    text=text, file_id=file_id, company_name=company_name
                ),
            )
        except Exception as exc:
            logger.exception(f"[ResearchPipeline] Background processing crashed: {exc}")
            await mongo_client.set_file_status(file_id, STATUS_FAILED, error=str(exc))
            return

        elapsed = (time.perf_counter() - started) * 1000
        if result.get("success"):
            await mongo_client.set_file_status(
                file_id,
                STATUS_COMPLETE,
                deal_id=result.get("deal_id"),
                report_id=result.get("report_id"),
            )
            logger.success(f"[ResearchPipeline] '{company_name}' complete in {elapsed:.0f}ms")
        else:
            await mongo_client.set_file_status(
                file_id, STATUS_FAILED, error=result.get("error", "Analysis failed.")
            )

    # Kept under the old name so the route's background task reads naturally.
    analyze_in_background = process

    async def run(self, company_name: str) -> dict:
        """Research, index and analyze synchronously. Used by tests and CLI."""
        res = await self.start(company_name)
        await self.process(res["file_id"], res["text"], res["company_name"])
        status = await mongo_client.get_file_status(res["file_id"])
        return {**res, "status": (status or {}).get("status")}


research_pipeline = ResearchPipeline()
