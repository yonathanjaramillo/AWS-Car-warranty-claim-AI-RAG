"""
Pydantic v2 models — typed contracts for the warranty claim pipeline.

WHY THIS MATTERS (tell Mike):
Every field flowing through the system is typed and validated.
No silent failures, no mystery dicts. If Textract returns a malformed
VIN, Pydantic catches it at the boundary before it reaches the agent.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, field_validator
import re


# ── Enums ──────────────────────────────────────────────────────────────────────

class OEM(str, Enum):
    FORD       = "ford"
    GM         = "gm"
    TOYOTA     = "toyota"
    STELLANTIS = "stellantis"


class ExtractionSource(str, Enum):
    TEXTRACT = "textract"
    VISION   = "claude_vision"
    MANUAL   = "manual"


class ClaimDecision(str, Enum):
    APPROVED  = "approved"
    REJECTED  = "rejected"
    ESCALATED = "escalated"   # human-in-the-loop triggered


class PipelineStage(str, Enum):
    RECEIVED   = "received"
    EXTRACTING = "extracting"
    VALIDATING = "validating"
    DECIDING   = "deciding"
    COMPLETE   = "complete"
    FAILED     = "failed"


# ── Field-level extraction result ─────────────────────────────────────────────

class ExtractedField(BaseModel):
    """A single extracted field with provenance — source + confidence."""
    value:      str
    source:     ExtractionSource
    confidence: float = Field(ge=0.0, le=1.0)
    raw:        Optional[str] = None   # original Textract/Vision output before normalization


# ── The core extracted claim document ─────────────────────────────────────────

class ExtractedClaim(BaseModel):
    """
    Structured output from the document intelligence layer.
    All fields are typed — VIN validated, date normalized, currency as Decimal.

    WHY DETERMINISTIC PARSERS (tell Mike):
    We don't ask the LLM to parse a VIN. We use NHTSA checksum validation.
    LLMs hallucinate structure. Parsers don't.
    """
    claim_id:       str
    oem:            OEM

    # Core claim fields — each with extraction provenance
    vin:            ExtractedField
    repair_date:    ExtractedField
    labor_op_code:  ExtractedField
    claim_amount:   ExtractedField
    part_number:    Optional[ExtractedField] = None
    mileage:        Optional[ExtractedField] = None
    dealer_id:      Optional[ExtractedField] = None
    technician_id:  Optional[ExtractedField] = None

    # Pipeline metadata
    extracted_at:   datetime = Field(default_factory=datetime.utcnow)
    s3_key:         str
    idempotency_key: str

    @field_validator("vin")
    @classmethod
    def validate_vin_format(cls, v: ExtractedField) -> ExtractedField:
        """Basic VIN format check — 17 alphanumeric chars, no I/O/Q."""
        vin = v.value.upper().strip()
        if not re.match(r"^[A-HJ-NPR-Z0-9]{17}$", vin):
            raise ValueError(f"Invalid VIN format: {vin}")
        return v


# ── RAG validation result ──────────────────────────────────────────────────────

class PolicyMatch(BaseModel):
    """A single policy document chunk that matched during RAG retrieval."""
    policy_id:   str
    policy_name: str
    section:     str
    content:     str
    score:       float = Field(ge=0.0, le=1.0)


class ValidationResult(BaseModel):
    """
    Output from the RAG policy validation node.

    WHY PER-OEM KNOWLEDGE BASES (tell Mike):
    Ford policy docs must never influence a GM validation.
    Isolated KBs per OEM is a hard tenant boundary —
    not just a filter, a physical separation.
    """
    claim_id:       str
    oem:            OEM
    is_valid:       bool
    policy_matches: list[PolicyMatch]
    validation_note: str
    guardrail_triggered: bool = False
    validated_at:   datetime = Field(default_factory=datetime.utcnow)


# ── Agent decision ─────────────────────────────────────────────────────────────

class AuditEntry(BaseModel):
    """Every action the agent takes — logged to CloudWatch."""
    timestamp:   datetime = Field(default_factory=datetime.utcnow)
    stage:       PipelineStage
    action:      str
    detail:      Optional[str] = None
    latency_ms:  Optional[int] = None
    cost_usd:    Optional[float] = None


class ClaimResult(BaseModel):
    """
    Final output of the full pipeline.
    This is what the FastAPI endpoint returns and what gets logged to CloudWatch.

    WHY FULL AUDIT TRAIL (tell Mike):
    WarrCloud processes claims on behalf of dealers against OEMs.
    Every decision needs to be defensible. 'The AI said so' is not
    acceptable — we log every policy rule that triggered the decision.
    """
    claim_id:         str
    oem:              OEM
    decision:         ClaimDecision
    confidence:       float = Field(ge=0.0, le=1.0)
    decision_reason:  str
    policy_citations: list[str]           # specific policy sections that drove the decision
    extracted:        ExtractedClaim
    validation:       ValidationResult
    audit_trail:      list[AuditEntry]
    total_latency_ms: int
    total_cost_usd:   float
    requires_human:   bool = False        # True when HITL interrupt fired
    completed_at:     datetime = Field(default_factory=datetime.utcnow)


# ── API request/response ───────────────────────────────────────────────────────

class ProcessClaimRequest(BaseModel):
    oem:       OEM
    dealer_id: str
    s3_key:    Optional[str] = None   # if already uploaded; else upload via multipart


class ProcessClaimResponse(BaseModel):
    claim_id:  str
    status:    PipelineStage
    result:    Optional[ClaimResult] = None
    message:   str


class HealthResponse(BaseModel):
    status:   str = "ok"
    version:  str = "0.1.0"
    services: dict[str, str]
