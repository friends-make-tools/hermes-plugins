# Spec: OpenRouter Balance & 30-Day Spend — Status Bar Plugin

**Status:** Ready for implementation
**Date:** 2026-08-29 (decisions locked same day)
**Target surface:** Hermes desktop app status bar (Windows host)
**Hermes home:** `$HERMES_HOME` (Windows default: `%LOCALAPPDATA%\hermes\`)

## 1. Problem

The user routes Hermes traffic through OpenRouter. The desktop status bar
shows session state, but nothing about money: how much prepaid balance is
left, and how much was spent in the last 30 days. Checking today requires a
browser trip to openrouter.ai.

**Goal:** a status bar chip in the Hermes desktop app that shows:

1. Remaining OpenRouter prepaid balance (USD).
2. Total spend over the last 30 days (USD).

## 2. Data sources (verified against OpenRouter docs, Aug 2026)

| Data | Endpoint | Auth | Key fields |
|---|---|---|---|
| Lifetime credits + usage | `GET https://openrouter.ai/api/v1/credits` | **Management key** | `data.total_credits`, `data.total_usage`. Balance = total_credits − total_usage. |
| 30-day activity | `GET https://openrouter.ai/api/v1/activity` | **Management key** | Last 30 **completed** UTC days, rows grouped by date + model + endpoint. Each row: `usage` (USD), `requests`, tokens. 30-day spend = sum of `usage` over all rows. Optional `date=YYYY-MM-DD` filter. |
| Per-key usage (NOT used) | `GET https://openrouter.ai/api/v1/key` | Normal usage key | Per-key only. Cannot replace the two calls above; do not use in v1. |

Caveats the implementer must honor:

- `/credits` and `/activity` return **403 for a normal usage key**. Only a
  management key works. The key Hermes uses for inference will NOT work.
- `/activity` covers the last 30 **completed** UTC days. Today's partial
  spend is not included. The UI must not claim "today included".
- `total_usage` is a lifetime cumulative counter. Never display it as the
  30-day figure; derive 30-day spend from `/activity`.
- `byok_usage_inference` is external BYOK credit, separate from prepaid
  balance. Exclude from both numbers.

## 3. Decisions (user-confirmed 2026-08-29)

| # | Decision |
|---|---|
| D1 | A **new dedicated management key** will be created for this plugin (not shared with inference). |
| D2 | **Option B architecture**: Python backend reads the key from `.env`; the key never enters the renderer. |
| D3 | Chip shows balance **and** 30-day spend: `OR $41.20 · 30d $8.80`. |
| D4 | Poll interval: **5 minutes** (configurable, see R5). |
| D5 | Chip click opens `https://openrouter.ai/activity` in the system browser (orchestrator decision, low stakes). |

## 4. Architecture — Option B (locked)

One plugin folder, three files:

```
$HERMES_HOME/plugins/openrouter-balance/
├── plugin.yaml              # manifest; "api": "plugin_api.py"
├── dashboard/
│   └── plugin_api.py        # Python backend; stdlib only (urllib, json)
└── desktop/
    └── plugin.js            # desktop half; registers the status bar chip
```

- **Backend (`plugin_api.py`)** — reads `OPENROUTER_MANAGEMENT_KEY` from
  `$HERMES_HOME/.env`. Serves `GET /summary` under the scoped namespace
  `/api/plugins/openrouter-balance/`. Calls both OpenRouter endpoints with
  `Authorization: Bearer <key>`. No new dependencies.
- **Desktop (`plugin.js`)** — polls the backend with `ctx.rest` every 5 min
  via the app's shared React Query client (`refetchInterval`); never
  hand-rolls a poll loop. Registers one chip in `area: 'statusBar.right'`.
- **Why not desktop-only:** a management key can create and destroy API
  keys; it must not sit in plaintext renderer storage (rejected Option A).

### Backend contract

`GET /api/plugins/openrouter-balance/summary` →

```json
{
  "balance": 41.20,
  "total_credits": 50.00,
  "total_usage": 8.80,
  "spend_30d": 8.80,
  "window": { "start": "2026-07-30", "end": "2026-08-28", "excludes_today": true },
  "fetched_at": "2026-08-29T14:03:11Z"
}
```

- Numbers rounded to cents. `balance` = total_credits − total_usage.
- `spend_30d` = sum of `usage` across all `/activity` rows.
- On OpenRouter failure: HTTP 502 with `{"error": "<message>", "status": <code>}`.
  The chip keeps its last values (R3).

## 5. Requirements

### Functional

- **R1** — Register a chip in `area: 'statusBar.right'`: `OR $<balance> · 30d $<spend>`.
- **R2** — Refresh every 5 minutes (D4), via React Query `refetchInterval`.
- **R3** — Error/stale behavior: keep last known values, dim the chip
  (secondary text color), tooltip shows "last updated HH:MM". First-load
  failure shows `OR: —`. Errors go to `host.logs`, never toast loops.
- **R4** — Hover tooltip: remaining balance, lifetime purchased, lifetime
  used, 30-day spend, last-updated time, and "30-day window excludes today".
- **R5** — Poll interval configurable (plugin config or constant at top of
  `plugin.js`); default 300 s. Key sourcing fixed to `.env` (D2).
- **R6** — Click on chip opens `https://openrouter.ai/activity`
  (`ctx.os.openExternal`).

### Non-functional

- **N1** — Secret: `OPENROUTER_MANAGEMENT_KEY` lives ONLY in
  `$HERMES_HOME/.env`. Never in `config.yaml`, never in plugin storage,
  never logged.
- **N2** — Theme: app theme vars only (`var(--ui-text-secondary)`,
  `var(--ui-stroke-secondary)`, `var(--ui-accent)`). No hardcoded colors.
- **N3** — `plugin.js` imports only `@hermes/plugin-sdk`, `react`,
  `react/jsx-runtime`. UI written with `jsx()` calls — JSX syntax does not
  parse in the uncompiled plugin file.
- **N4** — Tolerate OpenRouter downtime: failed refresh keeps prior data,
  no retry faster than the poll interval.
- **N5** — Backend uses Python stdlib only; must run under Hermes's Python
  3.11 on Windows.

## 6. Setup prerequisites (user actions, one-time)

1. Create a **new management key** at openrouter.ai/keys, dedicated to this
   plugin (D1). Note: OpenRouter management keys start `sk-or-v1-...` like
   usage keys; the key TYPE is chosen when creating it.
2. Add to `$HERMES_HOME/.env` (Windows default:
   `%LOCALAPPDATA%\hermes\.env`):
   `OPENROUTER_MANAGEMENT_KEY=sk-or-v1-...`
3. Enable gates (two, both required — classic "plugin not appearing" trap):
   - `plugins.enabled` in `config.yaml` must include `openrouter-balance`
     (via `hermes config set`, never hand-edit).
   - Settings → Plugins → toggle the desktop half on.

## 7. Acceptance criteria

- **AC1** — Chip appears in the status bar right within seconds of
  ⌘K → Reload desktop plugins; no error toast.
- **AC2** — Balance and 30-day spend match the openrouter.ai dashboard
  (allow the completed-UTC-days caveat for the 30-day figure).
- **AC3** — Network cut: chip keeps last values, dims, tooltip shows stale
  time; no crash, no unhandled rejection.
- **AC4** — Invalid key (401/403): chip shows error state, message lands in
  host logs, no toast loop.
- **AC5** — `config.yaml` and plugin storage contain no secret; the key is
  read only from `.env`.
- **AC6** — Editing `plugin.js` hot-reloads without restarting the app.
- **AC7** — `curl` against the backend `/summary` returns the contract JSON
  (section 4) before the UI is wired.
- **AC8** — Click on the chip opens the OpenRouter activity page.

## 8. Out of scope (v2 candidates)

- Per-model spend breakdown (a popover or page could reuse `/activity`).
- Balances for other providers.
- Low-balance alerts via `ctx.os.notify`.
- BYOK usage display.
- Today-spend approximation from `/key` (per-key, unreliable account-wide).

## 9. Roster (recorded 2026-08-29)

Profiles for this plugin. All use `z-ai/glm-5.3-flash` on openrouter.

| Profile | Role | Assignment |
|---|---|---|
| project-manager | Orchestrator | Owns the board, blockers, and acceptance sign-off |
| plugin-backend-dev | Backend worker | `plugin.yaml` + `dashboard/plugin_api.py`, curl-verified `/summary` |
| plugin-frontend-dev | Desktop worker | `desktop/plugin.js` status bar chip |
| software-dev-expert | Existing (idle) | Generalist; not used, role overlaps both workers |
| bot-hr | HR | Built the roster and handed off to project-manager |
