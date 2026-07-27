import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

# ── Request Models ───────────────────────────────────────────────────────────


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    stream: bool = False
    file_id: Optional[str] = None


class IngestURLRequest(BaseModel):
    url: str
    doc_type: str = "report"  # report, pitch_deck, fund_letter, news
    metadata: dict = Field(default_factory=dict)

    @field_validator("url")
    @classmethod
    def must_be_http(cls, v: str) -> str:
        """Reject non-HTTP schemes so the scraper can't be pointed at file:// etc."""
        if not v.lower().startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        return v


class ResearchRequest(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=120)


class ResearchResponse(BaseModel):
    success: bool
    file_id: str
    company_name: str
    chunks_stored: int
    sources: list[dict] = Field(default_factory=list)
    status: str
    message: str


class CompareRequest(BaseModel):
    company_a: str
    company_b: str
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


class ReportRequest(BaseModel):
    company_name: str
    report_type: str = "one_pager"  # one_pager, comparison, trend
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))


# ── Response Models ──────────────────────────────────────────────────────────


class ChatResponse(BaseModel):
    response: str
    session_id: str
    sources: list[dict] = Field(default_factory=list)
    agent_steps: list[str] = Field(default_factory=list)
    deal_analysis: Optional[dict] = None
    processing_time_ms: float


class IngestResponse(BaseModel):
    """Returned immediately after indexing; analysis continues in the background."""

    success: bool
    file_id: str
    filename: str
    company_name: str
    chunks_stored: int
    status: str
    message: str


class IngestStatusResponse(BaseModel):
    file_id: str
    status: str  # processing | complete | failed
    company_name: Optional[str] = None
    filename: Optional[str] = None
    deal_id: Optional[str] = None
    report_id: Optional[str] = None
    error: Optional[str] = None


class DealCard(BaseModel):
    deal_id: str
    company_name: str
    sector: str
    stage: str
    round_size: Optional[str] = None
    lead_investor: Optional[str] = None
    overall_score: Optional[float] = None
    recommendation: Optional[str] = None
    created_at: datetime
    file_id: Optional[str] = None
    # The five dimension scores, so the Dex grid can draw a stat spread per card
    # without an N+1 fetch of every deal's full detail.
    scores: Optional[dict] = None
    # Funding headline, likewise denormalized onto the card.
    last_round: Optional[str] = None
    round_amount: Optional[float] = None
    valuation: Optional[float] = None


class DealsListResponse(BaseModel):
    deals: list[DealCard]
    total: int


class ReportResponse(BaseModel):
    report_id: str
    company_name: str
    report_type: str
    content: str
    created_at: datetime


class HealthResponse(BaseModel):
    status: str
    gemini: bool          # required — embeddings run on Gemini regardless of chain
    openrouter: bool      # optional — extends the generation chain
    mongodb: bool
    chromadb: bool
    primary_model: str
    version: str = "1.0.0"
