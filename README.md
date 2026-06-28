# Wayco — AI-Powered Personal Injury Intake System

Built for Wayco (YC W26). An end-to-end voice AI intake pipeline for personal injury law firms — from inbound phone call to signed retainer agreement, fully automated.

---

## What It Does

A potential client calls the firm's phone number. An AI agent answers, conducts a full intake interview, extracts structured case data, scores the lead, estimates settlement value, sends follow-up SMS messages, collects documents, and delivers a signed Letter of Representation — all without any human involvement until the attorney is ready to take the case.

---

## System Architecture

```
Inbound Call
    │
    ▼
Vapi.ai Voice AI (Alex — PI Intake Agent)
    │  Conducts 4–8 min intake interview
    │
    ▼
Webhook → FastAPI Backend
    │
    ├── Claude AI (Extraction)
    │     Parses transcript → structured intake data
    │     (accident type, injuries, insurance, liability, etc.)
    │
    ├── Claude AI (Lead Scoring)
    │     Scores 0–100, assigns priority: hot / warm / cold / disqualified
    │
    ├── Claude AI (Settlement Estimation)
    │     Estimates min/max settlement range
    │
    ├── PostgreSQL
    │     Stores leads, calls, documents, follow-ups, LORs
    │
    ├── Celery + Redis (Background Tasks)
    │     Schedules SMS follow-up sequences
    │
    ├── Twilio SMS
    │     Sends follow-ups, document requests, LOR signing links
    │
    ├── AWS S3
    │     Stores uploaded documents (police reports, medical records, etc.)
    │
    └── Dropbox Sign
          Generates LOR PDF, sends for e-signature
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Voice AI | Vapi.ai + ElevenLabs (Rachel voice) |
| AI Extraction / Scoring | Anthropic Claude (claude-sonnet-4-6, claude-haiku-4-5) |
| Backend | FastAPI + Python |
| Database | PostgreSQL + SQLModel + Alembic |
| Task Queue | Celery + Redis |
| SMS | Twilio |
| Document Storage | AWS S3 |
| E-Signature | Dropbox Sign |
| Containerization | Docker + Docker Compose |
| Transcription | Deepgram Nova-2 |

---

## Features Built

### 1. Voice AI Intake Agent (Vapi.ai)
- Inbound phone number connected to AI agent "Alex"
- Dynamic assistant config served via `assistant-request` webhook
- Conducts structured PI intake interview covering:
  - Accident type, date, location
  - Liability and fault determination
  - Police report and witness information
  - Injury description and severity
  - Medical treatment history and providers
  - Insurance coverage (health, at-fault, own)
  - Prior attorney history
  - Contact information
- Call recording enabled
- Deepgram Nova-2 transcription

### 2. AI Data Extraction (Claude)
- Parses raw call transcript into 30+ structured fields
- Extracts: accident type, injury severity, medical bills, insurance carriers, liability clarity, prior attorney, etc.
- Model: `claude-sonnet-4-6`

### 3. Lead Scoring Engine (Claude)
- Rule-based scoring (0–100) across 8 weighted categories:
  - Liability clarity
  - Injury severity
  - Medical treatment
  - Insurance coverage
  - Case freshness (statute of limitations)
  - Documentation
  - Prior attorney flags
  - Contact completeness
- AI enhancement layer adds nuance from transcript context
- Priority assignment: `hot` / `warm` / `cold` / `disqualified`
- Model: `claude-haiku-4-5-20251001`

### 4. Settlement Estimation (Claude)
- Estimates min/max settlement range based on:
  - Injury type and severity
  - Medical bills
  - Policy limits
  - Liability strength
  - Treatment duration
- Returns dollar range + narrative notes
- Model: `claude-haiku-4-5-20251001`

### 5. Lead Management API
- `POST /leads/` — create lead manually
- `GET /leads/` — list all leads (filterable by status/priority)
- `GET /leads/hot` — hot leads only
- `GET /leads/{id}` — full lead detail
- `PATCH /leads/{id}` — update lead
- `POST /leads/{id}/trigger-followup` — manually trigger follow-up sequence
- `POST /leads/{id}/disqualify` — disqualify with reason

### 6. SMS Follow-Up Sequences (Twilio + Celery)
- Automatic sequences triggered after call ends
- **Hot leads**: immediate + 2-hour follow-up
- **Warm leads**: 1-hour, 24-hour, 72-hour follow-up
- **Cold leads**: 24-hour, 7-day follow-up
- Document request SMS with secure upload links
- LOR signing link SMS delivery

### 7. Document Collection (AWS S3)
- `POST /documents/{lead_id}/request` — request a document, sends SMS with upload link
- `POST /documents/upload/{token}` — public upload endpoint (no auth required, token-based)
- `GET /documents/{lead_id}` — list documents with presigned download URLs
- `PATCH /documents/{id}/verify` — mark document verified
- Supported types: police report, medical records, medical bills, insurance card, accident photos, injury photos
- Files stored in S3 at `leads/{lead_id}/{doc_type}/{uuid}.{ext}`
- Upload tokens expire after 7 days
- 48-hour reminder SMS for pending uploads

### 8. Letter of Representation — LOR (Dropbox Sign)
- `POST /lors/{lead_id}/generate` — generate, send, and track LOR
- Auto-generates professional PDF with firm branding using ReportLab:
  - Scope of representation
  - Contingency fee agreement (33.33% pre-suit / 40% post-suit)
  - Client obligations
  - Medical authorization
  - Lien acknowledgment
- Uploads PDF to S3
- Sends via Dropbox Sign for e-signature
- Webhook handler for signature events: viewed → signed → declined
- SMS delivery of signing link to client
- Lead status auto-updates to `retainer_sent` → `signed`

### 9. Webhook Handlers
- `POST /webhooks/vapi` — handles all Vapi call lifecycle events:
  - `assistant-request` — returns dynamic assistant config
  - `end-of-call-report` — triggers AI extraction pipeline
  - `status-update`, `transcript`, `speech-update` — handled gracefully
- `POST /webhooks/twilio` — inbound SMS handler
- `POST /lors/webhooks/dropbox-sign` — signature status updates

---

## Data Models

### Lead
Stores all extracted intake data including: personal info, accident details, injury severity, medical treatment, insurance carriers, AI score, priority, settlement estimate, AI summary, and status lifecycle.

**Status flow:** `new` → `hot/warm/cold` → `retainer_sent` → `signed` → `disqualified`

### Call
Links to lead, stores Vapi call ID, transcript, recording URL, duration, and direction (inbound/outbound).

### Document
Tracks requested/uploaded documents with S3 keys, upload tokens, expiry, verification status.

### FollowUp
Records every SMS sent with channel, type, status, Twilio SID, and scheduled/sent timestamps.

### LOR
Tracks letter of representation lifecycle: generated → sent → viewed → signed/declined, with Dropbox Sign request ID, signing URL, and S3 PDF location.

---

## Project Structure

```
wayco-project/
├── app/
│   ├── ai/
│   │   ├── intake_extractor.py     # Claude transcript → structured data
│   │   ├── lead_scorer.py          # Scoring engine + AI enhancement
│   │   └── settlement_estimator.py # Settlement range estimation
│   ├── api/
│   │   ├── routers/
│   │   │   ├── leads.py            # Lead CRUD endpoints
│   │   │   ├── documents.py        # Document request/upload endpoints
│   │   │   ├── lors.py             # LOR generation/tracking
│   │   │   └── calls.py            # Call history endpoints
│   │   └── webhooks/
│   │       ├── vapi_webhook.py     # Vapi call event handler
│   │       └── twilio_webhook.py   # Inbound SMS handler
│   ├── models/
│   │   ├── lead.py
│   │   ├── call.py
│   │   ├── document.py
│   │   ├── follow_up.py
│   │   └── lor.py
│   ├── services/
│   │   ├── voice_agent.py          # Vapi assistant config + outbound calls
│   │   ├── sms.py                  # Twilio SMS + follow-up sequences
│   │   ├── document_service.py     # S3 upload/download, token generation
│   │   └── lor_service.py          # PDF generation + Dropbox Sign
│   ├── tasks/
│   │   ├── celery_app.py           # Celery configuration
│   │   ├── follow_up_tasks.py      # Scheduled SMS tasks
│   │   └── document_tasks.py       # Document reminder tasks
│   └── core/
│       ├── config.py               # Settings from environment
│       └── database.py             # SQLModel + PostgreSQL engine
├── alembic/                        # Database migrations
├── tests/
│   ├── test_lead_scorer.py
│   └── test_settlement_estimator.py
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env.example
```

---

## Local Setup

### Prerequisites
- Docker + Docker Compose
- ngrok (for local webhook testing)
- Accounts: Vapi.ai, Twilio, AWS, Dropbox Sign, Anthropic

### 1. Clone and configure environment

```bash
git clone <repo-url>
cd wayco-project
cp .env.example .env
# Fill in all values in .env
```

### 2. Start all services

```bash
docker compose up -d
```

This starts: FastAPI API (port 8000), Celery worker, PostgreSQL (port 5432), Redis (port 6379).

### 3. Expose webhook endpoint

```bash
ngrok http 8000
```

Set `APP_URL=https://your-ngrok-url.ngrok-free.app` in `.env`, then:

