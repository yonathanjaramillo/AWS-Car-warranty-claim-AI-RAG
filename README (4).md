






<img width="1920" height="1080" alt="{AF0D770C-13EA-4189-9AD9-44924EC2F4E1}" src="https://github.com/user-attachments/assets/6ba17de2-147a-40b7-9fb9-9ea7bf7f7775" />


# AWS Car Warranty Claim AI — RAG · Bedrock · LangGraph · Textract

> Production-grade AWS-native AI pipeline for automotive warranty claim processing. Built to demonstrate real-world document intelligence, RAG validation, and agentic workflow orchestration on Amazon Bedrock. 

![AWS](https://img.shields.io/badge/AWS-Bedrock-FF9900?style=flat&logo=amazon-aws) ![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=flat&logo=python) ![FastAPI](https://img.shields.io/badge/FastAPI-0.111-009688?style=flat&logo=fastapi) ![LangGraph](https://img.shields.io/badge/LangGraph-Agent-6366F1?style=flat)

---

## What this does

Upload a warranty claim PDF. The system extracts structured fields using Amazon Textract, validates them against OEM policy documents via Bedrock RAG, and returns an approve/reject/escalate decision with a full audit trail — all in under 15 seconds for $0.0045 per claim.

```
PDF upload → S3 → Textract → VIN/date/code extraction → Bedrock RAG → OEM policy validation → Decision
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        FastAPI (ECS Fargate)                     │
│   POST /claims/submit → pipeline → ClaimResult JSON             │
└────────────────────────┬────────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
   ┌──────────┐   ┌─────────────┐   ┌──────────────┐
   │    S3    │   │  DynamoDB   │   │  CloudWatch  │
   │  Claims  │   │ Idempotency │   │  Structured  │
   │  bucket  │   │   + State   │   │   Logging    │
   └──────────┘   └─────────────┘   └──────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Document Intelligence Layer                    │
│                                                                  │
│   Textract AnalyzeDocument                                       │
│   → confidence scoring per field                                 │
│   → deterministic parsers (VIN checksum, ISO date, currency)    │
│   → Claude Vision fallback for low-confidence fields            │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                      RAG Validation Layer                        │
│                                                                  │
│   Bedrock Knowledge Base (per OEM — Ford / GM / Toyota)         │
│   → RetrieveAndGenerate API                                      │
│   → Bedrock Guardrails (grounding + PII redaction)              │
│   → Retrieval evaluation with golden datasets                   │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                     Agent Decision Layer                         │
│                                                                  │
│   LangGraph state machine                                        │
│   → extract_node → validate_node → decision_node                │
│   → HITL interrupt for ambiguous/high-value claims              │
│   → DynamoDB checkpointing                                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## Tech stack

| Layer | Services |
|---|---|
| **AI / LLM** | Amazon Bedrock (Claude 3), Bedrock Knowledge Bases, RetrieveAndGenerate, Guardrails |
| **Document intelligence** | Amazon Textract, Claude Vision multimodal fallback |
| **Orchestration** | LangGraph state machine, Bedrock AgentCore Runtime, MCP SDK |
| **Backend** | Python 3.12, FastAPI, Pydantic v2, asyncio, Boto3 |
| **AWS infra** | ECS Fargate, Lambda, S3, S3 Events, EventBridge, DynamoDB |
| **Security** | Cognito OIDC/PKCE, WAF, Secrets Manager, least-privilege IAM |
| **Observability** | CloudWatch structured JSON logging, cost-per-claim metrics |
| **IaC / CI/CD** | Terraform, GitHub Actions, Docker (ARM64) |

---

## Key features

**Confidence-gated dual extraction**
Textract runs first (~$0.0015/page). Fields below 85% confidence automatically fall back to Claude Vision. Every field carries its source and confidence score for full audit traceability.

**Deterministic field parsers**
VINs validated with NHTSA checksum. Dates normalized to ISO 8601. Currency extracted as Decimal. Labor op codes matched against OEM patterns. The LLM never parses structured fields — parsers don't hallucinate.

**Isolated Knowledge Bases per OEM**
Ford, GM, and Toyota each get their own Bedrock KB. Policy updates for one OEM never affect another. Physical tenant isolation, not just filters.

**Idempotency by design**
Every claim gets a content hash. DynamoDB prevents double-processing on Lambda retries. Safe to replay failed claims without risk of duplicate submissions.

**Full audit trail**
Every pipeline stage, tool call, and decision is logged to CloudWatch as structured JSON with timestamp, latency_ms, and cost_usd. Every claim decision is defensible.

**Cost tracking**
$0.0045 per claim end-to-end (Textract + Bedrock). CloudWatch cost-per-claim dashboard out of the box.

---

## Project structure

```
warranty-claim-ai/
├── app/
│   ├── api/routes/
│   │   ├── claims.py          # POST /claims/submit, GET /claims/{id}
│   │   └── health.py          # GET /health/
│   ├── models/claim.py        # Pydantic v2 typed models
│   ├── extraction/
│   │   ├── textract.py        # Textract AnalyzeDocument wrapper
│   │   ├── vision.py          # Claude Vision fallback
│   │   ├── parsers.py         # VIN / date / currency / labor op parsers
│   │   └── pipeline.py        # Confidence-gated extraction orchestrator
│   ├── rag/
│   │   └── knowledge_base.py  # Bedrock KB + RetrieveAndGenerate + fallback
│   ├── agent/
│   │   └── graph.py           # LangGraph state machine
│   ├── observability/
│   │   └── logger.py          # Structured JSON CloudWatch logging
│   └── config.py              # Pydantic-settings config
├── lambdas/
│   └── doc_processor/         # S3 Event → Textract trigger
├── data/mock/
│   ├── sample_claim.pdf       # Synthetic warranty claim for testing
│   └── oem_policies/          # Mock Ford / GM / Toyota policy docs
├── frontend/
│   └── index.html             # Single-file React-free UI
├── tests/
│   └── test_phase1.py
├── setup_aws.py               # One-command AWS resource setup
└── Dockerfile                 # ARM64 for AgentCore compatibility
```

---

## Quick start

### Prerequisites
- Python 3.12+
- AWS CLI configured (`aws configure`)
- AWS account with Bedrock access enabled

### 1. Clone and install
```bash
git clone https://github.com/yonathanjaramillo/AWS-Car-warranty-claim-AI-RAG.git
cd AWS-Car-warranty-claim-AI-RAG
pip install fastapi uvicorn pydantic pydantic-settings boto3 langgraph langchain-aws python-multipart structlog
```

### 2. Set up AWS resources
```bash
python setup_aws.py
# Creates: S3 bucket, DynamoDB table, verifies Bedrock access
```

### 3. Generate sample claim PDF
```bash
pip install reportlab
python -c "
import os; os.makedirs('data/mock', exist_ok=True)
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
doc = SimpleDocTemplate('data/mock/sample_claim.pdf', pagesize=letter)
styles = getSampleStyleSheet()
data = [['Field','Value'],['VIN','1FTFW1ET5DKE12345'],['Repair Date','03/15/2024'],['Labor Op Code','06-10B'],['Claim Amount','\$847.50'],['Part Number','FL3Z-6600-B'],['Mileage','34218'],['Dealer Code','FORD-MIA-0042']]
t = Table(data, colWidths=[3*inch, 4*inch])
t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.darkblue),('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,-1),'Helvetica'),('GRID',(0,0),(-1,-1),1,colors.black)]))
story = [Paragraph('WARRANTY CLAIM FORM', styles['Title']), Spacer(1,20), t]
doc.build(story)
print('Sample claim PDF created!')
"
```

### 4. Configure environment
```bash
# Set these environment variables (or create .env from .env.example)
set AWS_REGION=us-east-1
set API_KEY=dev-key-change-in-prod
set ENVIRONMENT=development
set CLAIMS_BUCKET=warranty-claim-ai-claims
set DYNAMODB_TABLE=warranty-claim-ai-state
```

### 5. Start the server
```bash
uvicorn app.api.main:app --reload --port 8000
```

### 6. Open the UI
Open `frontend/index.html` in your browser. Upload `data/mock/sample_claim.pdf`, select Ford, click Process Claim.

Or use the Swagger docs at `http://localhost:8000/docs`.

---

## API

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/claims/submit` | Upload PDF + trigger pipeline |
| `GET` | `/claims/{id}` | Poll claim status |
| `POST` | `/claims/{id}/approve` | HITL: approve escalated claim |
| `POST` | `/claims/{id}/reject` | HITL: reject escalated claim |
| `GET` | `/health/` | Service health + AWS connectivity |

**Authentication:** `X-API-Key` header (Cognito OIDC in production)

---

## Sample response

```json
{
  "claim_id": "WC-6C7D028E",
  "status": "complete",
  "result": {
    "oem": "ford",
    "decision": "approved",
    "confidence": 0.95,
    "decision_reason": "Labor op 06-10B covered under Ford basic warranty Section 4.2",
    "policy_citations": ["FORD Warranty Policy - Section 4.2"],
    "extracted": {
      "vin": { "value": "1FTFW1ET5DKE12345", "source": "textract", "confidence": 0.95 },
      "repair_date": { "value": "2024-03-15", "source": "textract", "confidence": 0.96 },
      "labor_op_code": { "value": "06-10B", "source": "textract", "confidence": 0.96 },
      "claim_amount": { "value": "847.50", "source": "textract", "confidence": 0.95 }
    },
    "total_latency_ms": 7152,
    "total_cost_usd": 0.0045
  }
}
```

---

## Cost breakdown

| Service | Cost | Notes |
|---|---|---|
| Amazon Textract | ~$0.0015/claim | AnalyzeDocument, 1 page |
| Amazon Bedrock | ~$0.003/claim | Claude 3 Haiku, RAG validation |
| S3 | ~$0.000023/claim | Storage + requests |
| DynamoDB | ~$0.000001/claim | On-demand pricing |
| **Total** | **~$0.0045/claim** | End-to-end |

---

## Built by

**Yonathan Jaramillo** — AWS Bedrock Software Engineer · Founder, Waku Cloud

AWS Certified Solutions Architect · AWS AI Practitioner · 5x AWS Certified

[LinkedIn](https://linkedin.com/in/yonathan-jaramillo) · [GitHub](https://github.com/yonathanjaramillo)

---

*Built as a production-grade demonstration of AWS-native AI platform engineering for automotive warranty claim processing.*
