import boto3
from fastapi import APIRouter
from app.models.claim import HealthResponse
from app.config import get_settings

router = APIRouter()
settings = get_settings()


@router.get("/", response_model=HealthResponse)
async def health_check():
    """Health check — verifies AWS connectivity for Bedrock and S3."""
    services = {}

    # Check S3
    try:
        s3 = boto3.client("s3", region_name=settings.aws_region)
        s3.head_bucket(Bucket=settings.claims_bucket)
        services["s3"] = "ok"
    except Exception as e:
        services["s3"] = f"error: {str(e)[:60]}"

    # Check Bedrock reachability
    try:
        bedrock = boto3.client("bedrock", region_name=settings.aws_region)
        bedrock.list_foundation_models(byOutputModality="TEXT")
        services["bedrock"] = "ok"
    except Exception as e:
        services["bedrock"] = f"error: {str(e)[:60]}"

    # Check DynamoDB
    try:
        ddb = boto3.client("dynamodb", region_name=settings.aws_region)
        ddb.describe_table(TableName=settings.dynamodb_table)
        services["dynamodb"] = "ok"
    except Exception as e:
        services["dynamodb"] = f"error: {str(e)[:60]}"

    return HealthResponse(services=services)
