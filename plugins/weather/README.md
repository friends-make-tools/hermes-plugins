# Weather

This unified Hermes plugin adds a weather chip to `statusBar.right`.
The chip opens one compact native popover.
A six-button row shows one view at a time:

- Current conditions
- The next 24 hours
- A seven-day forecast
- Official Canadian weather alerts
- Weather details
- Location, units, refresh, and notification settings

Current is the default view.
Manual refresh stays in the popover header.
All six views use one shared body with a 16-rem or 55-viewport-height maximum.
The body scrolls vertically when its active view needs more space.
The header, view buttons, refresh control, and attribution stay outside that body.
The first-use view keeps manual location setup compact.
After setup, location search and removal stay in Settings.

Open-Meteo supplies location search and forecast data.
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
A forecast outage does not hide successfully retrieved official alerts.

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

The plugin sends the selected coordinates and forecast settings to Open-Meteo.
For Canadian locations, it sends a small coordinate bounding box to ECCC.
It filters returned alert polygons against the selected point.
It stores only settings and alert fingerprints.
It does not store complete provider payloads.

Weather data: [Open-Meteo](https://open-meteo.com/).
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
