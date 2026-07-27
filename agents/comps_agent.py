import asyncio

from loguru import logger

from config.settings import settings
from tools.vector_store import query_comps


async def comps_node(state: dict) -> dict:
    """Retrieve comparable deals from the comps corpus."""
    logger.info("Executing comps node...")
    meta = state.get("metadata", {})

    # A rewritten query is injected into metadata by the CRAG rewrite node.
    q = meta.get("_rewrite_query")
    if not q:
        q = " ".join(
            part
            for part in (meta.get("sector"), meta.get("stage"), meta.get("business_model"))
            if part
        ).strip()

    if not q:
        logger.warning("No usable comps query could be built from metadata.")
        return {"comps": []}

    logger.info(f"Querying vector store for comps with query: '{q}'")
    comps = await asyncio.to_thread(query_comps, q, settings.top_k_results)

    logger.info(f"Comps node retrieved {len(comps)} matches.")
    return {"comps": comps}
