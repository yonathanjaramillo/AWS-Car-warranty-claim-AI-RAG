import time
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
