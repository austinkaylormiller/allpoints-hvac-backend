# AllPoints HVAC — FastAPI Backend

## Client
AllPoints HVAC. HVAC service business in Worcester, MA. Shares the
ElevenLabs voice agent (Jason, agent_4301kd412wrefv7a9t8hc402fra3)
with Manny's Oil Company — one agent triages between the two
businesses and routes to different webhook endpoints depending on
caller intent.

Matching agent repo: `../allpoints-hvac-agent`. See that repo's
CLAUDE.md for agent-side context.

Two-business note: AllPoints HVAC and Manny's Oil Company are
routed to different endpoints by the agent's triage. The FastAPI
backend treats them as distinct endpoints with distinct email
templates and brand identities. Today they share one inbox
(office@allpointshvac.com on PROD); this can split in the future
by changing OFFICE_EMAIL_RECIPIENTS without touching code.

## Stack
- Python 3.12
- FastAPI + uvicorn
- uv for dependency management
- Pydantic v2 for schema validation
- Railway for hosting (push to main, auto-deploys)

## Deploy
Two Railway services in the `allpoints-hvac` Railway project watch
this repo's `main` branch:

- PROD: `allpoints-hvac-backend`
  - Custom domain: `https://allpoints-api.getbookerai.com`
  - Serverless mode: OFF (always-on)
- TEST: `allpoints-hvac-backend-test`
  - Custom domain: `https://allpoints-api-test.getbookerai.com`
  - Serverless mode: ON (sleeps after 10 min; first request after
    sleep takes 2–5s)

Both services run the same code. They differ only in env vars
(PROD has real recipient list + forwarding enabled; TEST sends to
Austin only with forwarding disabled).

To deploy: `git push origin main`. Railway picks up the push and
redeploys both services within ~60s.

Build configuration: Railway uses NIXPACKS. Pin
`NIXPACKS_UV_VERSION=0.4.30` on both services. Without this,
NIXPACKS builds fail with "Invalid requirement: 'uv=='".

Start command (railway.toml): `uv run uvicorn api.main:app
--host 0.0.0.0 --port $PORT`.

## Endpoints

All POST endpoints return:
- 200 with `{"status": "ok", "message": str}` on success
- 422 with Pydantic detail on validation failure
- 500 with `{"status": "error", "message": "Sorry, our message
  system is having an issue. Please call back later or email us
  directly."}` on a downstream failure (Resend, etc.) — the agent
  speaks `message` back to the caller.

Optional fields on every email endpoint:
- `email` — caller email; renders in the template only when present.
- `callTimestamp` — ISO 8601 string from ElevenLabs's
  `{{system__time_utc}}`. Accepted and validated at the API
  boundary; the api/ layer fills in `datetime.utcnow()` when the
  agent omits it. **Not rendered in the email body** — the
  template intentionally drops the received-at line. The field is
  retained on the schema so the agent tool config can keep sending
  it without a breaking change if we ever want to start displaying
  it again.

All `phone` fields go through `services.utils.normalize_phone()` at
the request boundary — spoken-word digits, hyphens, parens, and
leading +1 are all reduced to digits only, with a minimum-7-digit
guard at the Pydantic layer.

### AllPoints HVAC endpoints

- `POST /scheduling_email`
  Required: customerName, phone, address, serviceIssue, preferredTimes.
  Subject: "New Appointment Request - {customerName}".
- `POST /reschedule_email`
  Required: customerName, phone, originalAppointment, preferredTimes.
  Subject: "Appointment Reschedule Request - {customerName}".
- `POST /cancel_email`
  Required: customerName, phone, appointmentToCancel.
  Subject: "Appointment Cancellation Request - {customerName}".
- `POST /general_inquiries_email`
  Required: customerName, phone, inquiry (lowercase), preferredTimes.
  Subject: "Callback Request - {customerName}".
- `POST /recent_service_email`
  Required: customerName, phone, inquiry (lowercase), preferredTimes.
  Subject: "Recent Service Follow-up - {customerName}".

### Manny's Oil Company endpoints

- `POST /manny_oil_delivery_request`
  Required: customerName, phone, address, preferredTimes.
  Subject: "Delivery Request, Manny's Oil - {customerName}".
- `POST /manny_oil_general_inquiries`
  Required: customerName, phone, inquiry (lowercase), preferredTimes.
  Subject: "Callback Request, Manny's Oil - {customerName}".

The Manny's Oil emails use the same Booker brand template but pass
`Manny's Oil Company` as `client_business_name` — the tagline and
footer ("Booker answered a call for Manny's Oil Company") read
`Manny's Oil Company` rather than `AllPoints HVAC`. The office can
tell at a glance which business a callback is for. Both Manny's
subjects follow the `[Action], Manny's Oil - [Name]` pattern so
inbox previews line up visually.

