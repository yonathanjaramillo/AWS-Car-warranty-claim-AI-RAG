import time
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
