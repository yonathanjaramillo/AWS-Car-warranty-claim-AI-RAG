import os

files = {
"app/extraction/__init__.py": "",

"app/extraction/parsers.py": '''import re
from decimal import Decimal, InvalidOperation
from typing import Optional

def parse_vin(raw):
    if not raw: return None
    vin = raw.upper().strip().replace("-","").replace(" ","")
    if len(vin) != 17: return None
    if not re.match(r"^[A-HJ-NPR-Z0-9]{17}$", vin): return None
    return vin

def parse_date(raw):
    if not raw: return None
    raw = raw.strip()
    patterns = [
        (r"(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})", "mdy"),
        (r"(\d{4})[/\-\.](\d{1,2})[/\-\.](\d{1,2})", "ymd"),
    ]
    for pattern, fmt in patterns:
        m = re.search(pattern, raw)
        if m:
            try:
                g = m.groups()
                if fmt == "mdy": mo,d,y = int(g[0]),int(g[1]),int(g[2])
                else: y,mo,d = int(g[0]),int(g[1]),int(g[2])
                return f"{y:04d}-{mo:02d}-{d:02d}"
            except: continue
    return None

def parse_currency(raw):
    if not raw: return None
    cleaned = re.sub(r"[^\d.]", "", raw.strip())
    try: return f"{Decimal(cleaned):.2f}"
    except: return None

def parse_labor_op_code(raw):
    if not raw: return None
    raw = raw.upper().strip()
    m = re.search(r"\b\d{2}-\d{2}[A-Z]?\b", raw)
    if m: return m.group(0)
    if re.match(r"^[A-Z0-9\-]{4,12}$", raw): return raw
    return None

def parse_part_number(raw):
    if not raw: return None
    cleaned = raw.upper().strip().replace(" ","-")
    if re.match(r"^[A-Z0-9\-]{6,20}$", cleaned): return cleaned
    return None

def parse_mileage(raw):
    if not raw: return None
    digits = re.sub(r"[^\d]","",raw.strip())
    try:
        m = int(digits)
        if 0 < m < 1000000: return m
    except: pass
    return None
''',

"app/extraction/textract.py": '''import time
import boto3
from app.config import get_settings
from app.observability.logger import get_logger

log = get_logger(__name__)
settings = get_settings()

class TextractExtractor:
    def __init__(self):
        self.client = boto3.client("textract", region_name=settings.aws_region)

    def extract_from_s3(self, bucket, key):
        log.info("textract_started", bucket=bucket, key=key)
        start = time.perf_counter()
        try:
            response = self.client.analyze_document(
                Document={"S3Object": {"Bucket": bucket, "Name": key}},
                FeatureTypes=["FORMS", "TABLES"],
            )
            latency_ms = int((time.perf_counter() - start) * 1000)
            log.info("textract_completed", latency_ms=latency_ms)
            return response
        except Exception as e:
            log.error("textract_failed", error=str(e))
            return {}

    def extract_key_values(self, textract_response):
        if not textract_response: return {}
        blocks = textract_response.get("Blocks", [])
        block_map = {b["Id"]: b for b in blocks}
        kv = {}
        for block in blocks:
            if block["BlockType"] != "KEY_VALUE_SET": continue
            if "KEY" not in block.get("EntityTypes", []): continue
            key_text = self._get_text(block, block_map).strip().lower()
            key_conf = block.get("Confidence", 0) / 100
            for rel in block.get("Relationships", []):
                if rel["Type"] != "VALUE": continue
                for vid in rel["Ids"]:
                    vb = block_map.get(vid, {})
                    val_text = self._get_text(vb, block_map).strip()
                    val_conf = vb.get("Confidence", 0) / 100
                    if key_text and val_text:
                        kv[key_text] = {"value": val_text, "confidence": min(key_conf, val_conf)}
        return kv

    def _get_text(self, block, block_map):
        text = ""
        for rel in block.get("Relationships", []):
            if rel["Type"] == "CHILD":
                for cid in rel["Ids"]:
                    child = block_map.get(cid, {})
                    if child.get("BlockType") == "WORD":
                        text += child.get("Text", "") + " "
        return text.strip()

    def map_fields_to_claim(self, kv):
        mappings = {
            "vin": ["vin","vehicle identification number","vin number"],
            "repair_date": ["repair date","date of repair","service date","ro date","date"],
            "labor_op_code": ["labor op","labor operation","op code","operation code","labor code"],
            "claim_amount": ["claim amount","total amount","amount claimed","total claim","amount"],
            "part_number": ["part number","part #","part no","parts"],
            "mileage": ["mileage","odometer","miles"],
            "dealer_id": ["dealer code","dealer #","dealer id"],
        }
        mapped = {}
        for field, aliases in mappings.items():
            for alias in aliases:
                if alias in kv:
                    mapped[field] = kv[alias]
                    break
                for key in kv:
                    if alias in key or key in alias:
                        mapped[field] = kv[key]
                        break
                if field in mapped: break
        return mapped
''',

"app/extraction/vision.py": '''import base64
import json
import re
import boto3
from app.config import get_settings
from app.observability.logger import get_logger

log = get_logger(__name__)
settings = get_settings()

VISION_PROMPT = """Extract warranty claim fields. Return ONLY valid JSON:
{"vin":null,"repair_date":null,"labor_op_code":null,"claim_amount":null,"part_number":null,"mileage":null,"dealer_id":null}
Rules: extract only what you clearly see. VIN must be 17 chars. Amount as numbers only."""

class VisionExtractor:
    def __init__(self):
        self.client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
        self.s3 = boto3.client("s3", region_name=settings.aws_region)

    def extract_from_s3(self, bucket, key, low_confidence_fields=None):
        log.info("vision_started", key=key, fields=low_confidence_fields)
        try:
            resp = self.s3.get_object(Bucket=bucket, Key=key)
            file_b64 = base64.standard_b64encode(resp["Body"].read()).decode()
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": settings.max_tokens_per_call,
                "messages": [{"role":"user","content":[
                    {"type":"document","source":{"type":"base64","media_type":"application/pdf","data":file_b64}},
                    {"type":"text","text":VISION_PROMPT}
                ]}]
            })
            r = self.client.invoke_model(modelId=settings.bedrock_vision_model, body=body, contentType="application/json")
            text = json.loads(r["body"].read())["content"][0]["text"].strip()
            text = re.sub(r"```json|```","",text).strip()
            return json.loads(text)
        except Exception as e:
            log.error("vision_failed", error=str(e))
            return {}
''',

"app/extraction/pipeline.py": '''import time
from app.config import get_settings
from app.models.claim import OEM, ExtractedClaim, ExtractedField, ExtractionSource
from app.extraction.textract import TextractExtractor
from app.extraction.vision import VisionExtractor
from app.extraction.parsers import parse_vin, parse_date, parse_currency, parse_labor_op_code, parse_part_number, parse_mileage
from app.observability.logger import get_logger

log = get_logger(__name__)
settings = get_settings()

class ExtractionPipeline:
    def __init__(self):
        self.textract = TextractExtractor()
        self.vision = VisionExtractor()
        self.threshold = settings.textract_confidence_threshold

    async def extract(self, claim_id, oem, s3_key, idempotency_key):
        start = time.perf_counter()
        log.info("extraction_started", claim_id=claim_id)
        textract_response = self.textract.extract_from_s3(settings.claims_bucket, s3_key)
        kv = self.textract.extract_key_values(textract_response)
        mapped = self.textract.map_fields_to_claim(kv)
        low_conf = [f for f,d in mapped.items() if d.get("confidence",0) < self.threshold]
        vision_results = {}
        if low_conf or not mapped:
            vision_results = self.vision.extract_from_s3(settings.claims_bucket, s3_key, low_conf)

        def make_field(tv, vv, parser_fn):
            if tv and tv.get("confidence",0) >= self.threshold:
                p = parser_fn(tv["value"])
                if p: return ExtractedField(value=str(p), source=ExtractionSource.TEXTRACT, confidence=tv["confidence"], raw=tv["value"])
            if vv:
                p = parser_fn(str(vv))
                if p: return ExtractedField(value=str(p), source=ExtractionSource.VISION, confidence=0.82, raw=str(vv))
            if tv:
                p = parser_fn(tv["value"])
                if p: return ExtractedField(value=str(p), source=ExtractionSource.TEXTRACT, confidence=tv.get("confidence",0.5), raw=tv["value"])
            return None

        def fallback(val, source=ExtractionSource.TEXTRACT):
            return ExtractedField(value=val, source=source, confidence=0.0, raw="extraction_failed")

        vin_f = make_field(mapped.get("vin"), vision_results.get("vin"), parse_vin) or fallback("UNKNOWN")
        date_f = make_field(mapped.get("repair_date"), vision_results.get("repair_date"), parse_date) or fallback("unknown")
        labor_f = make_field(mapped.get("labor_op_code"), vision_results.get("labor_op_code"), parse_labor_op_code) or fallback("unknown")
        amount_f = make_field(mapped.get("claim_amount"), vision_results.get("claim_amount"), parse_currency) or fallback("0.00")
        part_f = make_field(mapped.get("part_number"), vision_results.get("part_number"), parse_part_number)
        mileage_raw = (mapped.get("mileage") or {}).get("value") or str(vision_results.get("mileage") or "")
        mileage_val = parse_mileage(mileage_raw)
        mileage_f = ExtractedField(value=str(mileage_val), source=ExtractionSource.TEXTRACT, confidence=0.9, raw=mileage_raw) if mileage_val else None

        latency_ms = int((time.perf_counter() - start) * 1000)
        log.info("extraction_completed", claim_id=claim_id, latency_ms=latency_ms)
        return ExtractedClaim(claim_id=claim_id, oem=oem, vin=vin_f, repair_date=date_f,
            labor_op_code=labor_f, claim_amount=amount_f, part_number=part_f,
            mileage=mileage_f, s3_key=s3_key, idempotency_key=idempotency_key)
''',

"app/agent/__init__.py": "",

"app/agent/graph.py": '''from app.models.claim import OEM, ClaimResult, ClaimDecision, AuditEntry, PipelineStage, ValidationResult, PolicyMatch
from app.extraction.pipeline import ExtractionPipeline
from app.observability.logger import get_logger
from datetime import datetime
import time

log = get_logger(__name__)

async def run_claim_pipeline(claim_id, oem, dealer_id, s3_key, idempotency_key):
    start = time.perf_counter()
    audit = []
    audit.append(AuditEntry(stage=PipelineStage.RECEIVED, action="pipeline_started"))

    pipeline = ExtractionPipeline()
    extracted = await pipeline.extract(claim_id=claim_id, oem=oem, s3_key=s3_key, idempotency_key=idempotency_key)
    audit.append(AuditEntry(stage=PipelineStage.EXTRACTING, action="extraction_completed",
        detail=f"VIN={extracted.vin.value} confidence={extracted.vin.confidence:.2f}"))

    validation = ValidationResult(
        claim_id=claim_id, oem=oem, is_valid=True,
        policy_matches=[PolicyMatch(policy_id="MOCK-001", policy_name="Mock Policy",
            section="4.2", content="RAG validation will be implemented in Phase 3", score=0.0)],
        validation_note="Phase 3 RAG validation pending",
    )
    audit.append(AuditEntry(stage=PipelineStage.VALIDATING, action="validation_completed", detail="mock_validation"))

    total_ms = int((time.perf_counter() - start) * 1000)
    audit.append(AuditEntry(stage=PipelineStage.COMPLETE, action="pipeline_completed", latency_ms=total_ms))

    return ClaimResult(
        claim_id=claim_id, oem=oem,
        decision=ClaimDecision.ESCALATED,
        confidence=0.0,
        decision_reason="Phase 3 RAG validation pending — claim escalated for manual review",
        policy_citations=["Phase 3 will add real policy citations"],
        extracted=extracted,
        validation=validation,
        audit_trail=audit,
        total_latency_ms=total_ms,
        total_cost_usd=0.002,
        requires_human=True,
    )
''',

"setup_aws.py": '''import boto3

REGION = "us-east-1"
CLAIMS_BUCKET = "warranty-claim-ai-claims"
TABLE = "warranty-claim-ai-state"

def run():
    print("Setting up AWS resources...")
    s3 = boto3.client("s3", region_name=REGION)
    try:
        s3.create_bucket(Bucket=CLAIMS_BUCKET)
        print(f"S3 bucket created: {CLAIMS_BUCKET}")
    except Exception as e:
        print(f"S3: {e}")

    ddb = boto3.client("dynamodb", region_name=REGION)
    try:
        ddb.create_table(TableName=TABLE,
            KeySchema=[{"AttributeName":"pk","KeyType":"HASH"}],
            AttributeDefinitions=[{"AttributeName":"pk","AttributeType":"S"}],
            BillingMode="PAY_PER_REQUEST")
        print(f"DynamoDB table created: {TABLE}")
    except Exception as e:
        print(f"DynamoDB: {e}")

    bedrock = boto3.client("bedrock", region_name=REGION)
    try:
        models = bedrock.list_foundation_models(byOutputModality="TEXT")
        claude = [m for m in models["modelSummaries"] if "claude" in m["modelId"].lower()]
        print(f"Bedrock OK - {len(claude)} Claude models available")
    except Exception as e:
        print(f"Bedrock: {e}")

    print("Setup complete!")

if __name__ == "__main__":
    run()
''',
}

for path, content in files.items():
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w") as f:
        f.write(content)
    print(f"Created: {path}")

print("\nAll Phase 2 files created!")