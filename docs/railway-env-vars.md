# Railway env var setup — AllPoints HVAC

Two services, each gets its own env var set in Railway dashboard →
service → Variables tab. Use "Raw Editor" mode to paste a block, or
use the regular UI to add one at a time. After saving, Railway
auto-redeploys the service within ~60s.

Source of truth: [config.py](../config.py) (what the backend reads
from `os.getenv`) and [.env.example](../.env.example) (documented
defaults). This doc is the deployment checklist.

> **This update** (`feature/urgent-call` branch): adds the
> `TWILIO_*`, `SUPABASE_*`, `URGENT_CALL_*`, and `PUBLIC_BASE_URL`
> variables that power `/urgent_call`. The original 9 variables
> from the first deploy are already set on both Railway services —
> the per-service "what to paste" blocks below cover **only the new
> vars** to keep the existing config untouched.

## Where to get each value

| Var | Shared? | Source | Notes |
| --- | --- | --- | --- |
| `RESEND_API_KEY` | shared | Pull from T&T's PROD Railway service | already set; workspace-wide Resend sending key |
| `FROM_EMAIL` | shared | static | `Booker AI <austin@getbookerai.com>` — already set |
| `OFFICE_EMAIL_RECIPIENTS` | **differs** | static | PROD: `office@allpointshvac.com,austin@getbookerai.com`. TEST: `austin@getbookerai.com`. Already set. |
| `CLIENT_BUSINESS_NAME` | shared | static | `AllPoints HVAC` — already set |
| `MANNY_BUSINESS_NAME` | shared | static | `Manny's Oil Company` — already set |
| `BOOKER_WEBHOOK_URL` | shared | Pull from T&T's PROD Railway service | already set; Lovable edge function URL |
| `BOOKER_WEBHOOK_SECRET` | shared | Pull from T&T's PROD Railway service | already set; shared secret for `x-webhook-secret` |
| `POST_CALL_WEBHOOK_FORWARDING_ENABLED` | **differs** | static | PROD `true`, TEST `false` — already set |
| `NIXPACKS_UV_VERSION` | shared | static | `0.4.30` — already set; required for the NIXPACKS build |
| `USE_STUB_VENDOR_MESSAGE` | unset on both | n/a | leave unset; defaults to `false` |
| **NEW** `TWILIO_ACCOUNT_SID` | shared | Twilio dashboard → Account → API keys & tokens | starts `AC...`; same Twilio account on PROD and TEST |
| **NEW** `TWILIO_AUTH_TOKEN` | shared | Twilio dashboard → Account → API keys & tokens | same Twilio account; rotate together with SID if rotating at all |
| **NEW** `TWILIO_FROM_NUMBER` | shared | static | `+15084655351` on **both** services — the AllPoints Twilio number already used for the Make.com urgent flow |
| **NEW** `SUPABASE_URL` | shared | static | `https://snmzbjmddgukamuknbxr.supabase.co` — the Booker dashboard's shared Supabase project |
| **NEW** `SUPABASE_SERVICE_ROLE_KEY` | shared | Supabase dashboard → Project Settings → API → `service_role` secret | bypasses RLS; never expose this client-side |
| **NEW** `URGENT_CALL_RECIPIENT_PHONE` | **differs — CRITICAL** | static | **PROD: `+15087699785` (Manny's cell). TEST: `+12065364398` (Austin's cell).** A swap here means TEST rings Manny in the middle of integration testing — double-check before saving. |
| **NEW** `PUBLIC_BASE_URL` | **differs — CRITICAL** | static | PROD: `https://allpoints-api.getbookerai.com`. TEST: `https://allpoints-api-test.getbookerai.com`. **Must match the service's own custom domain** — Twilio fetches TwiML and posts Gather/status callbacks against this URL. If TEST is set to PROD's domain, Twilio calls PROD back with an `attempt_id` PROD never created, and the orchestration breaks silently. |

### Why TEST recipients differ

PROD sends real callback emails to the AllPoints office inbox plus
Austin. TEST exists for end-to-end smoke tests during integration —
those should never land in the customer-facing office inbox. TEST
sends to Austin only. Same logic applies to the three urgent
emails (initial, confirmation, never-confirmed): they all use
`OFFICE_EMAIL_RECIPIENTS`, so TEST urgent emails go to Austin only.

### Kill switch: `POST_CALL_WEBHOOK_FORWARDING_ENABLED`

`/elevenlabs_post_call` accepts the post-call webhook on both
services. PROD (`=true`) forwards events to the Booker dashboard's
Lovable edge function. TEST (`=false`) accepts and logs the event
but does NOT forward — keeps test-call traffic out of the
production dashboard. Already set; no action needed.

### `URGENT_CALL_RECIPIENT_PHONE` is the safety-critical one

PROD = Manny's cell. TEST = Austin's cell. If you accidentally set
TEST to Manny's number, every integration test ringing through the
3-attempt loop wakes Manny up. Eyeball this twice before saving
the TEST block.

### Timing is the same on PROD and TEST (90s + 30s)

