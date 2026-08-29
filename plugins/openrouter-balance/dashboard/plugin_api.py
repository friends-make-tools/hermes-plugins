"""OpenRouter balance & 30-day spend backend for the Hermes dashboard.

Mounted at /api/plugins/openrouter-balance/ by the Hermes web server
(see hermes_cli/web_server.py: the module-level ``router`` is imported
from the file named in dashboard/manifest.json ``api``).

Serves GET /summary with the contract from specs/openrouter-balance-plugin.md:

    {
      "balance": 41.20,
      "total_credits": 50.00,
      "total_usage": 8.80,
      "spend_30d": 8.80,
      "window": {"start": "2026-07-30", "end": "2026-08-28", "excludes_today": true},
      "fetched_at": "2026-08-29T14:03:11Z"
    }

Rules honored here:
- OPENROUTER_MANAGEMENT_KEY comes from the process environment first, then
  from a Hermes .env file. It is never logged and never appears in a response.
- /credits and /activity need a MANAGEMENT key; a usage key gets 401/403 and
  this backend surfaces that as a 502 with a clear message.
- /activity covers the last 30 COMPLETED UTC days; today is excluded and the
  response says so via window.excludes_today.
- total_usage is a lifetime counter. It is reported as total_usage only;
  the 30-day figure is summed from /activity rows.
- byok_usage_inference is external BYOK credit, not prepaid balance; it is
  never read.
- All money values are rounded to cents at this API edge.

Python stdlib only (urllib, json, os, datetime, threading).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

try:
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse
except Exception:  # Allows local unit tests without dashboard dependencies.
    class APIRouter:  # type: ignore[misc]
        def get(self, *_args, **_kwargs):
            return lambda fn: fn

    class JSONResponse:  # type: ignore[misc]
        def __init__(self, content=None, status_code: int = 200):
            self.status_code = status_code
            self.body = json.dumps(content).encode("utf-8")

router = APIRouter()

# OPENROUTER_API_BASE is a test seam only; production always uses the default.
OPENROUTER_API_BASE = os.environ.get("OPENROUTER_API_BASE", "").strip() or "https://openrouter.ai/api/v1"
KEY_ENV_NAME = "OPENROUTER_MANAGEMENT_KEY"
WINDOW_DAYS = 30
HTTP_TIMEOUT_S = 25


class UpstreamError(Exception):
    """OpenRouter call failed; safe to show, never contains the key."""

    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.message = message
        self.status = status


# ---------------------------------------------------------------------------
# Key sourcing (N1: .env only, never config.yaml, never plugin storage)
# ---------------------------------------------------------------------------

def _env_file_candidates():
    home = (os.environ.get("HERMES_HOME") or "").strip()
    if home:
        home_path = Path(home)
        yield home_path / ".env"
        # A profile-scoped process still finds the user-level .env.
        if home_path.parent.name.lower() == "profiles":
            yield home_path.parent / ".env"
    local_app_data = (os.environ.get("LOCALAPPDATA") or "").strip()
    if local_app_data:
        yield Path(local_app_data) / "hermes" / ".env"


def _read_key_from_env_files() -> str:
    for path in _env_file_candidates():
        try:
            if not path.is_file():
                continue
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith(KEY_ENV_NAME + "="):
                    value = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if value:
                        return value
        except OSError:
            continue
    return ""


def get_management_key() -> str:
    value = (os.environ.get(KEY_ENV_NAME) or "").strip()
    if value:
        return value
    return _read_key_from_env_files()


# ---------------------------------------------------------------------------
# OpenRouter calls
# ---------------------------------------------------------------------------

def _fetch_json(path: str, key: str) -> Any:
    url = OPENROUTER_API_BASE.rstrip("/") + path
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": "Bearer " + key,
            "Accept": "application/json",
            "User-Agent": "hermes-openrouter-balance/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
            payload = response.read()
            status = getattr(response, "status", 200)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            message = (
                "OpenRouter rejected the management key (HTTP %d). "
                "Check %s in the Hermes .env file." % (exc.code, KEY_ENV_NAME)
            )
        else:
            message = "OpenRouter returned HTTP %d for %s" % (exc.code, path)
        raise UpstreamError(message, exc.code)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        reason = getattr(exc, "reason", exc)
        raise UpstreamError("Cannot reach OpenRouter: %s" % reason, 0)
    try:
        return json.loads(payload.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise UpstreamError("OpenRouter returned invalid JSON for %s" % path, status)


def _parse_credits(payload: Any) -> Tuple[float, float]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise UpstreamError("Unexpected /credits response shape", 200)
    try:
        return float(data["total_credits"]), float(data["total_usage"])
    except (KeyError, TypeError, ValueError):
        raise UpstreamError("Unexpected /credits response fields", 200)


def window_bounds(now_utc: datetime) -> Tuple[str, str]:
    """Last 30 completed UTC days: [today-30, today-1]. Today is excluded."""
    end = (now_utc - timedelta(days=1)).date()
    start = (now_utc - timedelta(days=WINDOW_DAYS)).date()
    return start.isoformat(), end.isoformat()


def _parse_activity(payload: Any, window: Tuple[str, str]) -> float:
    rows = payload.get("data") if isinstance(payload, dict) else None
    if rows is None and isinstance(payload, list):
        rows = payload
    if not isinstance(rows, list):
        raise UpstreamError("Unexpected /activity response shape", 200)
    start, end = window
    total = 0.0
    for row in rows:
        if not isinstance(row, dict):
            continue
        # Row dates look like "2026-08-28 00:00:00"; compare by day.
        day = str(row.get("date", ""))[:10]
        if day < start or day > end:
            continue
        try:
            total += float(row.get("usage", 0.0))
        except (TypeError, ValueError):
            continue
    return total


def build_summary(now_utc: Optional[datetime] = None) -> Dict[str, Any]:
    key = get_management_key()
    if not key:
        raise UpstreamError(
            "%s is not set. Add it to the Hermes .env file." % KEY_ENV_NAME, 0
        )
    now_utc = now_utc or datetime.now(timezone.utc)
    window = window_bounds(now_utc)
    total_credits, total_usage = _parse_credits(_fetch_json("/credits", key))
    spend_30d = _parse_activity(_fetch_json("/activity", key), window)
    return {
        "balance": round(total_credits - total_usage, 2),
        "total_credits": round(total_credits, 2),
        "total_usage": round(total_usage, 2),
        "spend_30d": round(spend_30d, 2),
        "window": {"start": window[0], "end": window[1], "excludes_today": True},
        "fetched_at": now_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@router.get("/summary")
def summary():
    try:
        return build_summary()
    except UpstreamError as exc:
        return JSONResponse(
            status_code=502, content={"error": exc.message, "status": exc.status}
        )
    except Exception as exc:  # Last resort: no internals, no key material.
        return JSONResponse(
            status_code=502,
            content={"error": "Backend error: %s" % exc.__class__.__name__, "status": 0},
        )
