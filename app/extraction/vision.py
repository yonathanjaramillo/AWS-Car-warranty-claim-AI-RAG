import base64
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
