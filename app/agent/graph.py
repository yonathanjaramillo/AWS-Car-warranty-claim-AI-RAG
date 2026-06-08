import time
from app.models.claim import OEM, ClaimResult, ClaimDecision, AuditEntry, PipelineStage
from app.extraction.pipeline import ExtractionPipeline
from app.rag.knowledge_base import KnowledgeBaseRAG
from app.observability.logger import get_logger

log = get_logger(__name__)

TEXTRACT_COST = 0.0015
BEDROCK_COST = 0.003

async def run_claim_pipeline(claim_id, oem, dealer_id, s3_key, idempotency_key):
    start = time.perf_counter()
    audit = []
    total_cost = 0.0

    audit.append(AuditEntry(stage=PipelineStage.RECEIVED, action="pipeline_started", detail=f"oem={oem.value}"))

    pipeline = ExtractionPipeline()
    extracted = await pipeline.extract(claim_id=claim_id, oem=oem, s3_key=s3_key, idempotency_key=idempotency_key)
    total_cost += TEXTRACT_COST
    audit.append(AuditEntry(stage=PipelineStage.EXTRACTING, action="extraction_completed", detail=f"VIN={extracted.vin.value} conf={extracted.vin.confidence:.2f}", cost_usd=TEXTRACT_COST))

    rag = KnowledgeBaseRAG()
    validation = rag.validate_claim(claim_id=claim_id, oem=oem, vin=extracted.vin.value, repair_date=extracted.repair_date.value, labor_op_code=extracted.labor_op_code.value, claim_amount=extracted.claim_amount.value, mileage=extracted.mileage.value if extracted.mileage else None)
    total_cost += BEDROCK_COST
    audit.append(AuditEntry(stage=PipelineStage.VALIDATING, action="rag_validation_completed", detail=f"is_valid={validation.is_valid} matches={len(validation.policy_matches)}", cost_usd=BEDROCK_COST))

    confidence = max((m.score for m in validation.policy_matches), default=0.0)
    try:
        amount = float(extracted.claim_amount.value)
    except:
        amount = 0.0

    if not validation.is_valid:
        decision = ClaimDecision.REJECTED
        requires_human = False
        reason = f"Rejected: {validation.validation_note[:200]}"
    elif amount > 2500 or confidence < 0.6:
        decision = ClaimDecision.ESCALATED
        requires_human = True
        reason = f"Escalated: amount=${amount:.2f} confidence={confidence:.2f}"
    else:
        decision = ClaimDecision.APPROVED
        requires_human = False
        reason = f"Approved: {validation.validation_note[:200]}"

    total_ms = int((time.perf_counter() - start) * 1000)
    audit.append(AuditEntry(stage=PipelineStage.COMPLETE, action=f"decision_{decision.value}", detail=reason, latency_ms=total_ms, cost_usd=total_cost))

    return ClaimResult(
        claim_id=claim_id, oem=oem, decision=decision, confidence=confidence,
        decision_reason=reason,
        policy_citations=[f"{m.policy_name} - {m.section}" for m in validation.policy_matches[:3]] or ["Local policy validation"],
        extracted=extracted, validation=validation, audit_trail=audit,
        total_latency_ms=total_ms, total_cost_usd=round(total_cost, 4), requires_human=requires_human,
    )