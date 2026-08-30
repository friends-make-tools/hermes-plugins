"""OpenRouter balance & 30-day spend backend.

Mounted at /api/plugins/openrouter-balance/ by the Hermes dashboard web
server (see hermes_cli/web_server.py::_mount_plugin_api_routes). The
manifest (dashboard/manifest.json) declares ``"api": "plugin_api.py"`` and
this module must expose a module-level ``router`` (FastAPI APIRouter).

Secret handling (spec N1): the management key is read from
$HERMES_HOME/.env only, held only in local variables, and never logged,
cached, or returned. All failure responses carry error text and status
codes only.

Python 3.11 stdlib only (spec N5). ``fastapi`` imports are optional so the
module can be unit-tested without the dashboard stack.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

try:  # Real Hermes home when running inside Hermes; env/profile fallback otherwise.
    from hermes_constants import get_hermes_home
except ImportError:  # pragma: no cover - exercised only outside Hermes
    def get_hermes_home() -> Path:  # type: ignore[misc]
        val = (os.environ.get("HERMES_HOME") or "").strip()
        return Path(val) if val else Path.home() / ".hermes"

try:
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse
except Exception:  # Allows local unit tests without dashboard dependencies.

    class APIRouter:  # type: ignore[no-redef]
        def get(self, *_args, **_kwargs):
            return lambda fn: fn

    class JSONResponse(dict):  # type: ignore[no-redef]
        def __init__(self, status_code: int = 200, content: Any = None, **_kw):
            super().__init__(content if isinstance(content, dict) else {})
            self.status_code = status_code


router = APIRouter()

OPENROUTER_CREDITS_URL = "https://openrouter.ai/api/v1/credits"
OPENROUTER_ACTIVITY_URL = "https://openrouter.ai/api/v1/activity"
REQUEST_TIMEOUT_SECONDS = 15.0
WINDOW_DAYS = 30
CACHE_TTL_SECONDS = 60.0
MAX_ERROR_CHARS = 300

ENV_KEY_NAME = "OPENROUTER_MANAGEMENT_KEY"

_cache_lock = threading.Lock()
_cache: Optional[Dict[str, Any]] = None
_cache_at = 0.0


class OpenRouterError(Exception):
    """Upstream OpenRouter failure. Carries the upstream status (0 = no HTTP)."""

    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.message = message[:MAX_ERROR_CHARS]
        self.status = status


class MissingKeyError(Exception):
    """The management key is not configured in $HERMES_HOME/.env."""


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------

def _read_key_from_env_file(env_path: Path) -> str:
    """Return the key stored in *env_path*, or "" when absent/unreadable."""
    try:
        # utf-8-sig tolerates a BOM, which Windows editors add (see
        # hermes-agent skill, windows-quirks).
        text = env_path.read_text(encoding="utf-8-sig")
    except OSError:
        return ""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, raw = line.partition("=")
        if name.strip() == ENV_KEY_NAME:
            value = raw.strip().strip("'\"").strip()
            if value:
                return value
            break
    return ""


def _read_management_key() -> str:
    """Return the management key from the Hermes .env, or raise MissingKeyError.

    Resolution order:
    1. ``$HERMES_HOME/.env`` — the profile home when a profile is active.
    2. ``<hermes root>/.env`` — one level above ``profiles/``, the user-level
       file named by spec section 6. Profiles without their own key fall back
       to it, so one key serves the whole desktop app.
    Never logs and never embeds the key in an exception message.
    """
    env_path = get_hermes_home() / ".env"
    key = _read_key_from_env_file(env_path)
    if key:
        return key
    # One level up is the hermes root — except under profiles/, where the
    # root sits two levels up (profiles/<name> -> profiles -> hermes root).
    home = get_hermes_home()
    root = home.parent.parent if home.parent.name.lower() == "profiles" else home.parent
    root_env_path = root / ".env"
    if root_env_path != env_path:
        key = _read_key_from_env_file(root_env_path)
        if key:
            return key
    raise MissingKeyError(
        f"{ENV_KEY_NAME} is not set in {env_path}. "
        "Create a management key at openrouter.ai/keys and add it there."
    )


# ---------------------------------------------------------------------------
# Upstream calls
# ---------------------------------------------------------------------------

def _error_message(body: str, fallback: str) -> str:
    """Extract a human-readable message from an OpenRouter error body."""
    if body:
        try:
            data = json.loads(body)
            if isinstance(data, dict):
                err = data.get("error")
                if isinstance(err, dict):
                    msg = err.get("message") or err.get("code")
                    if msg:
                        return str(msg)
                if err:
                    return str(err)
                for field in ("message", "detail"):
                    if data.get(field):
                        return str(data[field])
        except (json.JSONDecodeError, ValueError):
            snippet = body.strip()[:200]
            if snippet:
                return snippet
    return fallback


def _fetch_json(url: str, api_key: str) -> Dict[str, Any]:
    """GET *url* with Bearer auth. Returns the decoded JSON object."""
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = int(resp.status)
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        fallback = f"OpenRouter returned HTTP {exc.code} for {url.rsplit('/', 1)[-1]}"
        raise OpenRouterError(_error_message(body, fallback), int(exc.code)) from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        reason = getattr(exc, "reason", None) or exc
        raise OpenRouterError(f"OpenRouter unreachable: {reason}", 0) from exc

    if status != 200:
        raise OpenRouterError(
            f"OpenRouter returned HTTP {status}", status
        )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise OpenRouterError("OpenRouter returned invalid JSON", status) from exc
    if not isinstance(data, dict):
        raise OpenRouterError("OpenRouter returned an unexpected payload", status)
    return data


# ---------------------------------------------------------------------------
# Math helpers
# ---------------------------------------------------------------------------

def _round_cents(value: Any) -> float:
    """Coerce to float and round to cents; normalize -0.0 to 0.0."""
    try:
        result = round(float(value) + 0.0, 2)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if result == 0 else result


def _window() -> tuple:
    """Return (start_date, end_date, today) for the last 30 completed UTC days.

    ``end_date`` is the last completed UTC day (yesterday); today is excluded.
    With today = 2026-08-29 the window is 2026-07-30..2026-08-28 inclusive.
    """
    today = datetime.now(timezone.utc).date()
    end = today - timedelta(days=1)
    start = end - timedelta(days=WINDOW_DAYS - 1)
    return start, end, today


# ---------------------------------------------------------------------------
# Summary assembly
# ---------------------------------------------------------------------------

def _extract_credits(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if "total_credits" not in data or "total_usage" not in data:
        raise OpenRouterError(
            "OpenRouter /credits response missing total_credits/total_usage", 200
        )
    return data


def _extract_activity_rows(payload: Dict[str, Any]) -> list:
    """Pull the row list out of /activity's payload, tolerating shape drift.

    Observed live 2026-08-29: {"data": [row, ...]}. Also accepted: a bare
    list, {"data": {"rows": [...]}}, and {"rows": [...]}.
    """
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for candidate in ("rows", "activity", "items", "data"):
            if isinstance(data.get(candidate), list):
                return data[candidate]
    for candidate in ("rows", "activity", "items"):
        if isinstance(payload.get(candidate), list):
            return payload[candidate]
    return []


def _row_is_byok(row: Dict[str, Any]) -> bool:
    """True when a row represents BYOK (bring-your-own-key) usage (spec: excluded)."""
    for field in ("byok", "is_byok", "byok_usage"):
        if row.get(field):
            return True
    byok_detail = row.get("byok_usage_detail")
    if isinstance(byok_detail, dict):
        return any(bool(v) for v in byok_detail.values())
    label = str(row.get("provider") or row.get("endpoint") or "").lower()
    return "byok" in label


def _compute_summary() -> Dict[str, Any]:
    api_key = _read_management_key()

    start, end, today = _window()

    credits_payload = _fetch_json(OPENROUTER_CREDITS_URL, api_key)
    # /activity with no date param returns the last 30 COMPLETED UTC days
    # (verified live 2026-08-29: date= filters a single day and rejects
    # dates older than 30 days with HTTP 400).
    activity_payload = _fetch_json(OPENROUTER_ACTIVITY_URL, api_key)

    credits = _extract_credits(credits_payload)
    total_credits = _round_cents(credits.get("total_credits"))
    total_usage = _round_cents(credits.get("total_usage"))
    # Spec section 2: balance excludes BYOK. total_credits/total_usage are
    # prepaid-credit counters; byok fields are never added here.
    balance = _round_cents(total_credits - total_usage)

    # spend_30d = sum of each row's prepaid `usage`. BYOK spend lives in the
    # separate `byok_usage_inference` field and is excluded (spec N/section 2).
    # Today's partial-day rows (if upstream ever emits them) are skipped too.
    spend_30d = 0.0
    today_iso = today.isoformat()
    start_iso = start.isoformat()
    for row in _extract_activity_rows(activity_payload):
        if not isinstance(row, dict):
            continue
        row_date = str(row.get("date") or "")[:10]
        if row_date and not (start_iso <= row_date < today_iso):
            continue
        usage = row.get("usage", row.get("cost"))
        if usage is not None:
            try:
                spend_30d += float(usage)
            except (TypeError, ValueError):
                continue

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "balance": balance,
        "total_credits": total_credits,
        "total_usage": total_usage,
        "spend_30d": _round_cents(spend_30d),
        "window": {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "excludes_today": True,
        },
        "fetched_at": now_iso,
    }


def _build_summary() -> Dict[str, Any]:
    """Assemble the /summary payload with a short success cache (60 s).

    Failures are never cached, so a recovery is visible on the next poll
    (spec N4: no retry faster than the poll interval is the UI's concern).
    """
    global _cache, _cache_at
    now = time.time()
    with _cache_lock:
        if _cache is not None and (now - _cache_at) < CACHE_TTL_SECONDS:
            return _cache
    payload = _compute_summary()
    with _cache_lock:
        _cache = payload
        _cache_at = time.time()
    return payload


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.get("/summary")
def summary() -> JSONResponse:
    """GET /api/plugins/openrouter-balance/summary

    200 -> contract payload (spec section 4).
    502 -> {"error": "<message>", "status": <upstream code>} on OpenRouter failure.
    503 -> management key not configured.
    """
    try:
        payload = _build_summary()
    except OpenRouterError as exc:
        return JSONResponse(
            status_code=502, content={"error": exc.message, "status": exc.status}
        )
    except MissingKeyError as exc:
        return JSONResponse(
            status_code=503, content={"error": str(exc), "status": 0}
        )
    except Exception:
        return JSONResponse(
            status_code=500,
            content={"error": "Internal error building balance summary", "status": 0},
        )
    return JSONResponse(status_code=200, content=payload)