There is no `URGENT_CALL_FAST_MODE` override. Both services run
the production 90s-per-attempt + 30s-between-attempts timings so
TEST integration runs validate the actual recipient experience.
A full 3-attempt failure path takes ~5.5 minutes — that is the
test bar.

### `PUBLIC_BASE_URL` must match the service's own custom domain

Twilio fetches `/urgent_call_twiml` and posts to
`/urgent_call_pressed` and `/urgent_call_status` at the base URL
the orchestration constructs. If TEST's `PUBLIC_BASE_URL` points at
PROD (or vice versa), Twilio's callback hits a service that has no
Supabase row for the `attempt_id` and the orchestration loop on
the originating service silently times out without a digit press
ever registering. Verify the URL per service after saving.

## PROD service: `allpoints-hvac-backend` — new vars to add

Paste this block into Railway → `allpoints-hvac-backend` →
Variables → Raw Editor. **Adds 7 new vars** on top of the existing
9; do not remove or re-paste the existing block.

```
TWILIO_ACCOUNT_SID=<paste-twilio-account-sid>
TWILIO_AUTH_TOKEN=<paste-twilio-auth-token>
TWILIO_FROM_NUMBER=+15084655351
SUPABASE_URL=https://snmzbjmddgukamuknbxr.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<paste-supabase-service-role-key>
URGENT_CALL_RECIPIENT_PHONE=+15087699785
PUBLIC_BASE_URL=https://allpoints-api.getbookerai.com
```

## TEST service: `allpoints-hvac-backend-test` — new vars to add

Paste this block into Railway → `allpoints-hvac-backend-test` →
Variables → Raw Editor. **Adds 7 new vars** on top of the existing
9. Two of the values differ from PROD on this block:
`URGENT_CALL_RECIPIENT_PHONE` and `PUBLIC_BASE_URL`.

```
TWILIO_ACCOUNT_SID=<paste-twilio-account-sid>
TWILIO_AUTH_TOKEN=<paste-twilio-auth-token>
TWILIO_FROM_NUMBER=+15084655351
SUPABASE_URL=https://snmzbjmddgukamuknbxr.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<paste-supabase-service-role-key>
URGENT_CALL_RECIPIENT_PHONE=+12065364398
PUBLIC_BASE_URL=https://allpoints-api-test.getbookerai.com
```

> **Removing the earlier `URGENT_CALL_FAST_MODE=true`:** if the TEST
> service has this var from the prior deploy attempt, delete it in
> the Railway dashboard before re-running the integration tests.
> The codebase no longer reads it.

## Verification after setting vars

Do these for each service (PROD and TEST) independently.

1. **Trigger a redeploy.** Saving in the Raw Editor usually
   triggers one. If not: Deployments → ⋯ → Redeploy.
2. **Watch the build.** Should complete in ~60s. Twilio and
   Supabase pull in a few extra deps; the build is slightly
   slower than before but still well under a minute.
3. **Hit `/health`:**
   - PROD: `curl https://allpoints-api.getbookerai.com/health`
   - TEST: `curl https://allpoints-api-test.getbookerai.com/health`
   Expect: `{"status":"ok"}`.
4. **Hit `/urgent_call_twiml?attempt_id=smoke-001` on each
   service** and verify it returns valid TwiML. This confirms the
   route is mounted on the new build:

   ```
   curl 'https://allpoints-api.getbookerai.com/urgent_call_twiml?attempt_id=smoke-001'
   curl 'https://allpoints-api-test.getbookerai.com/urgent_call_twiml?attempt_id=smoke-001'
   ```

   Expect XML containing the `<Gather>` block with `numDigits="1"`
   and an `action=` URL that starts with the service's own
   `PUBLIC_BASE_URL`. **The action URL is the canary** — if PROD's
   TwiML shows a TEST action URL or vice versa, `PUBLIC_BASE_URL`
   is wrong.
5. **PROD reachability stops there.** Do not POST `/urgent_call`
   against PROD — that would dial Manny. PROD is validated by
   real urgent-call traffic later.
6. **Run the TEST integration sequence below.**

## Integration test sequence (urgent_call)

After env vars are set on TEST and the TEST service is redeployed,
run these 3 scenarios against the TEST custom domain. Timings
match production — Scenario A takes ~90 seconds, Scenario B takes
~3 minutes, Scenario C takes ~5.5 minutes (real 3-attempt fail
flow). Slow on purpose: TEST validates the actual recipient
experience. **Austin's cell (`+12065364398`) is the one that
rings — keep it nearby and budget the time.**

Common setup:

```
BASE=https://allpoints-api-test.getbookerai.com
```

### Scenario A — Confirm on attempt 1

```
curl -sS -X POST "$BASE/urgent_call" \
  -H 'Content-Type: application/json' \
  -d '{
    "customerName": "Urgent Test A — Anya Sokolov",
    "phone": "508-555-0147",
    "address": "12 Maple St, Worcester, MA",
    "serviceIssue": "No heat, furnace not igniting — emergency"
  }'
```

Expect:
- 200 immediately with `attempt_id` in the response body.
- Initial `URGENT - Urgent Test A — Anya Sokolov` email at
  `austin@getbookerai.com` within seconds.
