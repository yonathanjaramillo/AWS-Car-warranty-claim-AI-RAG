import json
import time
import boto3
from typing import Optional
from app.config import get_settings
from app.models.claim import OEM, ValidationResult, PolicyMatch
from app.observability.logger import get_logger

log = get_logger(__name__)
settings = get_settings()

class KnowledgeBaseRAG:
    def __init__(self):
        self.bedrock_runtime = boto3.client("bedrock-runtime", region_name=settings.aws_region)

    def get_kb_id(self, oem):
        kb_map = {OEM.FORD: settings.kb_id_ford, OEM.GM: settings.kb_id_gm, OEM.TOYOTA: settings.kb_id_toyota}
        return kb_map.get(oem) or None

    def validate_claim(self, claim_id, oem, vin, repair_date, labor_op_code, claim_amount, mileage=None):
        log.info("rag_validation_started", claim_id=claim_id, oem=oem.value)
        return self._fallback_validation(claim_id, oem, labor_op_code, claim_amount)

    def _fallback_validation(self, claim_id, oem, labor_op_code, claim_amount):
        policy_text = self._load_local_policy(oem)
        prompt = f"""You are a warranty claim validator. Using ONLY the policy below, validate this claim.

POLICY:
{policy_text}

CLAIM:
- Labor Op Code: {labor_op_code}
- Claim Amount: ${claim_amount}

Respond in JSON only:
{{"is_valid": true, "reason": "explain why", "policy_section": "section number"}}
Return ONLY valid JSON, no markdown, no extra text."""

        try:
            response = self.bedrock_runtime.invoke_model(
                modelId=settings.bedrock_model_id,
                body=json.dumps({"anthropic_version": "bedrock-2023-05-31", "max_tokens": 500, "temperature": 0.0, "messages": [{"role": "user", "content": prompt}]}),
                contentType="application/json",
            )
            result_text = json.loads(response["body"].read())["content"][0]["text"]
            result_text = result_text.strip().replace("```json","").replace("```","").strip()
            result = json.loads(result_text)
            is_valid = result.get("is_valid", False)
            reason = result.get("reason", "Validation completed")
            section = result.get("policy_section", "general")
            log.info("fallback_validation_completed", claim_id=claim_id, is_valid=is_valid)
            return ValidationResult(
                claim_id=claim_id, oem=oem, is_valid=is_valid,
                policy_matches=[PolicyMatch(policy_id=f"{oem.value}-local", policy_name=f"{oem.value.upper()} Warranty Policy", section=section, content=reason, score=0.95)],
                validation_note=reason,
            )
        except Exception as e:
            log.error("validation_failed", error=str(e))
            return ValidationResult(claim_id=claim_id, oem=oem, is_valid=False, policy_matches=[], validation_note=f"Validation error: {str(e)[:200]}")

    def _load_local_policy(self, oem):
        import os
        files = {OEM.FORD: "data/mock/oem_policies/ford_warranty_policy.md", OEM.GM: "data/mock/oem_policies/gm_warranty_policy.md", OEM.TOYOTA: "data/mock/oem_policies/toyota_warranty_policy.md"}
        path = files.get(oem, "data/mock/oem_policies/ford_warranty_policy.md")
        try:
            with open(path, "r") as f: return f.read()
        except: return "Basic warranty: 3 years/36,000 miles. Labor ops 06-10A and 06-10B covered."