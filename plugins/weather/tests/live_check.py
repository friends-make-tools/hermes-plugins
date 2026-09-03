"""Live Markham check with forced Open-Meteo failure and real MET fallback."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

module_path = Path(__file__).parents[1] / "dashboard" / "plugin_api.py"
spec = importlib.util.spec_from_file_location("weather_live", module_path)
api = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(api)

location = {
    "name": "Markham",
    "displayName": "Markham, Ontario, CA",
    "latitude": 43.8561,
    "longitude": -79.3370,
    "countryCode": "CA",
    "admin1": "Ontario",
    "timezone": "America/Toronto",
}


def fail_open_meteo(*_args):
    raise api.UpstreamError("Injected Open-Meteo failure", 503)


snapshot = api.build_weather_snapshot(
    location,
    "metric",
    forecast_loader=fail_open_meteo,
)
if snapshot["current"] is None:
    raise SystemExit("MET Norway fallback returned no current conditions")
if snapshot["provider"]["forecast"] != {"name": "MET Norway", "status": "ok"}:
    raise SystemExit("MET Norway fallback did not become the active forecast provider")

print(json.dumps({
    "locationRequest": {
        "selected": location["displayName"],
        "primaryFailureInjected": True,
    },
    "weatherRequest": {
        "topLevelFields": sorted(snapshot),
        "currentTemperature": snapshot["current"]["temperature"],
        "currentCondition": snapshot["current"]["condition"],
        "currentHumidity": snapshot["current"]["humidity"],
        "hourlyCount": len(snapshot["hourly"]),
        "dailyCount": len(snapshot["daily"]),
        "alertCount": len(snapshot["alerts"]),
        "provider": snapshot["provider"],
        "fetchedAt": snapshot["fetchedAt"],
    },
}, indent=2))
