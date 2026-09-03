# Hermes Desktop Weather Plugin Specification

Status: implemented
Version: 1.3
Source plan date: 2026-09-02

## Decision

Build one unified plugin named `weather`.
Its desktop half renders a status chip in `statusBar.right`.
Its backend fetches, bounds, caches, and normalizes provider data.

Use Open-Meteo for manual location search, current conditions, hourly forecasts, and seven-day forecasts.
Use Environment and Climate Change Canada for authoritative Canadian alerts.
Do not infer location from an IP address.
Do not create official alerts from forecast thresholds.

## Package

```text
plugins/weather/
├── plugin.yaml
├── README.md
├── __init__.py
├── dashboard/
│   ├── manifest.json
│   └── plugin_api.py
├── desktop/
│   └── plugin.js
└── tests/
    ├── test_plugin_api.py
    ├── test_alert_policy.py
    └── desktop-contract.test.mjs
```

The backend is enabled through `plugins.enabled`.
The desktop half is enabled in Settings → Plugins.
Both gates are required.

## Backend contract

Expose these scoped routes:

- `GET /locations?q=<manual search text>`
- `GET /weather?latitude=<number>&longitude=<number>&name=<text>&countryCode=<code>&admin1=<text>&timezone=<IANA>&units=<metric|imperial>`

`/locations` returns `{ "locations": [...] }`.
Return no more than 10 normalized results.
Each result includes its provider ID, display name, coordinates, country code, region, and timezone.

`/weather` returns these top-level fields:

```text
location
current
hourly
daily
alerts
provider
sourceUpdatedAt
fetchedAt
```

`current` includes temperature, apparent temperature, condition, precipitation, humidity, wind, visibility, and pressure.
`hourly` contains no more than 24 records.
`daily` contains no more than seven records.
Daily records include sunrise and sunset.

Each alert includes:

- Stable provider ID
- Authoritative title and description
- Normalized severity
- Onset and expiry
- Source name and URL
- `isOfficial: true`

The backend preserves alert title and description wording.
It filters ECCC polygons against the selected coordinates.
It never labels a derived notice as official.

`provider.forecast` and `provider.alerts` have independent status values.
A forecast failure must not hide retrieved official alerts.
An alert failure must not hide valid forecast data.

## Network and safety rules

Use Python 3.11 standard-library networking.
Do not add dependencies or credentials.
Allow only these HTTPS hosts:

- `geocoding-api.open-meteo.com`
- `api.open-meteo.com`
- `api.weather.gc.ca`

Set every request timeout to 15 seconds.
Read no more than 2,000,000 response bytes.
Use a 60-second success cache.
Do not cache exceptions or partial provider failures.
Validate all query text, coordinates, units, country codes, and stored location fields.
Return short public errors without response bodies, secrets, URLs, or stack traces.

## Desktop contract

Use plain uncompiled ESM.
Import only `@hermes/plugin-sdk`, `react`, and `react/jsx-runtime`.
Use `jsx()` and `jsxs()` instead of JSX syntax.
Use Hermes UI components and theme variables.
Do not hardcode colors.

Render a stable-width chip with:

- Condition icon
- Rounded temperature
- Short condition
- Active-alert marker
- Stale marker after a failed refresh

Use one responsive square `PopoverContent` above the chip and align it to the right.
Set its width and height to the same viewport-bounded value.
Use a full-height column with a fixed header, bounded scrolling body, attribution footer, and bottom tab bar.
Keep the selected location and icon-only Refresh control in the fixed header.
Use the native ghost Button and a supported Refresh Codicon.
Give the Refresh control an accessible label and tooltip.
Keep provider attribution in a fixed footer above the tab bar.
Render attribution smaller than content on one truncated, non-wrapping line.
Preserve accessible provider names and links when the visual text truncates.

Show one of these views at a time:

1. Current
2. Hourly
3. Daily
4. Alerts
5. Details
6. Settings

Use a compact native bottom tab bar with tab semantics for view navigation.
Keep all six icon-and-label tabs on one horizontal, non-wrapping line.
Make Current the default view.
Keep initial manual location setup in a compact first-use pane.
After setup, show location search and removal only in Settings.
Do not put Settings controls in the Current view.
Render all six views inside one shared `ScrollArea` body.
Give the middle region `min-h-0`, flexible height, and overflow containment.
Give its `ScrollArea` the full bounded width and height.
Use internal vertical scrolling whenever any view exceeds the available middle region.
Keep the header, attribution, and bottom tab bar outside the scrolling body.
Keep the Hourly view's horizontal forecast strip inside the shared vertical body.

Use one React Query weather query shared by the chip and every view.
Key it by plugin ID, location coordinates, and units.
Use `ctx.rest` for both backend routes.
Use React Query refresh intervals.
Do not use a custom timer loop.
Enable refresh on reconnect and focus.
Disable automatic retries.
Keep prior successful data after refresh failure.
Show stale state and the last successful update.
Keep forecast and alert failure messages separate.

## Settings

Store a version 1 settings object with `ctx.storage`.
It contains:

- Selected normalized location
- Metric or imperial units
- A 5, 10, 15, 30, or 60-minute refresh interval
- Alert notification toggle
- Minimum alert severity

Removing the location disables weather requests and clears alert deduplication state.
Changing location or units changes the query key.

## Alert notification policy

Treat the first successful alert list for each location as a baseline.
Do not notify for alerts active during setup.
Persist alert fingerprints and expiry times.
Remove fingerprints after expiry.
Notify only for new official alerts at or above the chosen severity.
The default minimum is severe.
Use `host.notify` while Hermes has focus.
Use `ctx.os.notify` while Hermes is not focused.
Do not notify when the plugin setting disables alerts.
Hermes retains control of global plugin notification permission.

The plugin is not an emergency-alert service.
Polling stops when the status item unmounts.

## Attribution and privacy

Show Open-Meteo attribution in the popover.
Show ECCC attribution for Canadian alerts.
Open official alert source links with `ctx.os.openExternal`.

Store no complete provider payloads.
Store no credentials.
Transmit only manual search text, selected coordinates, and forecast settings.

## Verification

Backend tests must cover validation, normalization, WMO mapping, cache behavior, sanitized failures, response bounds, alert normalization, and provider independence.
Desktop contract tests must cover identity, status area, square native popover, six-view bottom navigation, one active view, separate Settings, one shared bounded scrolling body, fixed controls outside that body, icon-only refresh, one-line attribution, one query, `ctx.rest`, settings-aware keys, no custom polling, stale behavior, persistence, deduplication, notification disable, and theme safety.

Run Python tests, Node contract tests, Python compilation, and JavaScript syntax checks.
Run controlled live location and weather calls when the network allows.
Do not require live ECCC alerts to exist.