### Vendor message

- `POST /vendor_message`
  Mirror of T&T HVAC. Required: name, company, phone, reason.
  Subject: "Vendor Message - {company}".
  Has a JSONL stub mode toggled by `USE_STUB_VENDOR_MESSAGE=true`
  for local dev without hitting Resend.

### Post-call webhook

- `POST /elevenlabs_post_call`
  Receives ElevenLabs's post-call webhook (transcript + audio events)
  and forwards each event to the Booker dashboard's Lovable edge
  function. Replaces the Make.com dashboard scenario. Copied
  verbatim from T&T HVAC's `services/elevenlabs_webhook.py`
  (CLIENT_NAME changed to "AllPoints HVAC").

  Two event types are handled:
  - `post_call_transcription` — joins the transcript, pulls call
    metadata and data-collection fields, forwards a structured row.
    Calls of 20s or less are dropped as noise.
  - `post_call_audio` — forwards the call recording (base64). Only
    the audio length is logged, never the content.

  Always returns HTTP 200, even on downstream failure — ElevenLabs
  must never see an error and retry. Failures are logged.

  Forwarding is gated by `POST_CALL_WEBHOOK_FORWARDING_ENABLED`:
  - PROD (`=true`) forwards to the Booker dashboard.
  - TEST (`=false`) accepts and logs the webhook but does NOT
    forward — keeps test calls out of the production dashboard.

  Auth to the Lovable function is a shared secret in the
  `x-webhook-secret` header (no HMAC) — the scheme the unchanged
  Lovable function already validates. The Booker dashboard
  attributes each call to AllPoints HVAC via the ElevenLabs
  `agent_id` (`agent_4301kd412wrefv7a9t8hc402fra3`); the matching
  organization row must exist in Supabase before forwarding is
  enabled on PROD.

### Urgent call orchestration

Four routes power the urgent-dispatch flow. The agent hits
`/urgent_call`; the other three are Twilio webhook callbacks.

- `POST /urgent_call`
  Called by the agent's Urgent dispatch node. Required:
  customerName, phone, address, serviceIssue. Optional: email,
  callTimestamp. Sends the initial urgent email, creates an
  `urgent_call_attempts` row in Supabase (status="pending"),
  spawns the Twilio retry loop as a background asyncio task, and
  returns 200 immediately. Response:
  `{"status":"ok","message":"Urgent dispatch initiated. The owner
  will be contacted immediately.","attempt_id":"<uuid>"}`.

- `GET /urgent_call_twiml?attempt_id=...`
  Twilio fetches this URL when placing each call. Returns TwiML
  XML that plays the urgent message (Polly.Joanna-Neural) and
  Gathers one DTMF digit (timeout=15s). The Gather action URL
  carries `attempt_id` through as a query param.

- `POST /urgent_call_pressed?attempt_id=...`
  Twilio Gather action URL. Twilio POSTs form-encoded data with
  `Digits` and `CallSid` fields. If `Digits` is non-empty, the
  attempt row flips to status="confirmed", a confirmation email
  fires, and TwiML thanks the recipient. If empty (Gather
  timeout), no status change — the orchestration loop owns the
  retry decision.

- `POST /urgent_call_status?attempt_id=...`
  Twilio call-lifecycle callback (initiated/ringing/answered/
  completed). Appends a JSONB entry to `call_attempts` for
  observability. Returns 204. Does NOT drive control flow.

#### Retry loop

`services/urgent_call.orchestrate_urgent_call(attempt_id)` runs
detached on the event loop via `asyncio.create_task`. Per attempt
(up to 3):

1. Update row status="calling", attempt_num=N.
2. Place the Twilio call via `services/twilio_client`.
3. Append a "placed" log entry to `call_attempts`.
4. Sleep `ATTEMPT_TIMEOUT_SECONDS` (90s PROD, 10s with FAST_MODE).
5. Race-grace poll: 3× at 1s intervals, look for status=
   "confirmed" arriving just after sleep.
6. If confirmed → return. If not and attempts remain → sleep
   `BETWEEN_ATTEMPTS_SECONDS` (30s PROD, 3s with FAST_MODE) and
   loop.

After 3 failed attempts: row flips to status="never_confirmed"
and the failure email fires.

Twilio SDK failures during call placement are logged with a
`twilio_error` entry in `call_attempts` and the loop retries on
the next iteration rather than crashing the task.

