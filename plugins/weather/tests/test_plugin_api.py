"""Tests for the weather plugin backend."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest import mock
import unittest

MODULE_PATH = Path(__file__).parents[1] / "dashboard" / "plugin_api.py"
spec = importlib.util.spec_from_file_location("weather_plugin_api", MODULE_PATH)
api = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(api)


class ValidationTests(unittest.TestCase):
    def test_location_query_requires_two_visible_characters(self):
        with self.assertRaises(api.ValidationError):
            api.validate_location_query(" x ")
        self.assertEqual(api.validate_location_query("  Toronto  "), "Toronto")

    def test_coordinates_and_units_are_bounded(self):
        self.assertEqual(api.validate_coordinates("43.6532", "-79.3832"), (43.6532, -79.3832))
        for latitude, longitude in (("91", "0"), ("0", "181"), ("nan", "0")):
            with self.subTest(latitude=latitude, longitude=longitude):
                with self.assertRaises(api.ValidationError):
                    api.validate_coordinates(latitude, longitude)
        self.assertEqual(api.validate_units("metric"), "metric")
        self.assertEqual(api.validate_units("imperial"), "imperial")
        with self.assertRaises(api.ValidationError):
            api.validate_units("kelvin")

    def test_routes_are_exposed(self):
        paths = {getattr(route, "path", None) for route in api.router.routes}
        self.assertTrue({"/locations", "/weather"}.issubset(paths))


class NormalizationTests(unittest.TestCase):
    def test_wmo_codes_have_stable_labels_and_icons(self):
        self.assertEqual(api.weather_code(0), {"code": 0, "condition": "Clear sky", "icon": "☀"})
        self.assertEqual(api.weather_code(65)["condition"], "Heavy rain")
        self.assertEqual(api.weather_code(999)["condition"], "Unknown")

    def test_location_results_are_normalized_and_bounded(self):
        payload = {
            "results": [
                {
                    "id": index,
                    "name": "Toronto",
                    "latitude": 43.65,
                    "longitude": -79.38,
                    "country_code": "CA",
                    "admin1": "Ontario",
                    "timezone": "America/Toronto",
                }
                for index in range(20)
            ]
        }
        results = api.normalize_locations(payload)
        self.assertEqual(len(results), api.MAX_LOCATION_RESULTS)
        self.assertEqual(
            results[0],
            {
                "id": "0",
                "name": "Toronto",
                "displayName": "Toronto, Ontario, CA",
                "latitude": 43.65,
                "longitude": -79.38,
                "countryCode": "CA",
                "admin1": "Ontario",
                "timezone": "America/Toronto",
            },
        )

    def test_forecast_is_normalized_into_the_public_contract(self):
        payload = {
            "latitude": 43.65,
            "longitude": -79.38,
            "timezone": "America/Toronto",
            "current": {
                "time": "2026-09-02T12:00",
                "temperature_2m": 21.4,
                "apparent_temperature": 22.0,
                "weather_code": 3,
                "precipitation": 0.1,
                "relative_humidity_2m": 70,
                "wind_speed_10m": 12,
                "wind_gusts_10m": 20,
                "wind_direction_10m": 240,
                "visibility": 18000,
                "surface_pressure": 1008,
            },
            "hourly": {
                "time": ["2026-09-02T12:00"],
                "temperature_2m": [21.4],
                "apparent_temperature": [22.0],
                "weather_code": [3],
                "precipitation_probability": [40],
                "precipitation": [0.1],
                "relative_humidity_2m": [70],
                "wind_speed_10m": [12],
                "wind_gusts_10m": [20],
                "wind_direction_10m": [240],
                "visibility": [18000],
                "surface_pressure": [1008],
            },
            "daily": {
                "time": ["2026-09-02"],
                "weather_code": [61],
                "temperature_2m_max": [23],
                "temperature_2m_min": [15],
                "precipitation_probability_max": [60],
                "precipitation_sum": [2.5],
                "wind_speed_10m_max": [18],
                "wind_gusts_10m_max": [30],
                "sunrise": ["2026-09-02T06:42"],
                "sunset": ["2026-09-02T19:48"],
            },
        }
        result = api.normalize_forecast(payload)
        self.assertEqual(result["current"]["condition"], "Overcast")
        self.assertEqual(result["current"]["temperature"], 21.4)
        self.assertEqual(result["hourly"][0]["precipitationProbability"], 40)
        self.assertEqual(result["daily"][0]["condition"], "Slight rain")
        self.assertEqual(result["daily"][0]["sunrise"], "2026-09-02T06:42")
        self.assertEqual(result["sourceUpdatedAt"], "2026-09-02T12:00")


class _Response:
    def __init__(self, body: bytes, status: int = 200):
        self.body = body
        self.status = status
        self.read_size = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size=-1):
        self.read_size = size
        return self.body[:size] if size >= 0 else self.body


def response_payload(response):
    if hasattr(response, "body"):
        return json.loads(response.body)
    return dict(response)


class TransportAndCachingTests(unittest.TestCase):
    def setUp(self):
        api.clear_cache()

    def test_fetch_uses_timeout_and_rejects_oversized_responses(self):
        response = _Response(b"x" * (api.MAX_RESPONSE_BYTES + 1))
        with mock.patch.object(api.urllib.request, "urlopen", return_value=response) as opened:
            with self.assertRaisesRegex(api.UpstreamError, "too large"):
                api.fetch_json("https://api.open-meteo.com/v1/forecast")
        self.assertEqual(opened.call_args.kwargs["timeout"], 15.0)
        self.assertEqual(response.read_size, api.MAX_RESPONSE_BYTES + 1)

    def test_fetch_allows_only_fixed_provider_hosts_and_standard_https_port(self):
        with mock.patch.object(api.urllib.request, "urlopen") as opened:
            for url in (
                "https://evil.example/v1/forecast",
                "https://api.open-meteo.com:8443/v1/forecast",
            ):
                with self.subTest(url=url):
                    with self.assertRaisesRegex(api.UpstreamError, "not allowed"):
                        api.fetch_json(url)
        opened.assert_not_called()

    def test_success_is_cached_but_failures_are_not(self):
        calls = []

        def succeeds():
            calls.append("success")
            return {"ok": True}

        self.assertEqual(api.cached("same", succeeds), {"ok": True})
        self.assertEqual(api.cached("same", succeeds), {"ok": True})
        self.assertEqual(calls, ["success"])

        def fails():
            calls.append("failure")
            raise api.UpstreamError("service unavailable")

        for _ in range(2):
            with self.assertRaises(api.UpstreamError):
                api.cached("failure", fails)
        self.assertEqual(calls.count("failure"), 2)


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.location = {
            "name": "Toronto",
            "displayName": "Toronto, Ontario, CA",
            "latitude": 43.65,
            "longitude": -79.38,
            "countryCode": "CA",
            "admin1": "Ontario",
            "timezone": "America/Toronto",
        }
        self.forecast = {
            "current": {"time": "2026-09-02T12:00", "temperature": 21},
            "hourly": [],
            "daily": [],
            "sourceUpdatedAt": "2026-09-02T12:00",
            "timezone": "America/Toronto",
        }
        self.alerts = [{
            "id": "alert-1",
            "title": "Warning",
            "description": "Official wording",
            "severity": "severe",
            "onset": "2026-09-02T13:00:00Z",
            "expires": "2026-09-02T15:00:00Z",
            "sourceName": api.ECCC_SOURCE_NAME,
            "sourceUrl": api.ECCC_SOURCE_URL,
            "isOfficial": True,
        }]

    def test_forecast_failure_does_not_hide_official_alerts(self):
        def forecast_loader(*_args):
            raise api.UpstreamError("Forecast service is unavailable", 503)

        snapshot = api.build_weather_snapshot(
            self.location,
            "metric",
            forecast_loader=forecast_loader,
            alerts_loader=lambda *_args: self.alerts,
        )
        self.assertIsNone(snapshot["current"])
        self.assertEqual(snapshot["alerts"], self.alerts)
        self.assertEqual(snapshot["provider"]["forecast"]["status"], "error")
        self.assertEqual(snapshot["provider"]["alerts"]["status"], "ok")

    def test_alert_failure_does_not_hide_forecast(self):
        def alerts_loader(*_args):
            raise api.UpstreamError("Alert service is unavailable", 503)

        snapshot = api.build_weather_snapshot(
            self.location,
            "metric",
            forecast_loader=lambda *_args: self.forecast,
            alerts_loader=alerts_loader,
        )
        self.assertEqual(snapshot["current"]["temperature"], 21)
        self.assertEqual(snapshot["alerts"], [])
        self.assertEqual(snapshot["provider"]["forecast"]["status"], "ok")
        self.assertEqual(snapshot["provider"]["alerts"]["status"], "error")

    def test_snapshot_has_the_exact_top_level_contract(self):
        snapshot = api.build_weather_snapshot(
            self.location,
            "imperial",
            forecast_loader=lambda *_args: self.forecast,
            alerts_loader=lambda *_args: self.alerts,
        )
        self.assertEqual(
            set(snapshot),
            {"location", "current", "hourly", "daily", "alerts", "provider", "sourceUpdatedAt", "fetchedAt"},
        )
        self.assertEqual(snapshot["location"]["units"], "imperial")

    def test_route_sanitizes_unexpected_failures(self):
        with mock.patch.object(api, "get_weather", side_effect=RuntimeError("secret token and stack")):
            response = api.weather("43.65", "-79.38", name="Toronto", countryCode="CA")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response_payload(response), {"error": "Internal weather service error", "status": 0})


if __name__ == "__main__":
    unittest.main()
