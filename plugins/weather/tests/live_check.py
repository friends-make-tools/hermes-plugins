"""Controlled live check for Open-Meteo location and weather calls."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

module_path = Path(__file__).parents[1] / "dashboard" / "plugin_api.py"
spec = importlib.util.spec_from_file_location("weather_live", module_path)
api = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(api)

locations = api.get_locations("Toronto")
if not locations:
    raise SystemExit("Open-Meteo location search returned no Toronto results")
selected = next((row for row in locations if row.get("countryCode") == "CA"), locations[0])
snapshot = api.get_weather(
    selected["latitude"],
    selected["longitude"],
    "metric",
    selected["name"],
    selected["countryCode"],
    selected["admin1"],
    selected["timezone"],
)
print(json.dumps({
    "locationRequest": {
        "query": "Toronto",
        "resultCount": len(locations),
        "selected": selected["displayName"],
    },
    "weatherRequest": {
        "topLevelFields": sorted(snapshot),
        "currentTemperature": snapshot["current"].get("temperature") if snapshot["current"] else None,
        "currentCondition": snapshot["current"].get("condition") if snapshot["current"] else None,
        "hourlyCount": len(snapshot["hourly"]),
        "dailyCount": len(snapshot["daily"]),
        "alertCount": len(snapshot["alerts"]),
        "provider": snapshot["provider"],
        "fetchedAt": snapshot["fetchedAt"],
    },
}, indent=2))
