# Weather

https://github.com/user-attachments/assets/eee64f3a-fa43-43d4-9611-39f9dc562897

This unified Hermes plugin adds a weather chip to `statusBar.right`.
The chip opens a responsive square native popover.
Explicit inline dimensions keep the popover square in uncompiled desktop plugins.
A full-height flex shell and bounded `ScrollArea` also use inline geometry.
Critical geometry does not depend on Tailwind arbitrary classes.
A fixed four-item bottom tab bar shows one view at a time:

- A combined Forecast with a current hero, six hours, and seven compact days
- Official Canadian weather alerts
- Weather details
- Location, units, refresh, and notification settings

Forecast is the default view.
Its current hero shows a large icon, rounded temperature, condition, and feels-like value.
The hero also shows local update time and icon-based rain, humidity, and wind metrics.
Six equal cells show the next six hours in one row.
Seven dense daily rows align weekday, date, condition, high, low, rain, and wind values.
Daily rain shows probability when available and amount otherwise.
An icon-only Refresh control stays in the fixed popover header.
All four views use one shared bounded and vertically scrolling body.
The body fills the space between the fixed header and fixed footer controls.
Provider attribution stays on one truncated line above the bottom tab bar.
All four readable icon tabs stay on one horizontal line.
The first-use view keeps manual location setup compact.
After setup, location search and removal stay in Settings.

Open-Meteo supplies location search and primary forecast data.
MET Norway supplies forecast data when Open-Meteo is unavailable.
Environment and Climate Change Canada supplies official Canadian alerts.
The plugin does not infer a location from an IP address.

## Package parts

| Part | File | Role |
|---|---|---|
| Backend | `dashboard/plugin_api.py` | Serves `GET /locations` and `GET /weather`. |
| Desktop | `desktop/plugin.js` | Renders the chip and popover. |
| Manifests | `plugin.yaml`, `dashboard/manifest.json` | Declare the unified package and backend. |

Hermes mounts the routes at:

- `/api/plugins/weather/locations?q=Toronto`
- `/api/plugins/weather/weather?latitude=43.6532&longitude=-79.3832&name=Toronto&countryCode=CA&timezone=America%2FToronto&units=metric`

The weather response contains exactly these top-level fields:

- `location`
- `current`
- `hourly`
- `daily`
- `alerts`
- `provider`
- `sourceUpdatedAt`
- `fetchedAt`

Forecast and alert provider states remain separate.
An alert outage does not remove forecast data.
A failure from both forecast providers does not hide retrieved official alerts.
The forecast provider state names the provider whose data is active.

Provider failures use short, fixed public messages.
Non-JSON error bodies map to provider unavailability, including Open-Meteo streaming timeouts and HTML error pages.
The backend never returns raw provider text, HTML, stack traces, or request URLs.
It keeps an upstream response status in `statusCode` when one is available.
Malformed JSON-looking bodies still report an invalid JSON error.

## Install and enable

Copy the `plugins/weather` folder into the Hermes application plugin folder.
This repository task does not install the plugin.

Two enable gates apply:

1. Add `weather` to `plugins.enabled` for the Python backend.
2. Enable Weather under Settings → Plugins for the desktop half.

Restart the gateway after backend changes.
Use ⌘K → Reload desktop plugins after desktop changes.

No API key is required.
The backend only contacts these fixed hosts:

- `geocoding-api.open-meteo.com`
- `api.open-meteo.com`
- `api.met.no`
- `api.weather.gc.ca`

## Settings

Settings use plugin-scoped `ctx.storage` with schema version 1.
They include the selected location, units, refresh interval, alert toggle, and minimum severity.
Allowed refresh periods are 5, 10, 15, 30, and 60 minutes.

The first alert result becomes a baseline.
It does not cause notifications.
Later severe or extreme official alerts can cause one notification.
Stored alert fingerprints suppress repeats across reloads.
Expired fingerprints are removed.

Hermes controls the global plugin notification permission.
This plugin also has its own alert notification toggle.

## Privacy and attribution

The plugin sends selected coordinates and forecast settings to Open-Meteo.
It sends selected coordinates to MET Norway only when the primary forecast fails.
For Canadian locations, it sends a small coordinate bounding box to ECCC.
It filters returned alert polygons against the selected point.
It stores only settings and alert fingerprints.
It does not store complete provider payloads.

Weather data: [Open-Meteo](https://open-meteo.com/).
Fallback weather data: [MET Norway](https://www.met.no/en).
Official Canadian alerts: [Environment and Climate Change Canada](https://weather.gc.ca/warnings/index_e.html).

## Tests

Run from the repository root:

```bash
python -m unittest discover -s plugins/weather/tests -p 'test_*.py' -v
node --test plugins/weather/tests/desktop-contract.test.mjs
python -m compileall -q plugins/weather
node --check plugins/weather/desktop/plugin.js
```

The Python tests use only the standard library.
The desktop test checks the uncompiled ESM contract.

The canonical design spec is [`specs/weather-plugin.md`](../../specs/weather-plugin.md).
