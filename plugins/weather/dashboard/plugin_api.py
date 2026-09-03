"""Weather forecast and official Canadian alert backend.

Hermes mounts ``router`` at ``/api/plugins/weather``. Networking uses only the
Python 3.11 standard library. FastAPI is supplied by the Hermes host.
"""
from __future__ import annotations

import json
import math
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable

try:
    from fastapi import APIRouter
    from fastapi.responses import JSONResponse
except Exception:  # pragma: no cover - local tests without Hermes dependencies
    class _Route:
        def __init__(self, path: str):
            self.path = path

    class APIRouter:  # type: ignore[no-redef]
        def __init__(self):
            self.routes: list[_Route] = []

        def get(self, path: str, **_kwargs):
            self.routes.append(_Route(path))
            return lambda function: function

    class JSONResponse(dict):  # type: ignore[no-redef]
        def __init__(self, status_code: int = 200, content: Any = None, **_kwargs):
            super().__init__(content if isinstance(content, dict) else {})
            self.status_code = status_code


router = APIRouter()

GEOCODING_HOST = "geocoding-api.open-meteo.com"
FORECAST_HOST = "api.open-meteo.com"
ECCC_HOST = "api.weather.gc.ca"
ALLOWED_HOSTS = frozenset({GEOCODING_HOST, FORECAST_HOST, ECCC_HOST})
REQUEST_TIMEOUT_SECONDS = 15.0
MAX_RESPONSE_BYTES = 2_000_000
CACHE_TTL_SECONDS = 60.0
MAX_LOCATION_RESULTS = 10
MAX_HOURLY_ITEMS = 24
MAX_DAILY_ITEMS = 7
MAX_ALERT_RESULTS = 50
ECCC_SOURCE_NAME = "Environment and Climate Change Canada"
ECCC_SOURCE_URL = "https://weather.gc.ca/warnings/index_e.html"
USER_AGENT = "Hermes-Weather-Plugin/1.0 (+https://github.com/NousResearch/hermes-agent)"

_cache: dict[str, tuple[float, Any]] = {}
_cache_lock = threading.Lock()


class ValidationError(ValueError):
    """A public request parameter is invalid."""


class UpstreamError(Exception):
    """A sanitized provider failure safe to return to clients."""

    def __init__(self, message: str, status: int = 0):
        super().__init__(message)
        self.message = str(message)[:200]
        self.status = int(status or 0)


def validate_location_query(value: Any) -> str:
    query = str(value or "").strip()
    if len(query) < 2 or len(query) > 100:
        raise ValidationError("Location search must contain 2 to 100 characters")
    return query


def validate_coordinates(latitude: Any, longitude: Any) -> tuple[float, float]:
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Latitude and longitude must be numbers") from exc
    if not math.isfinite(lat) or not math.isfinite(lon) or not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValidationError("Latitude or longitude is outside its valid range")
    return lat, lon


def validate_units(value: Any) -> str:
    units = str(value or "metric").strip().lower()
    if units not in {"metric", "imperial"}:
        raise ValidationError("Units must be metric or imperial")
    return units


def _bounded_text(value: Any, fallback: str, maximum: int) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    if len(text) > maximum or any(ord(char) < 32 for char in text):
        raise ValidationError("A location field is invalid")
    return text


def _provider_label(host: str) -> str:
    if host == ECCC_HOST:
        return "Alert service"
    if host == GEOCODING_HOST:
        return "Location service"
    return "Forecast service"