```bash
docker compose restart api
```

### 4. Configure Vapi

In the Vapi dashboard:
- Create a phone number
- Set Server URL to: `https://your-ngrok-url/webhooks/vapi`
- Leave Server URL Secret blank for development

### 5. Test the full flow

```bash
# Check API is up
curl http://localhost:8000/health

# Create a test lead manually
curl -X POST http://localhost:8000/leads/ \
  -H "Content-Type: application/json" \
  -d '{"phone": "+1XXXXXXXXXX", "first_name": "Test", "email": "test@example.com"}'

# Generate LOR for the lead
curl -X POST http://localhost:8000/lors/LEAD_ID/generate

# Request a document from the lead
curl -X POST "http://localhost:8000/documents/LEAD_ID/request?doc_type=police_report"

# Call the Vapi phone number to test the full AI intake flow
# After the call ends, check:
curl http://localhost:8000/leads/ | python3 -m json.tool
```

---

## Environment Variables

See `.env.example` for all required variables:

- `ANTHROPIC_API_KEY` — Claude AI for extraction, scoring, estimation
- `VAPI_API_KEY`, `VAPI_PHONE_NUMBER_ID` — Voice AI
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER` — SMS
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_BUCKET` — Document storage
- `DROPBOX_SIGN_API_KEY` — E-signature
- `DATABASE_URL` — PostgreSQL connection
- `REDIS_URL` — Celery broker
- `APP_URL` — Public URL for webhooks (ngrok in dev)
- `FIRM_NAME`, `FIRM_ADDRESS`, `FIRM_PHONE`, `FIRM_EMAIL`, `FIRM_BAR_NUMBER` — LOR template

---

## API Reference

Full interactive docs available at `http://localhost:8000/docs` (Swagger UI) when running locally.

---

## Key Design Decisions

- **Dynamic assistant config**: The Vapi assistant is configured at call-time via `assistant-request` webhook rather than a static pre-created assistant. This allows the server URL to always be current without dashboard changes.
- **Async intake processing**: `end-of-call-report` triggers a FastAPI background task for AI extraction so the webhook returns immediately and Vapi isn't left waiting.
- **Token-based document upload**: Clients receive a unique upload link via SMS — no login required. Tokens expire in 7 days.
- **Celery for follow-ups**: SMS sequences are scheduled as Celery tasks with `countdown` so delays (2h, 24h, 7 days) are reliable even if the API restarts.
- **LOR PDF generated server-side**: ReportLab generates the PDF in-memory, uploads to S3, then sends to Dropbox Sign — no external PDF service needed.