- Austin's cell rings within ~10s (Twilio dial time). Scenario A
  resolves on this first call.
- **Pick up. Press any digit.** Twilio plays "Thank you,
  confirmation received." then hangs up.
- `Urgent Confirmed - Urgent Test A — Anya Sokolov` email lands.
- Supabase: `urgent_call_attempts` row for this `attempt_id` shows
  `status='confirmed'`, `digits_pressed='<the digit you pressed>'`,
  `confirmed_at` filled in. `attempt_num` is 1.
- Scenario wall-clock: ~90 seconds (the orchestration sleeps the
  full 90s grace window before checking status, even though you
  confirmed early; the race-grace poll exits as soon as it sees
  `status='confirmed'`).

### Scenario B — Confirm on attempt 3

```
curl -sS -X POST "$BASE/urgent_call" \
  -H 'Content-Type: application/json' \
  -d '{
    "customerName": "Urgent Test B — Bartek Nowak",
    "phone": "508-555-0322",
    "address": "45 Oak Ave, Worcester, MA",
    "serviceIssue": "AC failure during heat advisory — emergency"
  }'
```

Expect:
- 200 immediately + initial email.
- Cell rings (~10s) — **decline or ignore call 1**.
- After ~2 minutes (90s attempt timeout + 30s between attempts),
  cell rings again — **decline or ignore call 2**.
- After another ~2 minutes, cell rings for the third time —
  **pick up, press a digit**.
- `Urgent Confirmed` email lands.
- Supabase row: `status='confirmed'`, `attempt_num=3`. The
  `call_attempts` JSONB array has 3 `placed` entries (one per
  Twilio dial) plus a `confirmed` entry, plus lifecycle entries
  from `/urgent_call_status`.
- Scenario wall-clock: ~3 minutes total.

### Scenario C — Never confirm

```
curl -sS -X POST "$BASE/urgent_call" \
  -H 'Content-Type: application/json' \
  -d '{
    "customerName": "Urgent Test C — Cyryl Wisniewski",
    "phone": "508-555-0438",
    "address": "78 Birch Ln, Worcester, MA",
    "serviceIssue": "Carbon monoxide alarm — emergency"
  }'
```

Expect:
- 200 immediately + initial email.
- 3 calls to Austin's cell across ~5 minutes — **ignore all three**.
- After ~5.5 minutes total (3 × 90s attempt timeout + 2 × 30s
  between attempts + race-grace polls), `URGENT - All Phone
  Attempts Failed - Urgent Test C — Cyryl Wisniewski` email
  lands.
- Supabase row: `status='never_confirmed'`, `attempt_num=3`.
- Scenario wall-clock: ~5.5 minutes total. This is the production
  worst-case flow and the real test of "did the recipient
  experience match what we promised the client."

### Cleanup tips

After the three scenarios, the TEST Supabase table has 3 rows
that can be left in place (the dashboard query filters by
`client_id`/`created_at` and the rows are harmless). If you want
to clear them:

```sql
DELETE FROM urgent_call_attempts
WHERE client_id = 'allpoints-hvac'
  AND customer_name LIKE 'Urgent Test %';
```

## Forward reference: complete env var inventory

Both Railway services should have these vars set after this update.
"Already set" = configured during the initial deploy. "New" = set
in this session as part of `feature/urgent-call`.

| Var | PROD | TEST | Status |
| --- | --- | --- | --- |
| `RESEND_API_KEY` | Resend sending key | same | already set |
| `FROM_EMAIL` | `Booker AI <austin@getbookerai.com>` | same | already set |
| `OFFICE_EMAIL_RECIPIENTS` | `office@allpointshvac.com,austin@getbookerai.com` | `austin@getbookerai.com` | already set |
| `CLIENT_BUSINESS_NAME` | `AllPoints HVAC` | same | already set |
| `MANNY_BUSINESS_NAME` | `Manny's Oil Company` | same | already set |
| `BOOKER_WEBHOOK_URL` | Lovable edge function URL | same | already set |
| `BOOKER_WEBHOOK_SECRET` | shared secret | same | already set |
| `POST_CALL_WEBHOOK_FORWARDING_ENABLED` | `true` | `false` | already set |
| `NIXPACKS_UV_VERSION` | `0.4.30` | same | already set |
| `TWILIO_ACCOUNT_SID` | Twilio SID | same | **new** |
| `TWILIO_AUTH_TOKEN` | Twilio auth token | same | **new** |
| `TWILIO_FROM_NUMBER` | `+15084655351` | same | **new** |
| `SUPABASE_URL` | `https://snmzbjmddgukamuknbxr.supabase.co` | same | **new** |
| `SUPABASE_SERVICE_ROLE_KEY` | service-role secret | same | **new** |
| `URGENT_CALL_RECIPIENT_PHONE` | `+15087699785` (Manny) | `+12065364398` (Austin) | **new** |
| `PUBLIC_BASE_URL` | `https://allpoints-api.getbookerai.com` | `https://allpoints-api-test.getbookerai.com` | **new** |
| `USE_STUB_VENDOR_MESSAGE` | (unset) | (unset) | intentionally unset |
