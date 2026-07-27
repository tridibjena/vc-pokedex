"""
Global application settings loaded from .env
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Gemini / LLM ────────────────────────────
    gemini_api_key: str = ""
    # Primary generation model. Provider-qualified: "openrouter:<id>", or bare
    # for Gemini. OpenRouter leads because its free tier is both larger and
    # longer-context than Gemini's; Gemini backs it up.
    primary_model: str = "openrouter:google/gemini-3.1-flash-lite"
    # Free-tier generate quota is 20/day PER MODEL, so a busy day exhausts one
    # model while its siblings still have headroom. On 429 we fail over down
    # this list rather than degrading the analysis to fallback values.
    # Chain entries may be provider-qualified as "openrouter:<model-id>".
    # Unqualified entries are Gemini. OpenRouter legs are skipped automatically
    # when OPENROUTER_API_KEY is unset, so this default is safe either way.
    fallback_models: str = (
        # Free legs behind the paid primary: if the account has no credits,
        # OpenRouter answers 402 and the chain drops through to these.
        "openrouter:nvidia/nemotron-3-super-120b-a12b:free,"
        "openrouter:openai/gpt-oss-20b:free,"
        "openrouter:openrouter/free,"
        "gemini-3.6-flash,"
        "gemini-3.1-flash-lite,"
        "gemini-3-flash-preview,"
        "gemini-3.5-flash"
    )
    gemini_embed_model: str = "gemini-embedding-001"

    # Max characters of document text sent to the extraction prompt.
    max_extract_chars: int = 60000

    # Gemini free tier caps embedding at 100 requests/minute, counted per input
    # item rather than per batched call — so a 200-chunk document trips it.
    # Keep headroom under the cap; raise this on a paid plan.
    embed_items_per_minute: int = 90
    embed_batch_size: int = 50

    # Generation is capped far harder: 5 requests/minute per model on the free
    # tier. One full analysis makes ~6 LLM calls, so without pacing the last
    # nodes (rewrite, memo) always 429. Raise this on a paid plan.
    generate_requests_per_minute: int = 5

    # ── MongoDB ──────────────────────────────────
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_db: str = "vc_pokedex"
    # Driver default is 30s, which turns an unreachable DB into a 30s hang.
    mongo_timeout_ms: int = 3000

    # ── ChromaDB ─────────────────────────────────
    chroma_persist_dir: str = "./data/chroma"

    # ── FastAPI ──────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    debug: bool = True
    log_level: str = "INFO"

    # Comma-separated list of origins allowed to call the API.
    # "*" with credentials makes Starlette echo any origin back, which lets any
    # site issue credentialed cross-origin requests — so keep this explicit.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ── File Storage ─────────────────────────────
    upload_dir: str = "./data/uploads"
    max_upload_size_mb: int = 50

    # ── RAG ──────────────────────────────────────
    chunk_size: int = 1000
    chunk_overlap: int = 200
    top_k_results: int = 5

    # ── OpenRouter (second LLM provider) ─────────
    # Free tier: 20 req/min, 50 req/day — 1,000/day once any credits are bought.
    openrouter_api_key: str = ""
    openrouter_timeout_s: int = 120

    # ── Optional External APIs ───────────────────
    tavily_api_key: str = ""
    # Tavily defaults to a 60s timeout. Healthy queries return in ~1.5s, so a
    # single slow one otherwise adds a full minute to every scan.
    tavily_timeout_s: int = 15
    sec_user_agent: str = "VCPokedex contact@example.com"

    @property
    def model_chain(self) -> list[str]:
        """Primary model first, then quota fallbacks, de-duplicated."""
        chain = [self.primary_model] + [
            m.strip() for m in self.fallback_models.split(",") if m.strip()
        ]
        seen, out = set(), []
        for m in chain:
            if m and m not in seen:
                seen.add(m)
                out.append(m)
        return out

    @property
    def upload_path(self) -> Path:
        p = Path(self.upload_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def chroma_path(self) -> Path:
        p = Path(self.chroma_persist_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
