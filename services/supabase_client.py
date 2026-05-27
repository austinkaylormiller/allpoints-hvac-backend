"""Thin wrapper around the supabase-py SDK.

All CRUD on the urgent_call_attempts table goes through this module.
Tests mock these functions directly rather than the SDK underneath,
which keeps the test boundary clean.

Auth uses the service-role key (bypasses RLS). The key is fetched
from config at client-init time — the client is lazily built per
call to keep the module import-side-effect free (the tests need
to import services that import this module even when SUPABASE_URL
is unset).
"""

import logging
from typing import Any, Optional

from supabase import Client, create_client

import config

logger = logging.getLogger(__name__)

_TABLE = "urgent_call_attempts"
_CLIENT_ID = "allpoints-hvac"


def _client() -> Client:
    """Build a Supabase client; raise if credentials are unset."""
    if not config.SUPABASE_URL or not config.SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must both be set"
        )
    return create_client(config.SUPABASE_URL, config.SUPABASE_SERVICE_ROLE_KEY)


def create_urgent_attempt(payload: dict) -> dict:
    """Insert a new urgent_call_attempts row and return it.

    `payload` carries the customer fields; this function fills in
    the client_id, status, and attempt_num defaults so callers
    don't have to remember them.
    """
    row = {
        "client_id": _CLIENT_ID,
        "customer_name": payload["customer_name"],
        "customer_phone": payload["customer_phone"],
        "customer_address": payload["customer_address"],
        "service_issue": payload["service_issue"],
        "status": "pending",
        "attempt_num": 0,
    }
    response = _client().table(_TABLE).insert(row).execute()
    if not response.data:
        raise RuntimeError("supabase insert returned no row")
    created = response.data[0]
    logger.info(
        "supabase: created urgent_call_attempts id=%s customer=%s",
        created["id"],
        created["customer_name"],
    )
    return created


def update_urgent_attempt(attempt_id: str, **fields: Any) -> dict:
    """Patch an urgent_call_attempts row by id and return it."""
    if not fields:
        raise ValueError("update_urgent_attempt called with no fields")
    response = (
        _client()
        .table(_TABLE)
        .update(fields)
        .eq("id", attempt_id)
        .execute()
    )
    if not response.data:
        raise RuntimeError(f"supabase update affected no row id={attempt_id}")
    return response.data[0]


def get_urgent_attempt_by_id(attempt_id: str) -> Optional[dict]:
    """Look up an urgent_call_attempts row by primary key."""
    response = (
        _client()
        .table(_TABLE)
        .select("*")
        .eq("id", attempt_id)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    return rows[0] if rows else None


def get_urgent_attempt_by_call_sid(call_sid: str) -> Optional[dict]:
    """Look up by last_call_sid (uses the index on that column)."""
    response = (
        _client()
        .table(_TABLE)
        .select("*")
        .eq("last_call_sid", call_sid)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    return rows[0] if rows else None


def append_call_attempt_log(attempt_id: str, entry: dict) -> None:
    """Append a JSON object to the call_attempts JSONB array.

    Read-modify-write: pull the existing array, append, write back.
    Race-tolerant only at the single-orchestration-per-attempt level
    (which is the invariant — only one orchestrate_urgent_call task
    runs per row). Twilio status callbacks can interleave with the
    orchestration's appends; brief races overwrite each other but
    the call_attempts log is observability, not control state.
    """
    current = get_urgent_attempt_by_id(attempt_id)
    if current is None:
        logger.warning(
            "append_call_attempt_log: attempt_id=%s not found, skipping",
            attempt_id,
        )
        return
    existing = current.get("call_attempts") or []
    if not isinstance(existing, list):
        existing = []
    existing.append(entry)
    update_urgent_attempt(attempt_id, call_attempts=existing)
