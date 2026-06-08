"""
Lambda document processor — triggered by S3 Events.

WHY LAMBDA (tell Mike):
Lambda scales to zero when there are no claims — zero cost at idle.
S3 Events trigger it automatically on upload — no polling needed.
The idempotency check at the top prevents double-processing if
Lambda retries (which it does automatically on failure).
"""
import json
import os
import boto3
import urllib.parse

# Lambda environment settings
REGION = os.environ.get("AWS_REGION", "us-east-1")
DYNAMODB_TABLE = os.environ.get("DYNAMODB_TABLE", "warranty-claim-ai-state")

ddb = boto3.client("dynamodb", region_name=REGION)


def lambda_handler(event, context):
    """
    S3 Event → extract claim metadata → write to DynamoDB → trigger pipeline.

    This Lambda is the bridge between S3 upload and the FastAPI pipeline.
    In production the FastAPI service polls DynamoDB for new claims.
    """
    print(json.dumps({"event": "lambda_triggered", "record_count": len(event.get("Records", []))}))

    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
        size = record["s3"]["object"].get("size", 0)

        print(json.dumps({"event": "s3_record_received", "bucket": bucket, "key": key, "size": size}))

        # Parse claim metadata from S3 key
        # Key format: claims/{oem}/{dealer_id}/{claim_id}/{filename}
        parts = key.split("/")
        if len(parts) < 4:
            print(json.dumps({"event": "invalid_key_format", "key": key}))
            continue

        oem = parts[1] if len(parts) > 1 else "unknown"
        dealer_id = parts[2] if len(parts) > 2 else "unknown"
        claim_id = parts[3] if len(parts) > 3 else "unknown"

        # Idempotency check
        try:
            existing = ddb.get_item(
                TableName=DYNAMODB_TABLE,
                Key={"pk": {"S": f"LAMBDA#{claim_id}"}}
            )
            if "Item" in existing:
                print(json.dumps({"event": "idempotency_hit", "claim_id": claim_id}))
                continue
        except Exception as e:
            print(json.dumps({"event": "dynamodb_check_failed", "error": str(e)}))

        # Write processing record
        try:
            ddb.put_item(
                TableName=DYNAMODB_TABLE,
                Item={
                    "pk":        {"S": f"LAMBDA#{claim_id}"},
                    "claim_id":  {"S": claim_id},
                    "s3_key":    {"S": key},
                    "bucket":    {"S": bucket},
                    "oem":       {"S": oem},
                    "dealer_id": {"S": dealer_id},
                    "stage":     {"S": "extracting"},
                    "size":      {"N": str(size)},
                },
                ConditionExpression="attribute_not_exists(pk)"
            )
            print(json.dumps({"event": "claim_queued", "claim_id": claim_id, "oem": oem}))
        except ddb.exceptions.ConditionalCheckFailedException:
            print(json.dumps({"event": "idempotency_race_condition", "claim_id": claim_id}))
            continue
        except Exception as e:
            print(json.dumps({"event": "dynamodb_write_failed", "error": str(e)}))
            raise

    return {"statusCode": 200, "body": json.dumps({"processed": len(event.get("Records", []))})}