def fetch_json(url: str) -> dict[str, Any]:
    """Fetch bounded JSON from one fixed provider host."""
    parsed = urllib.parse.urlsplit(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise UpstreamError("Upstream host is not allowed") from exc
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS or port not in {None, 443}:
        raise UpstreamError("Upstream host is not allowed")
    label = _provider_label(parsed.hostname or "")
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            status = int(getattr(response, "status", 200))
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise UpstreamError(f"{label} returned HTTP {exc.code}", int(exc.code)) from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise UpstreamError(f"{label} is unavailable") from exc
    if len(raw) > MAX_RESPONSE_BYTES:
        raise UpstreamError(f"{label} response is too large", status)
    if not 200 <= status < 300:
        raise UpstreamError(f"{label} returned HTTP {status}", status)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        if not raw.lstrip().startswith((b"{", b"[")):
            raise UpstreamError(f"{label} is unavailable", status) from exc
        raise UpstreamError(f"{label} returned invalid JSON", status) from exc
    if not isinstance(payload, dict):
        raise UpstreamError(f"{label} returned invalid data", status)
    return payload


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def cached(key: str, loader: Callable[[], Any], cacheable: Callable[[Any], bool] | None = None) -> Any:
    """Return a 60-second successful value. Exceptions are never cached."""
    now = time.monotonic()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_TTL_SECONDS:
            return hit[1]
    value = loader()
    if cacheable is None or cacheable(value):
        with _cache_lock:
            _cache[key] = (time.monotonic(), value)
    return value


_WMO_CODES = {
    0: ("Clear sky", "☀"), 1: ("Mainly clear", "🌤"), 2: ("Partly cloudy", "⛅"),
    3: ("Overcast", "☁"), 45: ("Fog", "🌫"), 48: ("Rime fog", "🌫"),
    51: ("Light drizzle", "🌦"), 53: ("Drizzle", "🌦"), 55: ("Heavy drizzle", "🌧"),
    56: ("Light freezing drizzle", "🌧"), 57: ("Freezing drizzle", "🌧"),
    61: ("Slight rain", "🌦"), 63: ("Rain", "🌧"), 65: ("Heavy rain", "🌧"),
    66: ("Light freezing rain", "🌧"), 67: ("Freezing rain", "🌧"),
    71: ("Slight snow", "🌨"), 73: ("Snow", "🌨"), 75: ("Heavy snow", "❄"),
    77: ("Snow grains", "🌨"), 80: ("Slight rain showers", "🌦"),
    81: ("Rain showers", "🌧"), 82: ("Heavy rain showers", "🌧"),
    85: ("Slight snow showers", "🌨"), 86: ("Heavy snow showers", "❄"),
    95: ("Thunderstorm", "⛈"), 96: ("Thunderstorm with hail", "⛈"),
    99: ("Severe thunderstorm with hail", "⛈"),
}


def weather_code(value: Any) -> dict[str, Any]:
    try:
        code = int(value)
    except (TypeError, ValueError):
        code = -1
    condition, icon = _WMO_CODES.get(code, ("Unknown", "?"))
    return {"code": code, "condition": condition, "icon": icon}


def normalize_locations(payload: Any) -> list[dict[str, Any]]:
    rows = payload.get("results", []) if isinstance(payload, dict) else []
    results: list[dict[str, Any]] = []
    for row in rows[:MAX_LOCATION_RESULTS] if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        try:
            lat, lon = validate_coordinates(row.get("latitude"), row.get("longitude"))
        except ValidationError:
            continue
        name = str(row.get("name") or "").strip()
        if not name:
            continue
        admin1 = str(row.get("admin1") or "").strip()
        country = str(row.get("country_code") or "").strip().upper()
        raw_id = row.get("id")
        results.append({
            "id": str(raw_id if raw_id is not None else f"{lat},{lon}"),
            "name": name,
            "displayName": ", ".join(part for part in (name, admin1, country) if part),
            "latitude": lat,
            "longitude": lon,
            "countryCode": country,
            "admin1": admin1,
            "timezone": str(row.get("timezone") or "UTC"),
        })
    return results


def _series_value(section: dict[str, Any], field: str, index: int) -> Any:
    values = section.get(field)
    return values[index] if isinstance(values, list) and index < len(values) else None


def _condition_fields(value: Any) -> dict[str, Any]:
    mapped = weather_code(value)
    return {"weatherCode": mapped["code"], "condition": mapped["condition"], "icon": mapped["icon"]}


def normalize_forecast(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise UpstreamError("Forecast service returned invalid data")
    current_raw = payload.get("current")
    if not isinstance(current_raw, dict) or not current_raw.get("time"):
        raise UpstreamError("Forecast service returned incomplete data")
    current = {
        "time": current_raw.get("time"),
        "temperature": current_raw.get("temperature_2m"),
        "apparentTemperature": current_raw.get("apparent_temperature"),
        **_condition_fields(current_raw.get("weather_code")),
        "precipitation": current_raw.get("precipitation"),
        "humidity": current_raw.get("relative_humidity_2m"),
        "windSpeed": current_raw.get("wind_speed_10m"),
        "windGust": current_raw.get("wind_gusts_10m"),
        "windDirection": current_raw.get("wind_direction_10m"),
        "visibility": current_raw.get("visibility"),
        "pressure": current_raw.get("surface_pressure"),
    }
    hourly_raw = payload.get("hourly") if isinstance(payload.get("hourly"), dict) else {}
    hourly: list[dict[str, Any]] = []
    times = hourly_raw.get("time") if isinstance(hourly_raw.get("time"), list) else []
    for index, timestamp in enumerate(times[:MAX_HOURLY_ITEMS]):
        hourly.append({
            "time": timestamp,
            "temperature": _series_value(hourly_raw, "temperature_2m", index),
            "apparentTemperature": _series_value(hourly_raw, "apparent_temperature", index),
            **_condition_fields(_series_value(hourly_raw, "weather_code", index)),
            "precipitationProbability": _series_value(hourly_raw, "precipitation_probability", index),
            "precipitation": _series_value(hourly_raw, "precipitation", index),
            "humidity": _series_value(hourly_raw, "relative_humidity_2m", index),
            "windSpeed": _series_value(hourly_raw, "wind_speed_10m", index),
            "windGust": _series_value(hourly_raw, "wind_gusts_10m", index),
            "windDirection": _series_value(hourly_raw, "wind_direction_10m", index),
            "visibility": _series_value(hourly_raw, "visibility", index),
            "pressure": _series_value(hourly_raw, "surface_pressure", index),
        })
    daily_raw = payload.get("daily") if isinstance(payload.get("daily"), dict) else {}
    daily: list[dict[str, Any]] = []
    dates = daily_raw.get("time") if isinstance(daily_raw.get("time"), list) else []
    for index, date in enumerate(dates[:MAX_DAILY_ITEMS]):
        daily.append({
            "date": date,
            **_condition_fields(_series_value(daily_raw, "weather_code", index)),
            "temperatureMax": _series_value(daily_raw, "temperature_2m_max", index),
            "temperatureMin": _series_value(daily_raw, "temperature_2m_min", index),
            "precipitationProbability": _series_value(daily_raw, "precipitation_probability_max", index),
            "precipitation": _series_value(daily_raw, "precipitation_sum", index),
            "windSpeed": _series_value(daily_raw, "wind_speed_10m_max", index),
            "windGust": _series_value(daily_raw, "wind_gusts_10m_max", index),
            "sunrise": _series_value(daily_raw, "sunrise", index),
            "sunset": _series_value(daily_raw, "sunset", index),
        })
    return {
        "current": current,
        "hourly": hourly,
        "daily": daily,
        "sourceUpdatedAt": current_raw.get("time"),
        "timezone": str(payload.get("timezone") or "UTC"),
    }


def _property(properties: dict[str, Any], *names: str) -> Any:
    for name in names:
        value = properties.get(name)
        if value is not None and value != "":
            return value
    return None


def normalize_alerts(payload: Any) -> list[dict[str, Any]]:
    features = payload.get("features", []) if isinstance(payload, dict) else []
    alerts: list[dict[str, Any]] = []
    if not isinstance(features, list):
        return alerts
    for feature in features:
        if len(alerts) >= MAX_ALERT_RESULTS:
            break
        if not isinstance(feature, dict) or not isinstance(feature.get("properties"), dict):
            continue
        properties = feature["properties"]
        title = _property(properties, "event", "alert_name_en", "headline", "title")
        description = _property(
            properties, "description", "description_en", "alert_text_en", "instruction", "message"
        )
        if not str(title or "").strip() or not str(description or "").strip():
            continue
        identifier = feature.get("id") or _property(properties, "id", "identifier", "alert_id")
        if not identifier:
            identifier = f"{title}|{_property(properties, 'onset', 'sent', 'issued_at') or ''}"
        raw_severity = str(_property(properties, "severity", "severity_en") or "").lower()
        if raw_severity in {"minor", "moderate", "severe", "extreme"}:
            severity = raw_severity
        else:
            alert_type = str(_property(properties, "alert_type", "type") or "").lower()
            severity = {
                "warning": "severe",
                "emergency": "extreme",
                "watch": "moderate",
                "advisory": "moderate",
                "statement": "moderate",
            }.get(alert_type, "unknown")
        raw_url = str(_property(properties, "url", "web", "source_url") or "")
        source_url = raw_url if raw_url.startswith("https://weather.gc.ca/") else ECCC_SOURCE_URL
        alerts.append({
            "id": str(identifier), "title": str(title), "description": str(description),
            "severity": severity,
            "onset": _property(
                properties, "onset", "effective", "validity_datetime", "publication_datetime", "sent", "issued_at"
            ),
            "expires": _property(
                properties, "expires", "expiry", "expiration_datetime", "event_end_datetime", "expires_at"
            ),
            "sourceName": ECCC_SOURCE_NAME, "sourceUrl": source_url, "isOfficial": True,
        })
    return alerts


def _point_on_segment(longitude: float, latitude: float, first: Any, second: Any) -> bool:
    try:
        x1, y1 = float(first[0]), float(first[1])
        x2, y2 = float(second[0]), float(second[1])
    except (TypeError, ValueError, IndexError):
        return False
    cross = (longitude - x1) * (y2 - y1) - (latitude - y1) * (x2 - x1)
    if abs(cross) > 1e-9:
        return False
    return min(x1, x2) - 1e-9 <= longitude <= max(x1, x2) + 1e-9 and min(y1, y2) - 1e-9 <= latitude <= max(y1, y2) + 1e-9


def _ring_contains_point(ring: Any, latitude: float, longitude: float) -> bool:
    if not isinstance(ring, list) or len(ring) < 4:
        return False
    inside = False
    previous = ring[-1]
    for current in ring:
        if _point_on_segment(longitude, latitude, previous, current):
            return True
        try:
            x1, y1 = float(previous[0]), float(previous[1])
            x2, y2 = float(current[0]), float(current[1])
        except (TypeError, ValueError, IndexError):
            previous = current
            continue
        if (y1 > latitude) != (y2 > latitude):
            crossing = (x2 - x1) * (latitude - y1) / (y2 - y1) + x1
            if longitude < crossing:
                inside = not inside
        previous = current
    return inside


def _polygon_contains_point(polygon: Any, latitude: float, longitude: float) -> bool:
    if not isinstance(polygon, list) or not polygon:
        return False
    return _ring_contains_point(polygon[0], latitude, longitude) and not any(
        _ring_contains_point(hole, latitude, longitude) for hole in polygon[1:]
    )


def _geometry_contains_point(geometry: Any, latitude: float, longitude: float) -> bool:
    if not isinstance(geometry, dict):
        return False
    coordinates = geometry.get("coordinates")
    if geometry.get("type") == "Polygon":
        return _polygon_contains_point(coordinates, latitude, longitude)
    if geometry.get("type") == "MultiPolygon" and isinstance(coordinates, list):
        return any(_polygon_contains_point(polygon, latitude, longitude) for polygon in coordinates)
    return False


def normalize_alerts_for_point(payload: Any, latitude: float, longitude: float) -> list[dict[str, Any]]:
    features = payload.get("features", []) if isinstance(payload, dict) else []
    matching = [
        feature for feature in features
        if isinstance(feature, dict) and _geometry_contains_point(feature.get("geometry"), latitude, longitude)
    ] if isinstance(features, list) else []
    return normalize_alerts({"features": matching})


def _url(host: str, path: str, params: dict[str, Any]) -> str:
    return urllib.parse.urlunsplit(("https", host, path, urllib.parse.urlencode(params), ""))


def fetch_locations(query: str) -> list[dict[str, Any]]:
    url = _url(GEOCODING_HOST, "/v1/search", {
        "name": query, "count": MAX_LOCATION_RESULTS, "language": "en", "format": "json",
    })
    return normalize_locations(fetch_json(url))


def fetch_forecast(location: dict[str, Any], units: str) -> dict[str, Any]:
    params: dict[str, Any] = {
        "latitude": location["latitude"], "longitude": location["longitude"],
        "timezone": location["timezone"], "forecast_hours": MAX_HOURLY_ITEMS,
        "forecast_days": MAX_DAILY_ITEMS,
        "current": ",".join((
            "temperature_2m", "apparent_temperature", "weather_code", "precipitation",
            "relative_humidity_2m", "wind_speed_10m", "wind_gusts_10m",
            "wind_direction_10m", "visibility", "surface_pressure",
        )),
        "hourly": ",".join((
            "temperature_2m", "apparent_temperature", "weather_code",
            "precipitation_probability", "precipitation", "relative_humidity_2m",
            "wind_speed_10m", "wind_gusts_10m", "wind_direction_10m", "visibility",
            "surface_pressure",
        )),
        "daily": ",".join((
            "weather_code", "temperature_2m_max", "temperature_2m_min",
            "precipitation_probability_max", "precipitation_sum", "wind_speed_10m_max",
            "wind_gusts_10m_max", "sunrise", "sunset",
        )),
    }
    if units == "imperial":
        params.update({"temperature_unit": "fahrenheit", "wind_speed_unit": "mph", "precipitation_unit": "inch"})
    return normalize_forecast(fetch_json(_url(FORECAST_HOST, "/v1/forecast", params)))


def fetch_alerts(location: dict[str, Any]) -> list[dict[str, Any]]:
    lat = location["latitude"]
    lon = location["longitude"]
    margin = 0.35
    bbox = f"{lon - margin},{lat - margin},{lon + margin},{lat + margin}"
    url = _url(ECCC_HOST, "/collections/weather-alerts/items", {
        "bbox": bbox, "f": "json", "limit": MAX_ALERT_RESULTS,
    })
    return normalize_alerts_for_point(fetch_json(url), lat, lon)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_weather_snapshot(
    location: dict[str, Any],
    units: str,
    forecast_loader: Callable[..., dict[str, Any]] = fetch_forecast,
    alerts_loader: Callable[..., list[dict[str, Any]]] = fetch_alerts,
) -> dict[str, Any]:
    forecast: dict[str, Any] | None = None
    alerts: list[dict[str, Any]] = []
    forecast_status: dict[str, Any]
    alerts_status: dict[str, Any]
    try:
        forecast = forecast_loader(location, units)
        forecast_status = {"name": "Open-Meteo", "status": "ok"}
    except UpstreamError as exc:
        forecast_status = {"name": "Open-Meteo", "status": "error", "error": exc.message, "statusCode": exc.status}

    if location.get("countryCode", "").upper() == "CA":
        try:
            alerts = alerts_loader(location)
            alerts_status = {"name": ECCC_SOURCE_NAME, "status": "ok"}
        except UpstreamError as exc:
            alerts_status = {"name": ECCC_SOURCE_NAME, "status": "error", "error": exc.message, "statusCode": exc.status}
    else:
        alerts_status = {"name": ECCC_SOURCE_NAME, "status": "not-applicable"}

    if forecast is None and alerts_status["status"] != "ok":
        raise UpstreamError("Weather services are unavailable")
    source_updated = forecast.get("sourceUpdatedAt") if forecast else None
    if not source_updated and alerts:
        source_updated = max((str(alert.get("onset") or "") for alert in alerts), default="") or None
    public_location = dict(location)
    public_location["units"] = units
    return {
        "location": public_location,
        "current": forecast.get("current") if forecast else None,
        "hourly": forecast.get("hourly", []) if forecast else [],
        "daily": forecast.get("daily", []) if forecast else [],
        "alerts": alerts,
        "provider": {"forecast": forecast_status, "alerts": alerts_status},
        "sourceUpdatedAt": source_updated,
        "fetchedAt": _utc_now(),
    }


def _snapshot_is_complete(snapshot: dict[str, Any]) -> bool:
    return all(part.get("status") != "error" for part in snapshot.get("provider", {}).values())


def get_locations(query: str) -> list[dict[str, Any]]:
    normalized = validate_location_query(query)
    return cached(f"locations:{normalized.casefold()}", lambda: fetch_locations(normalized))


def get_weather(
    latitude: Any,
    longitude: Any,
    units: Any = "metric",
    name: Any = "Selected location",
    country_code: Any = "",
    admin1: Any = "",
    timezone_name: Any = "auto",
) -> dict[str, Any]:
    lat, lon = validate_coordinates(latitude, longitude)
    normalized_units = validate_units(units)
    country = _bounded_text(country_code, "", 2).upper()
    if country and (len(country) != 2 or not country.isalpha()):
        raise ValidationError("Country code must contain two letters")
    location = {
        "name": _bounded_text(name, "Selected location", 120),
        "displayName": "",
        "latitude": lat,
        "longitude": lon,
        "countryCode": country,
        "admin1": _bounded_text(admin1, "", 120),
        "timezone": _bounded_text(timezone_name, "auto", 100),
    }
    location["displayName"] = ", ".join(
        part for part in (location["name"], location["admin1"], location["countryCode"]) if part
    )
    key = "weather:" + json.dumps([lat, lon, normalized_units, location["name"], country, location["admin1"], location["timezone"]])
    return cached(
        key,
        lambda: build_weather_snapshot(location, normalized_units),
        cacheable=_snapshot_is_complete,
    )


def _error_response(exc: Exception, fallback: str, default_status: int) -> JSONResponse:
    if isinstance(exc, ValidationError):
        return JSONResponse(status_code=400, content={"error": str(exc), "status": 0})
    if isinstance(exc, UpstreamError):
        return JSONResponse(status_code=default_status, content={"error": exc.message, "status": exc.status})
    return JSONResponse(status_code=500, content={"error": fallback, "status": 0})


@router.get("/locations")
def locations(q: str = "") -> JSONResponse:
    try:
        results = get_locations(q)
    except Exception as exc:
        return _error_response(exc, "Internal location service error", 502)
    return JSONResponse(status_code=200, content={"locations": results})


@router.get("/weather")
def weather(
    latitude: str = "",
    longitude: str = "",
    units: str = "metric",
    name: str = "Selected location",
    countryCode: str = "",
    admin1: str = "",
    timezone: str = "auto",
) -> JSONResponse:
    try:
        snapshot = get_weather(latitude, longitude, units, name, countryCode, admin1, timezone)
    except Exception as exc:
        return _error_response(exc, "Internal weather service error", 502)
    return JSONResponse(status_code=200, content=snapshot)
