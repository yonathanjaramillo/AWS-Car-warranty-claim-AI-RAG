from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    aws_region:             str = "us-east-1"
    aws_account_id:         str = ""
    claims_bucket:          str = "warranty-claim-ai-claims"
    policies_bucket:        str = "warranty-claim-ai-policies"
    bedrock_model_id:       str = "anthropic.claude-3-haiku-20240307-v1:0"
    bedrock_vision_model:   str = "anthropic.claude-3-haiku-20240307-v1:0"
    bedrock_embed_model:    str = "amazon.titan-embed-text-v2:0"
    kb_id_ford:             str = ""
    kb_id_gm:               str = ""
    kb_id_toyota:           str = ""
    kb_id_stellantis:       str = ""
    dynamodb_table:         str = "warranty-claim-ai-state"
    textract_confidence_threshold: float = 0.85
    rag_confidence_threshold:      float = 0.75
    max_tokens_per_call:    int   = 1000
    max_rag_chunks:         int   = 5
    log_level:              str   = "INFO"
    environment:            str   = "development"
    api_key:                str   = "dev-key-change-in-prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()
