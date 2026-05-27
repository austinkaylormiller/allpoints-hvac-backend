# allpoints-hvac-backend

FastAPI webhook backend for the AllPoints HVAC ElevenLabs voice
agent. Hosts callback endpoints for two businesses that share the
agent: **AllPoints HVAC** (HVAC service) and **Manny's Oil
Company** (heating-oil delivery).

See [CLAUDE.md](CLAUDE.md) for architecture, deploy, and the full
endpoint contract.

## Quick start

```
uv sync
uv run pytest -q
uv run uvicorn api.main:app --reload
```

Copy `.env.example` to `.env` and fill in `RESEND_API_KEY` (or
leave it blank and set `USE_STUB_VENDOR_MESSAGE=true` to exercise
`/vendor_message` against the JSONL stub).

## Endpoints

| Method | Path |
| --- | --- |
| GET  | `/health` |
| POST | `/vendor_message` |
| POST | `/scheduling_email` |
| POST | `/reschedule_email` |
| POST | `/cancel_email` |
| POST | `/general_inquiries_email` |
| POST | `/recent_service_email` |
| POST | `/manny_oil_delivery_request` |
| POST | `/manny_oil_general_inquiries` |
| POST | `/elevenlabs_post_call` |
