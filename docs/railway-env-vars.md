# Railway env var setup — AllPoints HVAC

Two services, each gets its own env var set in Railway dashboard →
service → Variables tab. Use "Raw Editor" mode to paste a block, or
use the regular UI to add one at a time. After saving, Railway
auto-redeploys the service within ~60s.

Source of truth: [config.py](../config.py) (what the backend reads
from `os.getenv`) and [.env.example](../.env.example) (documented
defaults). This doc is the deployment checklist.

## Where to get each value

| Var | Source | Notes |
| --- | --- | --- |
| `RESEND_API_KEY` | Pull from T&T's PROD Railway service (`t-t-hvac-backend` → Variables → `RESEND_API_KEY`) | Workspace-wide Resend sending-access key. Same value on every Booker backend. |
| `FROM_EMAIL` | Static | `Booker AI <austin@getbookerai.com>` — domain `getbookerai.com` is Resend-verified. |
| `OFFICE_EMAIL_RECIPIENTS` | **Differs PROD vs TEST** — see blocks below | Comma-separated. TEST omits `office@allpointshvac.com` on purpose; see "Why TEST recipients differ" below. |
| `CLIENT_BUSINESS_NAME` | Static | `AllPoints HVAC` — appears in 5 AllPoints HVAC email templates' footer/tagline. |
| `MANNY_BUSINESS_NAME` | Static | `Manny's Oil Company` — appears in 2 Manny's Oil email templates' footer/tagline. |
| `BOOKER_WEBHOOK_URL` | Pull from T&T's PROD Railway service (`t-t-hvac-backend` → Variables → `BOOKER_WEBHOOK_URL`) | Lovable edge function URL. Same value PROD + TEST (kill switch gates whether AllPoints actually forwards). |
| `BOOKER_WEBHOOK_SECRET` | Pull from T&T's PROD Railway service (`t-t-hvac-backend` → Variables → `BOOKER_WEBHOOK_SECRET`) | Shared secret sent in `x-webhook-secret` header. Same value PROD + TEST. |
| `POST_CALL_WEBHOOK_FORWARDING_ENABLED` | **Differs PROD vs TEST** — see blocks below | `true` on PROD, `false` on TEST. See "Kill switch" below. |
| `NIXPACKS_UV_VERSION` | Static | `0.4.30` — pins the uv version NIXPACKS uses to install deps during the build. Without this, Railway builds fail with `Invalid requirement: 'uv=='`. Required on **both** services. |

### Why TEST recipients differ

PROD sends real callback emails to the AllPoints office inbox plus
Austin. TEST exists for end-to-end smoke tests during integration —
those should never land in the customer-facing office inbox. TEST
sends to Austin only.

### Kill switch: `POST_CALL_WEBHOOK_FORWARDING_ENABLED`

`/elevenlabs_post_call` accepts the post-call webhook on both
services. PROD (`=true`) forwards the structured row + audio to the
Booker dashboard's Lovable edge function so the call appears in
Vincent's dashboard. TEST (`=false`) accepts and logs the event but
does NOT forward — test-call traffic never pollutes the production
dashboard.

### `USE_STUB_VENDOR_MESSAGE` is intentionally UNSET

`config.py` defaults this to `false` when unset. Leaving it unset
on both services keeps `/vendor_message` on the real Resend path —
the JSONL stub mode (`true`) exists only for local dev without a
Resend key. Do not add this var on Railway. If you ever see it set
to `true` on PROD, the office stops getting vendor emails — yank it.

## PROD service: `allpoints-hvac-backend`

Paste this block into Railway → service → Variables → Raw Editor.
Replace each `<paste-...>` placeholder with the value from the
"Where to get each value" table above. Don't quote values unless
the value contains shell-meaningful chars (none of these do).

```
RESEND_API_KEY=<paste-resend-api-key-from-t-t-hvac-backend-railway>
FROM_EMAIL=Booker AI <austin@getbookerai.com>
OFFICE_EMAIL_RECIPIENTS=office@allpointshvac.com,austin@getbookerai.com
CLIENT_BUSINESS_NAME=AllPoints HVAC
MANNY_BUSINESS_NAME=Manny's Oil Company
BOOKER_WEBHOOK_URL=<paste-booker-webhook-url-from-t-t-hvac-backend-railway>
BOOKER_WEBHOOK_SECRET=<paste-booker-webhook-secret-from-t-t-hvac-backend-railway>
POST_CALL_WEBHOOK_FORWARDING_ENABLED=true
NIXPACKS_UV_VERSION=0.4.30
```

## TEST service: `allpoints-hvac-backend-test`

Same shape as PROD with two values flipped (`OFFICE_EMAIL_RECIPIENTS`,
`POST_CALL_WEBHOOK_FORWARDING_ENABLED`). The 7 shared values are
copied verbatim from PROD.

```
RESEND_API_KEY=<paste-resend-api-key-from-t-t-hvac-backend-railway>
FROM_EMAIL=Booker AI <austin@getbookerai.com>
OFFICE_EMAIL_RECIPIENTS=austin@getbookerai.com
CLIENT_BUSINESS_NAME=AllPoints HVAC
MANNY_BUSINESS_NAME=Manny's Oil Company
BOOKER_WEBHOOK_URL=<paste-booker-webhook-url-from-t-t-hvac-backend-railway>
BOOKER_WEBHOOK_SECRET=<paste-booker-webhook-secret-from-t-t-hvac-backend-railway>
POST_CALL_WEBHOOK_FORWARDING_ENABLED=false
NIXPACKS_UV_VERSION=0.4.30
```

## Verification after setting vars

Do these for each service (PROD and TEST) independently.

1. **Trigger a redeploy.** Saving a variable in Railway triggers
   one automatically. If it didn't (Raw Editor sometimes batches),
   go to Deployments → ⋯ → Redeploy.
2. **Watch the build.** Should complete in ~60s. If you see
   `Invalid requirement: 'uv=='`, `NIXPACKS_UV_VERSION` is missing
   or wrong — set it to `0.4.30` and redeploy.
3. **Hit `/health`** on the custom domain (or the
   `*.up.railway.app` URL if you haven't added the custom domain
   yet):
   - PROD: `curl https://allpoints-api.getbookerai.com/health`
   - TEST: `curl https://allpoints-api-test.getbookerai.com/health`
   Expect: `{"status":"ok"}`. TEST may take 2–5s on first hit if
   it was sleeping (Serverless mode is ON on TEST).
4. **Check Deploy logs** for the most recent deployment. Look for
   the uvicorn startup line:
   `Uvicorn running on http://0.0.0.0:$PORT`. No `RESEND_API_KEY
   is not set` or `OFFICE_EMAIL_RECIPIENTS is not set` should
   appear at boot (those raise only on request, not import, but
   any obvious env-loading errors surface here).
5. **End-to-end TEST verification** (after both services are up and
   the agent is wired) — see the curl checklist in the session
   handoff. Run only against TEST. PROD gets validated by real
   call traffic.

## Forward reference: vars not yet added

The following env vars are out of scope for this session and must
not be added to either Railway service until the next build
session. They support `/urgent_call` (Twilio + Supabase + asyncio
orchestration), which does not exist yet:

- `TWILIO_*` — Twilio account SID, auth token, from-number
- `URGENT_CALL_*` — dispatch routing config
- `SUPABASE_*` — Supabase URL + service-role key

Adding them prematurely is harmless (they just sit unused), but
leaving them out keeps the env panel clean and makes the next
session's diff easy to read.
