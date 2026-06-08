"""
Claims API routes.

POST /claims/submit  — upload a PDF + trigger the full pipeline
GET  /claims/{id}    — poll pipeline status (frontend polls this)
POST /claims/{id}/approve  — HITL: warranty specialist approves escalated claim
POST /claims/{id}/reject   — HITL: warranty specialist rejects escalated claim
"""
import uuid
import hashlib
from typing import Optional

import boto3
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Depends
from fastapi.security.api_key import APIKeyHeader

from app.config import get_settings
from app.models.claim import (
    OEM, ClaimResult, PipelineStage, ProcessClaimResponse
)
from app.observability.logger import get_logger, bind_claim_context

router = APIRouter()
settings = get_settings()
log = get_logger(__name__)

# Simple API key auth — replaced by Cognito OIDC in production
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str = Depends(api_key_header)):
    if api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return api_key


@router.post("/submit", response_model=ProcessClaimResponse)
async def submit_claim(
    file: UploadFile = File(...),
    oem: OEM = Form(...),
    dealer_id: str = Form(...),
    _: str = Depends(verify_api_key),
):
    """
    Upload a warranty claim PDF and trigger the full AI pipeline.

    Flow:
    1. Upload PDF to S3
    2. Write idempotency key to DynamoDB
    3. Trigger async processing via Lambda (or run inline for demo)
    4. Return claim_id for polling
    """
    # Generate claim ID and idempotency key
    file_bytes = await file.read()
    file_hash = hashlib.sha256(file_bytes).hexdigest()[:16]
    claim_id = f"WC-{uuid.uuid4().hex[:8].upper()}"
    idempotency_key = f"{dealer_id}:{file_hash}"

    bind_claim_context(claim_id=claim_id, oem=oem.value, stage="received")
    log.info("claim_received", claim_id=claim_id, oem=oem.value,
             dealer_id=dealer_id, file_size_bytes=len(file_bytes))

    # Upload to S3
    s3_key = f"claims/{oem.value}/{dealer_id}/{claim_id}/{file.filename}"
    try:
        s3 = boto3.client("s3", region_name=settings.aws_region)

        # Check idempotency — don't reprocess the same document
        ddb = boto3.client("dynamodb", region_name=settings.aws_region)
        try:
            existing = ddb.get_item(
                TableName=settings.dynamodb_table,
                Key={"pk": {"S": f"CLAIM#{idempotency_key}"}}
            )
            if "Item" in existing:
                existing_claim_id = existing["Item"]["claim_id"]["S"]
                log.info("idempotency_hit", existing_claim_id=existing_claim_id)
                return ProcessClaimResponse(
                    claim_id=existing_claim_id,
                    status=PipelineStage.COMPLETE,
                    message=f"Duplicate claim — already processed as {existing_claim_id}",
                )
        except Exception:
            pass  # Table might not exist yet in dev

        # Upload PDF
        s3.put_object(
            Bucket=settings.claims_bucket,
            Key=s3_key,
            Body=file_bytes,
            ContentType="application/pdf",
            Metadata={
                "claim_id": claim_id,
                "oem": oem.value,
                "dealer_id": dealer_id,
                "idempotency_key": idempotency_key,
            }
        )
        log.info("claim_uploaded_to_s3", s3_key=s3_key)

        # Write idempotency record
        try:
            ddb.put_item(
                TableName=settings.dynamodb_table,
                Item={
                    "pk":              {"S": f"CLAIM#{idempotency_key}"},
                    "claim_id":        {"S": claim_id},
                    "s3_key":          {"S": s3_key},
                    "oem":             {"S": oem.value},
                    "dealer_id":       {"S": dealer_id},
                    "stage":           {"S": PipelineStage.RECEIVED.value},
                    "idempotency_key": {"S": idempotency_key},
                },
                ConditionExpression="attribute_not_exists(pk)"
            )
        except Exception as e:
            log.warning("dynamodb_write_failed", error=str(e))

    except Exception as e:
        log.error("s3_upload_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

    # Import here to avoid circular imports
    from app.agent.graph import run_claim_pipeline

    # Run pipeline (async in production via Lambda trigger; inline here for demo)
    try:
        result = await run_claim_pipeline(
            claim_id=claim_id,
            oem=oem,
            dealer_id=dealer_id,
            s3_key=s3_key,
            idempotency_key=idempotency_key,
        )
        return ProcessClaimResponse(
            claim_id=claim_id,
            status=PipelineStage.COMPLETE if not result.requires_human else PipelineStage.DECIDING,
            result=result,
            message="Claim processed successfully" if not result.requires_human
                    else "Claim escalated for human review",
        )
    except Exception as e:
        log.error("pipeline_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Pipeline failed: {str(e)}")


@router.get("/{claim_id}", response_model=ProcessClaimResponse)
async def get_claim_status(claim_id: str, _: str = Depends(verify_api_key)):
    """Poll claim status — used by the frontend for live pipeline updates."""
    try:
        ddb = boto3.client("dynamodb", region_name=settings.aws_region)
        item = ddb.get_item(
            TableName=settings.dynamodb_table,
            Key={"pk": {"S": f"RESULT#{claim_id}"}}
        )
        if "Item" not in item:
            return ProcessClaimResponse(
                claim_id=claim_id,
                status=PipelineStage.RECEIVED,
                message="Processing...",
            )
        stage = item["Item"].get("stage", {}).get("S", "received")
        return ProcessClaimResponse(
            claim_id=claim_id,
            status=PipelineStage(stage),
            message=f"Stage: {stage}",
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{claim_id}/approve")
async def approve_claim(claim_id: str, _: str = Depends(verify_api_key)):
    """HITL: warranty specialist approves an escalated claim."""
    log.info("hitl_approved", claim_id=claim_id)
    # Resume LangGraph from checkpoint — implementation in Phase 4
    return {"claim_id": claim_id, "action": "approved", "status": "resuming_agent"}


@router.post("/{claim_id}/reject")
async def reject_claim(claim_id: str, reason: str = "", _: str = Depends(verify_api_key)):
    """HITL: warranty specialist rejects an escalated claim."""
    log.info("hitl_rejected", claim_id=claim_id, reason=reason)
    return {"claim_id": claim_id, "action": "rejected", "reason": reason}
