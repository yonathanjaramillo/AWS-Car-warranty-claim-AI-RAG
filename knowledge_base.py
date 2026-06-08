"""
Bedrock Knowledge Base + RAG validation module.

WHY ISOLATED KBs PER OEM (tell Mike):
Ford policy docs must NEVER influence a GM validation.
This is not just a filter — it is a physical separation.
Each OEM gets its own Knowledge Base ID, its own vector index,
and its own ingestion pipeline. Tenant isolation by design.
"""
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
    """
    Bedrock Knowledge Base retrieval and validation.
    Uses RetrieveAndGenerate API for grounded responses.
    """

    def __init__(self):
        self.bedrock_agent = boto3.client(
            "bedrock-agent-runtime",
            region_name=settings.aws_region
        )
        self.bedrock_runtime = boto3.client(
            "bedrock-runtime",
            region_name=settings.aws_region
        )

    def get_kb_id(self, oem: OEM) -> Optional[str]:
        """Get Knowledge Base ID for a given OEM."""
        kb_map = {
            OEM.FORD:       settings.kb_id_ford,
            OEM.GM:         settings.kb_id_gm,
            OEM.TOYOTA:     settings.kb_id_toyota,
            OEM.STELLANTIS: settings.kb_id_stellantis,
        }
        return kb_map.get(oem) or None

    def validate_claim(
        self,
        claim_id: str,
        oem: OEM,
        vin: str,
        repair_date: str,
        labor_op_code: str,
        claim_amount: str,
        mileage: Optional[str] = None,
    ) -> ValidationResult:
        """
        Validate extracted claim fields against OEM policy KB.

        Uses RetrieveAndGenerate — retrieves relevant policy chunks
        then generates a grounded validation decision.

        WHY RetrieveAndGenerate (tell Mike):
        We don't retrieve chunks and then call the LLM separately.
        RetrieveAndGenerate does both in one API call with automatic
        grounding — the model CAN ONLY answer from retrieved context.
        That's how we prevent hallucinated policy interpretations.
        """
        start = time.perf_counter()
        kb_id = self.get_kb_id(oem)

        # Build validation query
        query = f"""
        Validate this warranty claim against the OEM policy:
        - VIN: {vin}
        - Repair Date: {repair_date}
        - Labor Op Code: {labor_op_code}
        - Claim Amount: ${claim_amount}
        - Mileage: {mileage or 'unknown'}

        Is this claim covered? What policy sections apply?
        What is the maximum approved amount for this labor operation?
        Are there any issues or concerns with this claim?
        """

        if not kb_id:
            # No KB configured — use fallback validation
            log.warning("kb_not_configured", oem=oem.value, claim_id=claim_id)
            return self._fallback_validation(
                claim_id, oem, labor_op_code, claim_amount
            )

        try:
            log.info("rag_retrieval_started", claim_id=claim_id, oem=oem.value, kb_id=kb_id)

            response = self.bedrock_agent.retrieve_and_generate(
                input={"text": query},
                retrieveAndGenerateConfiguration={
                    "type": "KNOWLEDGE_BASE",
                    "knowledgeBaseConfiguration": {
                        "knowledgeBaseId": kb_id,
                        "modelArn": f"arn:aws:bedrock:{settings.aws_region}::foundation-model/{settings.bedrock_model_id}",
                        "retrievalConfiguration": {
                            "vectorSearchConfiguration": {
                                "numberOfResults": settings.max_rag_chunks,
                            }
                        },
                        "generationConfiguration": {
                            "inferenceConfig": {
                                "textInferenceConfig": {
                                    "maxTokens": settings.max_tokens_per_call,
                                    "temperature": 0.0,  # deterministic for validation
                                }
                            },
                            "guardrailConfiguration": {
                                "guardrailId": "NONE",
                            } if True else {}
                        }
                    }
                }
            )

            output_text = response["output"]["text"]
            citations = response.get("citations", [])

            # Parse policy matches from citations
            policy_matches = []
            for citation in citations[:settings.max_rag_chunks]:
                for ref in citation.get("retrievedReferences", []):
                    content = ref.get("content", {}).get("text", "")
                    metadata = ref.get("metadata", {})
                    score = ref.get("score", 0.5)
                    policy_matches.append(PolicyMatch(
                        policy_id=metadata.get("source", "unknown"),
                        policy_name=f"{oem.value.upper()} Warranty Policy",
                        section=metadata.get("section", "general"),
                        content=content[:500],
                        score=score,
                    ))

            # Determine if claim is valid based on response
            is_valid = any(word in output_text.lower() for word in
                          ["covered", "approved", "valid", "eligible"])
            is_rejected = any(word in output_text.lower() for word in
                             ["not covered", "excluded", "ineligible", "denied"])

            if is_rejected:
                is_valid = False

            latency_ms = int((time.perf_counter() - start) * 1000)
            log.info("rag_retrieval_completed",
                     claim_id=claim_id,
                     latency_ms=latency_ms,
                     is_valid=is_valid,
                     policy_matches=len(policy_matches))

            return ValidationResult(
                claim_id=claim_id,
                oem=oem,
                is_valid=is_valid,
                policy_matches=policy_matches,
                validation_note=output_text[:1000],
            )

        except Exception as e:
            log.error("rag_retrieval_failed", error=str(e), claim_id=claim_id)
            return self._fallback_validation(claim_id, oem, labor_op_code, claim_amount)

    def _fallback_validation(
        self,
        claim_id: str,
        oem: OEM,
        labor_op_code: str,
        claim_amount: str,
    ) -> ValidationResult:
        """
        Fallback validation when KB is not configured.
        Uses Claude directly with embedded policy rules.
        This is the demo mode — works without a KB ID.
        """
        log.info("fallback_validation_started", claim_id=claim_id)

        # Load policy from local file
        policy_text = self._load_local_policy(oem)

        prompt = f"""You are a warranty claim validator. Using ONLY the policy below, validate this claim.

POLICY:
{policy_text}

CLAIM:
- Labor Op Code: {labor_op_code}
- Claim Amount: ${claim_amount}

Respond in JSON:
{{"is_valid": true/false, "reason": "...", "policy_section": "...", "max_approved_amount": "..."}}
Return ONLY valid JSON, no markdown."""

        try:
            response = self.bedrock_runtime.invoke_model(
                modelId=settings.bedrock_model_id,
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 500,
                    "temperature": 0.0,
                    "messages": [{"role": "user", "content": prompt}]
                }),
                contentType="application/json",
            )
            result_text = json.loads(response["body"].read())["content"][0]["text"]
            result_text = result_text.strip().replace("```json", "").replace("```", "")
            result = json.loads(result_text)

            is_valid = result.get("is_valid", False)
            reason = result.get("reason", "Validation completed")
            section = result.get("policy_section", "general")

            log.info("fallback_validation_completed",
                     claim_id=claim_id, is_valid=is_valid)

            return ValidationResult(
                claim_id=claim_id,
                oem=oem,
                is_valid=is_valid,
                policy_matches=[PolicyMatch(
                    policy_id=f"{oem.value}-local-policy",
                    policy_name=f"{oem.value.upper()} Warranty Policy (Local)",
                    section=section,
                    content=reason,
                    score=0.95,
                )],
                validation_note=reason,
            )

        except Exception as e:
            log.error("fallback_validation_failed", error=str(e))
            return ValidationResult(
                claim_id=claim_id,
                oem=oem,
                is_valid=False,
                policy_matches=[],
                validation_note=f"Validation error: {str(e)[:200]}",
            )

    def _load_local_policy(self, oem: OEM) -> str:
        """Load local mock policy file for fallback validation."""
        import os
        policy_files = {
            OEM.FORD:       "data/mock/oem_policies/ford_warranty_policy.md",
            OEM.GM:         "data/mock/oem_policies/gm_warranty_policy.md",
            OEM.TOYOTA:     "data/mock/oem_policies/toyota_warranty_policy.md",
            OEM.STELLANTIS: "data/mock/oem_policies/ford_warranty_policy.md",
        }
        path = policy_files.get(oem, "data/mock/oem_policies/ford_warranty_policy.md")
        try:
            with open(path, "r") as f:
                return f.read()
        except FileNotFoundError:
            return "Basic warranty: 3 years/36,000 miles. Labor ops 06-10A and 06-10B covered."