Background-task safety: `orchestrate_urgent_call` wraps its body
in try/except so uncaught exceptions show up in logs instead of
disappearing into the event loop.

#### FAST_MODE

`URGENT_CALL_FAST_MODE=true` (TEST-only) compresses the timings
to 10s/3s so a full 3-attempt timeout flow finishes in ~30s
instead of 5.5 minutes. PROD leaves the var unset
(defaults to false).

### Health

- `GET /health` → `{"status": "ok"}` (200). Used by Railway's
  health check and for manual deploy verification.

## Active integrations

- Resend (`RESEND_API_KEY`) — transactional email. All 7 branded
  email endpoints plus `/vendor_message` send via Resend to
  `OFFICE_EMAIL_RECIPIENTS`. Sender: `Booker AI
  <austin@getbookerai.com>` (verified domain getbookerai.com).
  The three urgent_call emails (initial, confirmation, never-
  confirmed) also send via Resend to the same recipient list.
- Booker dashboard webhook (`BOOKER_WEBHOOK_URL`,
  `BOOKER_WEBHOOK_SECRET`) — `/elevenlabs_post_call` forwards
  post-call events to the Lovable edge function that ingests them
  into the Booker dashboard.
- Twilio (`TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`,
  `TWILIO_FROM_NUMBER`) — places the urgent retry calls.
  `URGENT_CALL_RECIPIENT_PHONE` is the number that rings (PROD:
  Manny's cell, TEST: Austin's cell). Twilio reaches the backend
  via the public custom domain configured in `PUBLIC_BASE_URL`.
- Supabase (`SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`) —
  `urgent_call_attempts` table tracks each dispatch through its
  retry-loop lifecycle. Service-role key bypasses RLS.

Credentials live in the Railway dashboard, not the repo. `.env`
is gitignored.

## Environment variables

See `.env.example` for the full list. Values live in Railway per
service:

| Var | PROD | TEST |
| --- | --- | --- |
| `RESEND_API_KEY` | Resend sending-access key | same as PROD |
| `FROM_EMAIL` | `Booker AI <austin@getbookerai.com>` | same |
| `OFFICE_EMAIL_RECIPIENTS` | `office@allpointshvac.com,austin@getbookerai.com` | `austin@getbookerai.com` |
| `CLIENT_BUSINESS_NAME` | `AllPoints HVAC` | same |
| `MANNY_BUSINESS_NAME` | `Manny's Oil Company` | same |
| `BOOKER_WEBHOOK_URL` | Lovable edge function URL (same value PROD+TEST) | same |
| `BOOKER_WEBHOOK_SECRET` | shared secret (same value PROD+TEST) | same |
| `POST_CALL_WEBHOOK_FORWARDING_ENABLED` | `true` | `false` |
| `NIXPACKS_UV_VERSION` | `0.4.30` | `0.4.30` |
| `USE_STUB_VENDOR_MESSAGE` | unset (defaults `false`) | unset |
| `TWILIO_ACCOUNT_SID` | shared Twilio account SID | same |
| `TWILIO_AUTH_TOKEN` | shared Twilio auth token | same |
| `TWILIO_FROM_NUMBER` | `+15084655351` | same |
| `SUPABASE_URL` | `https://snmzbjmddgukamuknbxr.supabase.co` | same |
| `SUPABASE_SERVICE_ROLE_KEY` | service-role key | same |
| `URGENT_CALL_RECIPIENT_PHONE` | `+15087699785` (Manny) | `+12065364398` (Austin) |
| `URGENT_CALL_FAST_MODE` | unset / `false` | `true` (optional, for fast integration tests) |
| `PUBLIC_BASE_URL` | `https://allpoints-api.getbookerai.com` | `https://allpoints-api-test.getbookerai.com` |

TEST recipient isolation: `OFFICE_EMAIL_RECIPIENTS` on TEST is
`austin@getbookerai.com` only — test calls never land in
`office@allpointshvac.com`. Confirm this list before flipping the
agent's tool URLs to TEST during integration sessions.

## File layout

```
allpoints-hvac-backend/
├── api/
│   └── main.py            # FastAPI app, route definitions, request logging
├── services/
│   ├── email_send.py      # branded-email handlers (AllPoints + Manny's + 3 urgent)
│   ├── email_templates.py # HTML + plain-text builders, Booker brand spec
│   ├── elevenlabs_webhook.py  # post-call forwarder with kill switch
│   ├── supabase_client.py # urgent_call_attempts CRUD
│   ├── twilio_client.py   # urgent-call placement + TwiML generation
│   ├── urgent_call.py     # 3-attempt retry orchestration
│   ├── utils.py           # normalize_phone
│   └── vendor_message.py  # vendor message (Resend + stub mode)
├── models/
│   └── schemas.py         # Pydantic request/response models
├── data/                  # stub storage (gitignored)
├── tests/
│   ├── test_endpoints.py
│   └── test_urgent_call.py
├── config.py              # env loading
├── .env.example
├── .gitignore
├── pyproject.toml
├── railway.toml
└── CLAUDE.md
```

