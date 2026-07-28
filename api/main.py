from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from api.routes import chat, library, reports, research
from api.schemas import HealthResponse
from config.settings import settings
from tools.mongo_client import mongo_client

DIST_DIR = Path("dashboard/dist")
API_PREFIXES = (
    "chat", "reports", "research", "library",
    "health", "docs", "redoc", "openapi.json",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.upload_path
    settings.chroma_path
    await mongo_client.ensure_indexes()

    logger.info("VC Pokedex backend started.")
    from tools.llm_client import usable_chain as _uc
    logger.info(f"Model chain (live): {' -> '.join(_uc())}")
    logger.info(f"Embeddings: {settings.gemini_embed_model}")
    logger.info(f"MongoDB: {settings.mongodb_url} | Chroma: {settings.chroma_persist_dir}")
    logger.info(f"CORS origins: {settings.cors_origin_list}")
    yield
    logger.info("VC Pokedex backend shutting down.")


app = FastAPI(
    title="VC Pokedex API",
    description="AI-powered VC deal analysis with multi-agent orchestration",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Explicit origins, not "*". With allow_credentials=True, Starlette echoes the
# caller's Origin back instead of sending "*", which would let any site issue
# credentialed cross-origin requests against this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(reports.router)
app.include_router(research.router)
app.include_router(library.router)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Report whether the backing services are usable.

    Deliberately does NOT call the Gemini API: the dashboard polls this endpoint
    on a timer, and a generate() per poll burns thousands of free-tier requests
    a day just to render a status dot. Credential presence is what we can check
    for free; a real call would be the first genuine request.
    """
    from tools.llm_client import is_configured, usable_chain
    from tools.openrouter import is_configured as openrouter_configured

    # Gemini is not optional even when OpenRouter leads the chain: embeddings,
    # and therefore all retrieval, run on gemini-embedding-001.
    gemini_ok = is_configured()
    openrouter_ok = openrouter_configured()
    mongo_ok = await mongo_client.ping()

    chroma_ok = False
    try:
        from tools.vector_store import health as chroma_health

        chroma_health()
        chroma_ok = True
    except Exception as exc:
        logger.warning(f"ChromaDB health check failed: {exc}")

    return HealthResponse(
        status="ok" if (gemini_ok and mongo_ok and chroma_ok) else "degraded",
        gemini=gemini_ok,
        openrouter=openrouter_ok,
        mongodb=mongo_ok,
        chromadb=chroma_ok,
        # The chain as it will actually run — legs whose provider has no key
        # are filtered out, so the configured primary may not be the live one.
        primary_model=usable_chain()[0],
        version="1.0.0",
    )


# ── Static dashboard (only when the React app has been built) ────────────────
if DIST_DIR.exists():
    assets_dir = DIST_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")
    logger.info(f"Serving built React dashboard from: {DIST_DIR}")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_react_app(full_path: str):
        # Never shadow the API surface — return a real 404 instead of `null`.
        if full_path.split("/", 1)[0] in API_PREFIXES:
            raise HTTPException(status_code=404, detail="Not Found")

        # Real files in the dist root (favicon.ico, logo-mark.png, anything
        # Vite copies from public/) must be served as themselves. Only /assets
        # was mounted, so everything else used to fall through to this catch-all
        # and come back as index.html with content-type text/html — which is why
        # the logo and favicon rendered as broken images.
        if full_path:
            candidate = (DIST_DIR / full_path).resolve()
            dist_root = DIST_DIR.resolve()
            # Reject traversal: the resolved path must stay inside dist.
            if candidate.is_file() and candidate.is_relative_to(dist_root):
                return FileResponse(str(candidate))

        index_file = DIST_DIR / "index.html"
        if index_file.exists():
            return FileResponse(str(index_file))
        raise HTTPException(status_code=404, detail="Not Found")

else:
    logger.warning("dashboard/dist not found — serving API only.")

    @app.get("/")
    async def api_root():
        return {
            "message": "VC Pokedex API is running. Frontend has not been built yet.",
            "docs": "/docs",
            "health": "/health",
        }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )
