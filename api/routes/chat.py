import asyncio
import json
import time

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger

from api.schemas import ChatRequest, ChatResponse
from tools.llm_client import agenerate, stream
from tools.mongo_client import mongo_client
from tools.vector_store import query_documents

router = APIRouter(prefix="/chat", tags=["chat"])

CHAT_SYSTEM = (
    "You are a professional Venture Capital investment analyst. Use the provided "
    "document context to answer questions. Be precise, fact-based, and highlight "
    "any financial metrics when relevant."
)


def _build_prompt(query: str, context: str) -> str:
    return f"Context:\n{context}\n\nQuestion: {query}" if context else query


async def _retrieve(query: str, file_id: str | None, n: int = 3) -> list[dict]:
    """Retrieve document context off the event loop (Chroma + embed are blocking)."""
    return await asyncio.to_thread(query_documents, query, n, file_id)


@router.post("", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """Answer a question against the indexed documents."""
    start_time = time.perf_counter()
    logger.info(f"Chat request: session={request.session_id} file_id={request.file_id}")

    await mongo_client.save_agent_memory(
        request.session_id, {"role": "user", "content": request.query}
    )

    try:
        docs = await _retrieve(request.query, request.file_id)
        context = "\n\n".join(d["text"] for d in docs)
        res = await agenerate(_build_prompt(request.query, context), system=CHAT_SYSTEM)

        await mongo_client.save_agent_memory(
            request.session_id, {"role": "assistant", "content": res}
        )

        elapsed = (time.perf_counter() - start_time) * 1000
        logger.success(f"Chat completed in {elapsed:.0f}ms")

        return ChatResponse(
            response=res,
            session_id=request.session_id,
            sources=[{"text": d["text"][:200], "meta": d["meta"]} for d in docs],
            agent_steps=["retrieve_context", "generate_response"],
            deal_analysis=None,
            processing_time_ms=elapsed,
        )
    except Exception as exc:
        logger.exception(f"Chat execution failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@router.post("/stream")
async def chat_stream_endpoint(request: ChatRequest):
    """Server-Sent Events chat: emits retrieval steps, then streams the answer."""
    logger.info(f"Streaming chat: session={request.session_id} file_id={request.file_id}")

    await mongo_client.save_agent_memory(
        request.session_id, {"role": "user", "content": request.query}
    )

    async def event_generator():
        assistant_response = ""
        try:
            yield _sse({
                "type": "step",
                "node": "retrieve_context",
                "steps": [
                    "Querying ChromaDB vector store",
                    "Ranking documents using dense + sparse BM25 fusion",
                ],
            })

            docs = await _retrieve(request.query, request.file_id)
            context = "\n\n".join(d["text"] for d in docs)

            yield _sse({
                "type": "step",
                "node": "generate_response",
                "steps": [
                    f"Retrieved {len(docs)} context chunk(s)."
                    if docs else "No matching context found; answering from general knowledge.",
                ],
            })

            if docs:
                yield _sse({
                    "type": "sources",
                    "content": [{"text": d["text"][:200], "meta": d["meta"]} for d in docs],
                })

            async for chunk in stream(_build_prompt(request.query, context), system=CHAT_SYSTEM):
                assistant_response += chunk
                yield _sse({"type": "response", "content": chunk})

            if assistant_response:
                await mongo_client.save_agent_memory(
                    request.session_id, {"role": "assistant", "content": assistant_response}
                )

            yield _sse({"type": "done"})

        except Exception as exc:
            logger.exception(f"Streaming chat failed: {exc}")
            yield _sse({"type": "error", "content": str(exc)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/history/{session_id}")
async def get_chat_history(session_id: str):
    """Retrieve chat history messages."""
    try:
        history = await mongo_client.get_agent_memory(session_id)
        return {
            "session_id": session_id,
            "messages": [
                {
                    "role": m.get("role"),
                    "content": m.get("content"),
                    "deal_analysis": m.get("deal_analysis"),
                    "timestamp": m.get("timestamp"),
                }
                for m in history
            ],
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.delete("/history/{session_id}")
async def clear_chat_history(session_id: str):
    """Clear chat memory for a session."""
    try:
        await mongo_client.clear_agent_memory(session_id)
        return {"status": "success", "message": f"Cleared history for session: {session_id}"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