Keep `services/` free of FastAPI imports — service logic must be
callable from anywhere, not coupled to HTTP. The `api/` layer is
the thin HTTP wrapper. Portability hedge if Railway/FastAPI ever
get swapped.

## Email branding

Each endpoint uses a distinct accent color on the header card's
left border so the office can scan inbox previews at a glance:

| Endpoint | Accent | Hex |
| --- | --- | --- |
| `/scheduling_email` | orange clay | `#c66140` |
| `/reschedule_email` | amber gold | `#b8842a` |
| `/cancel_email` | earthy red | `#9c4a3f` |
| `/general_inquiries_email` | blue-gray | `#5a7f8b` |
| `/recent_service_email` | blue-gray | `#5a7f8b` |
| `/manny_oil_delivery_request` | orange clay | `#c66140` |
| `/manny_oil_general_inquiries` | blue-gray | `#5a7f8b` |
| `/vendor_message` | orange clay | `#c66140` |

Booker brand pattern: subtle border accent, plain-text headers
(no emoji), business name in the tagline and footer. Manny's Oil
emails substitute `Manny's Oil Company` for the business name.

## Schema rules

- camelCase field names match the agent's webhook tool config.
- `inquiry` is **lowercase** on `/general_inquiries_email`,
  `/recent_service_email`, and `/manny_oil_general_inquiries`. The
  ElevenLabs agent tools currently send capital `Inquiry`; the
  agent tool config will be updated at Phase 10 migration time.
  Until then a capital-I payload returns 422 — which is the
  intended fail-fast behavior.
- `email` and `callTimestamp` are optional everywhere. `email`
  renders in the template only when present; `callTimestamp`
  defaults to server UTC at the request boundary.
- `phone` is normalized via `normalize_phone()` and Pydantic
  enforces a 7-digit minimum.

## Stub vs. real integration

`/vendor_message` has a JSONL stub behind `USE_STUB_VENDOR_MESSAGE`
(true → writes to `data/messages.jsonl`; false → calls Resend).
The 7 branded-email endpoints do not currently have a stub mode —
during local dev, they return 500 with the standard error message
because `RESEND_API_KEY` is unset. If you need to exercise them
locally without Resend, mock `services.email_send.resend.Emails.send`
in tests (see `tests/test_endpoints.py`).

## Local testing

```
uv sync
uv run pytest -q
uv run uvicorn api.main:app --reload
curl http://localhost:8000/health
curl -X POST http://localhost:8000/vendor_message \
  -H 'Content-Type: application/json' \
  -d '{"name":"Test","company":"ACME","phone":"555-1234","reason":"hi"}'
```

(`/vendor_message` runs against the stub if you set
`USE_STUB_VENDOR_MESSAGE=true` in `.env`; output appears in
`data/messages.jsonl`.)

## Logging

Every request/response pair is logged via the FastAPI middleware:

```
[endpoint] req={...}
[endpoint] resp_status=200 resp={...} dur=42ms
```

Audio webhooks are size-capped before logging (the full base64
recording is multiple MB — only its length is logged).

## Quirks and decisions

- The `/elevenlabs_post_call` URL deliberately differs from T&T
  HVAC's `/elevenlabs_webhook` — the AllPoints agent's tool config
  uses the more-descriptive name. The handler module is
  `services/elevenlabs_webhook.py` (verbatim from T&T except
  `CLIENT_NAME`).
- `inquiry` casing mismatch with current agent tools is intentional
  and resolves at Phase 10 migration. Don't add an alias.
- Two-business architecture: keeping the brand split inside the
  same backend (rather than a second deployment) keeps Railway
  cost flat and makes shared concerns — the post-call webhook,
  vendor message endpoint, brand template module — single-source
  of truth.

## Forward references

- End-to-end manual integration testing for `/urgent_call`
  happens in the next session, after Twilio/Supabase env vars are
  configured on Railway. The next session uses TEST with FAST_MODE
  on, rings Austin's cell, walks through happy path + never-
  confirmed paths, then verifies the Supabase rows.
- Phase 10 migration of the ElevenLabs agent tool URLs from
  Make.com to this backend is a separate branch-based change.
  This session does not touch the agent.
