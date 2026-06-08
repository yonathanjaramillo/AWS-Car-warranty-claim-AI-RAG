"""
FastAPI application entry point.

WHY FASTAPI (tell Mike):
FastAPI gives us async request handling, automatic OpenAPI docs,
and Pydantic v2 validation at the boundary — all in one.
The middleware here adds structured JSON logging to every request
so CloudWatch gets claim_id, latency, and status automatically.
"""
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.observability.logger import configure_logging, get_logger
from app.api.routes import claims, health

settings = get_settings()
configure_logging(settings.log_level)
log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("warranty_ai_startup", environment=settings.environment, region=settings.aws_region)
    yield
    log.info("warranty_ai_shutdown")


app = FastAPI(
    title="Warranty Claim AI",
    description="AWS-native warranty claim processing — Bedrock · RAG · LangGraph",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow the React frontend (S3/CloudFront in prod, localhost in dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://*.cloudfront.net"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def structured_logging_middleware(request: Request, call_next) -> Response:
    """
    Log every request with latency — gives CloudWatch the raw data
    for latency-per-endpoint dashboards with zero extra instrumentation.
    """
    request_id = str(uuid.uuid4())[:8]
    start = time.perf_counter()

    log.info(
        "request_started",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
    )

    response = await call_next(request)
    latency_ms = int((time.perf_counter() - start) * 1000)

    log.info(
        "request_completed",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        latency_ms=latency_ms,
    )
    return response


# Routes
app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(claims.router, prefix="/claims", tags=["claims"])
