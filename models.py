from pydantic import BaseModel, Field
from typing import Any


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


class ScanRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=32000)
    user_id: str | None = None


class ThreatCategory(BaseModel):
    name: str
    score: float


class ScanResponse(BaseModel):
    threat_score: float = Field(..., ge=0, le=100)
    blocked: bool
    sanitized_text: str
    categories: list[ThreatCategory]
    reasons: list[str]
    semantic_hits: list[str] = []
    regex_hits: list[str] = []


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=32000)
    session_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    input_scan: ScanResponse
    output_safe: bool
    output_filtered: bool


class LogEntry(BaseModel):
    id: str | None = None
    ts: float
    level: str
    event: str
    detail: str
    meta: dict[str, Any] | None = None


class ThreatRecord(BaseModel):
    id: str | None = None
    user_id: str | None
    message_preview: str
    threat_score: float
    blocked: bool
    categories: list[str]
    timestamp: float


class AnalyticsSummary(BaseModel):
    total_scans: int
    blocked_count: int
    avg_threat_score: float
    by_category: dict[str, int]
    timeline: list[dict[str, Any]]


class SimulateRequest(BaseModel):
    prompts: list[str] | None = None
