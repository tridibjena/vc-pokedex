"""
Guard against writing to ChromaDB while the API server is running.

ChromaDB's PersistentClient is a single-process embedded store, not a server.
When a seed script mutates the directory underneath a live uvicorn process, the
running server keeps its own stale view and fails in two ways:

  * hard  — `chromadb.errors.InternalError: Error finding id` out of the dense
            leg, which 500s every chat request until the server is restarted
  * soft  — the cached BM25 index still holds ids that were deleted, so RRF
            fuses ranks for rows that no longer exist and retrieval silently
            returns fewer results than it should

The soft failure is the dangerous one: nothing errors, answers just get worse.

Both are avoided by not writing while the server is up, which is what this
checks for.
"""
import sys
from pathlib import Path

import httpx
from loguru import logger

# The port `uvicorn api.main:app` is documented to run on.
DEFAULT_HEALTH_URL = "http://127.0.0.1:8000/health"


def api_is_running(url: str = DEFAULT_HEALTH_URL, timeout: float = 1.5) -> bool:
    """True if something is answering /health locally."""
    try:
        return httpx.get(url, timeout=timeout).status_code == 200
    except Exception:
        return False


OVERRIDE_FLAG = "--allow-running-api"


def ensure_exclusive_access(*, force: bool = False, url: str = DEFAULT_HEALTH_URL) -> None:
    """Abort if the API is live, unless the caller explicitly overrode it."""
    if not api_is_running(url):
        return

    if force:
        logger.warning(
            f"The API is running and {OVERRIDE_FLAG} was passed. The server will "
            f"keep a stale view of the vector store until it is restarted."
        )
        return

    script = Path(sys.argv[0]).name or "seed_library.py"
    raise SystemExit(
        "\nThe API server is running on port 8000.\n\n"
        "ChromaDB's PersistentClient is single-process: seeding now would leave\n"
        "the running server with a stale index, breaking RAG chat until it is\n"
        "restarted — sometimes silently, by returning fewer results.\n\n"
        "Stop the server, seed, then start it again:\n\n"
        "    pkill -f 'uvicorn api.main:app'\n"
        f"    python {script}\n"
        "    uvicorn api.main:app --port 8000\n\n"
        f"Or pass {OVERRIDE_FLAG} and restart the server afterwards.\n"
    )
