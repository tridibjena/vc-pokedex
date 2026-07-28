from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from loguru import logger
from motor.motor_asyncio import AsyncIOMotorClient

from config.settings import settings

# Cap server selection: the driver's 30s default means a request against a dead
# MongoDB hangs the caller for half a minute before failing.
client = AsyncIOMotorClient(
    settings.mongodb_url,
    serverSelectionTimeoutMS=settings.mongo_timeout_ms,
    connectTimeoutMS=settings.mongo_timeout_ms,
)
db = client[settings.mongodb_db]

# Ingestion job states stored on the `files` collection.
STATUS_PROCESSING = "processing"
STATUS_COMPLETE = "complete"
STATUS_FAILED = "failed"


def _now() -> datetime:
    """Timezone-aware UTC. datetime.utcnow() is deprecated from Python 3.12."""
    return datetime.now(timezone.utc)


def _serialize(doc: dict | None) -> dict | None:
    """Convert ObjectId fields to strings for JSON serialization."""
    if doc is None:
        return None
    doc = dict(doc)
    if "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


def _as_id(value: str):
    """Return an ObjectId when the string is one, else the value unchanged.

    File ids are UUID strings while deals/reports/documents use ObjectIds, so
    both shapes reach the same helpers.
    """
    if isinstance(value, str):
        try:
            return ObjectId(value)
        except (InvalidId, TypeError):
            return value
    return value


class MongoDBClient:
    """Asynchronous MongoDB helper wrapper client."""

    # ── Health & setup ────────────────────────────────────────────────────
    async def ping(self) -> bool:
        try:
            await db.command("ping")
            return True
        except Exception as exc:
            logger.error(f"MongoDB ping failed: {exc}")
            return False

    async def ensure_indexes(self) -> None:
        """Create the indexes the query patterns rely on. Idempotent."""
        try:
            await db.deals.create_index("company_name")
            await db.deals.create_index("file_id")
            await db.deals.create_index([("created_at", -1)])
            await db.deals.create_index("sector")
            await db.deals.create_index("stage")
            await db.documents.create_index("file_id")
            await db.documents.create_index([("ingested_at", -1)])
            await db.library.create_index("file_id", unique=True)
            await db.library.create_index([("uploaded_at", -1)])
            await db.reports.create_index("deal_id")
            await db.reports.create_index([("created_at", -1)])
            await db.agent_memory.create_index([("session_id", 1), ("timestamp", 1)])
            logger.info("MongoDB indexes ensured.")
        except Exception as exc:
            logger.error(f"Failed to ensure MongoDB indexes: {exc}")

    # ── Deals ─────────────────────────────────────────────────────────────
    async def insert_deal(self, deal_data: dict) -> str:
        deal_data["created_at"] = _now()
        deal_data["updated_at"] = _now()
        result = await db.deals.insert_one(deal_data)
        deal_id = str(result.inserted_id)
        logger.info(f"Inserted deal: {deal_id}")
        return deal_id

    async def get_deal(self, deal_id: str) -> dict | None:
        try:
            return _serialize(await db.deals.find_one({"_id": _as_id(deal_id)}))
        except Exception as exc:
            logger.error(f"Failed to get deal {deal_id}: {exc}")
            return None

    async def list_deals(
        self, filter: dict | None = None, limit: int = 50, skip: int = 0
    ) -> list[dict]:
        try:
            cursor = (
                db.deals.find(filter or {})
                .sort("created_at", -1)
                .skip(skip)
                .limit(limit)
            )
            return [_serialize(doc) async for doc in cursor]
        except Exception as exc:
            logger.error(f"Failed to list deals: {exc}")
            return []

    async def update_deal(self, deal_id: str, update_data: dict) -> bool:
        update_data["updated_at"] = _now()
        try:
            result = await db.deals.update_one(
                {"_id": _as_id(deal_id)}, {"$set": update_data}
            )
            return result.modified_count > 0
        except Exception as exc:
            logger.error(f"Failed to update deal {deal_id}: {exc}")
            return False

    async def count_deals(self, filter: dict | None = None) -> int:
        return await db.deals.count_documents(filter or {})

    # ── Files (raw source text + ingestion status) ─────────────────────────
    async def save_file(self, file_id: str, doc: dict) -> None:
        doc = {**doc, "_id": file_id, "status": STATUS_PROCESSING, "created_at": _now()}
        await db.files.insert_one(doc)

    async def set_file_status(
        self, file_id: str, status: str, error: str | None = None, **extra
    ) -> None:
        update = {"status": status, "updated_at": _now(), **extra}
        if error is not None:
            update["error"] = error
        await db.files.update_one({"_id": file_id}, {"$set": update})

    async def get_file_status(self, file_id: str) -> dict | None:
        doc = await db.files.find_one(
            {"_id": file_id},
            {"text": 0},  # never ship the full document text in a status poll
        )
        return _serialize(doc)

    # ── Documents (metadata) ──────────────────────────────────────────────
    async def save_document_metadata(self, metadata: dict) -> str:
        metadata["ingested_at"] = _now()
        result = await db.documents.insert_one(metadata)
        doc_id = str(result.inserted_id)
        logger.info(f"Saved document metadata: {doc_id}")
        return doc_id

    async def list_documents(self, limit: int = 100) -> list[dict]:
        cursor = db.documents.find({}).sort("ingested_at", -1).limit(limit)
        return [_serialize(doc) async for doc in cursor]

    async def delete_document(self, doc_id: str) -> bool:
        try:
            result = await db.documents.delete_one({"_id": _as_id(doc_id)})
            return result.deleted_count > 0
        except Exception as exc:
            logger.error(f"Failed to delete document {doc_id}: {exc}")
            return False

    # ── Library (uploaded reference documents) ────────────────────────────
    # A separate collection from `documents` on purpose. `documents` backs the
    # Dex grid, where every row without a deal renders as a pending silhouette;
    # a term sheet filed here is reference material for chat, not a company
    # awaiting a score, and would otherwise sit in the Dex scanning forever.

    async def save_library_doc(self, record: dict) -> str:
        record["uploaded_at"] = _now()
        result = await db.library.insert_one(record)
        logger.info(f"Saved library document: {record.get('filename')}")
        return str(result.inserted_id)

    async def list_library_docs(self, limit: int = 200) -> list[dict]:
        cursor = db.library.find({}).sort("uploaded_at", -1).limit(limit)
        return [_serialize(doc) async for doc in cursor]

    async def get_library_doc(self, file_id: str) -> dict | None:
        return _serialize(await db.library.find_one({"file_id": file_id}))

    async def set_library_status(
        self, file_id: str, status: str, error: str | None = None, **extra
    ) -> None:
        update = {"status": status, "updated_at": _now(), **extra}
        update["error"] = error  # cleared on success, so a retry looks clean
        await db.library.update_one({"file_id": file_id}, {"$set": update})

    async def delete_library_doc(self, file_id: str) -> bool:
        result = await db.library.delete_one({"file_id": file_id})
        return result.deleted_count > 0

    # ── Agent Memory ──────────────────────────────────────────────────────
    async def save_agent_memory(self, session_id: str, memory_data: dict) -> None:
        memory_data["session_id"] = session_id
        memory_data["timestamp"] = _now()
        await db.agent_memory.insert_one(memory_data)

    async def get_agent_memory(self, session_id: str, limit: int = 50) -> list[dict]:
        cursor = (
            db.agent_memory.find({"session_id": session_id})
            .sort("timestamp", 1)
            .limit(limit)
        )
        return [_serialize(doc) async for doc in cursor]

    async def clear_agent_memory(self, session_id: str) -> None:
        await db.agent_memory.delete_many({"session_id": session_id})

    # ── Reports ───────────────────────────────────────────────────────────
    async def save_report(self, report_data: dict) -> str:
        report_data["created_at"] = _now()
        result = await db.reports.insert_one(report_data)
        report_id = str(result.inserted_id)
        logger.info(f"Saved report: {report_id}")
        return report_id

    async def get_report(self, report_id: str) -> dict | None:
        try:
            return _serialize(await db.reports.find_one({"_id": _as_id(report_id)}))
        except Exception as exc:
            logger.error(f"Failed to get report {report_id}: {exc}")
            return None

    async def list_reports(self, limit: int = 50) -> list[dict]:
        cursor = db.reports.find({}).sort("created_at", -1).limit(limit)
        return [_serialize(doc) async for doc in cursor]

    # ── Aggregations ──────────────────────────────────────────────────────
    async def _distribution(self, field: str) -> dict[str, int]:
        try:
            cursor = db.deals.aggregate(
                [{"$group": {"_id": f"${field}", "count": {"$sum": 1}}}]
            )
            return {r["_id"]: r["count"] async for r in cursor if r["_id"]}
        except Exception as exc:
            logger.error(f"Failed to get {field} distribution: {exc}")
            return {}

    async def get_sector_distribution(self) -> dict[str, int]:
        return await self._distribution("sector")

    async def get_stage_distribution(self) -> dict[str, int]:
        return await self._distribution("stage")


mongo_client = MongoDBClient()
