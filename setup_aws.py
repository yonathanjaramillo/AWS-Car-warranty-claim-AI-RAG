import boto3

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
