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

    def test_met_symbols_use_existing_condition_labels_and_icons(self):
        self.assertEqual(api.met_symbol("clearsky_night"), {"weatherCode": None, "condition": "Clear sky", "icon": "☀"})
        self.assertEqual(api.met_symbol("heavyrainandthunder"), {"weatherCode": None, "condition": "Thunderstorm", "icon": "⛈"})
        self.assertEqual(api.met_symbol("lightsleetshowers_day")["condition"], "Light freezing rain")
        self.assertEqual(api.met_symbol("lightsnowshowers_night")["condition"], "Slight snow showers")
        self.assertEqual(api.met_symbol("unknown_future_symbol"), {"weatherCode": None, "condition": "Unknown", "icon": "?"})

    def test_met_forecast_normalizes_hourly_current_and_daily_aggregation(self):
        payload = met_payload()

        result = api.normalize_met_forecast(payload, "metric", "America/Toronto")

        self.assertEqual(result["sourceUpdatedAt"], "2026-09-02T21:58:00Z")
        self.assertEqual(result["timezone"], "America/Toronto")
        self.assertEqual(result["current"], {
            "time": "2026-09-02T22:00:00Z",
            "temperature": 20.0,
            "apparentTemperature": None,
            "weatherCode": None,
            "condition": "Slight rain showers",
            "icon": "🌦",
            "precipitation": None,
            "humidity": 70.0,
            "windSpeed": 18.0,
            "windGust": 25.2,
            "windDirection": 240.0,
            "visibility": None,
            "pressure": 1008.0,
        })
        self.assertEqual(len(result["hourly"]), 3)
        self.assertEqual(set(result["hourly"][0]), {
            "time", "temperature", "apparentTemperature", "weatherCode", "condition", "icon",
            "precipitationProbability", "precipitation", "humidity", "windSpeed", "windGust",
            "windDirection", "visibility", "pressure",
        })
        self.assertEqual(result["hourly"][1]["precipitationProbability"], 60.0)
        self.assertEqual(result["daily"][0], {
            "date": "2026-09-02",
            "weatherCode": None,
            "condition": "Heavy rain",
            "icon": "🌧",
            "temperatureMax": 22.0,
            "temperatureMin": 20.0,
            "precipitationProbability": 60.0,
            "precipitation": 3.0,
            "windSpeed": 21.6,
            "windGust": 28.8,
            "sunrise": None,
            "sunset": None,
        })
        self.assertEqual(result["daily"][1]["date"], "2026-09-03")
        self.assertEqual(result["daily"][1]["condition"], "Clear sky")

    def test_met_forecast_converts_temperature_wind_and_precipitation_for_imperial(self):
        result = api.normalize_met_forecast(met_payload(), "imperial", "America/Toronto")

        self.assertAlmostEqual(result["current"]["temperature"], 68.0)
        self.assertAlmostEqual(result["current"]["windSpeed"], 11.18468146)
        self.assertIsNone(result["current"]["precipitation"])
        self.assertAlmostEqual(result["hourly"][0]["precipitation"], 1.0 / 25.4)
        self.assertAlmostEqual(result["daily"][0]["temperatureMax"], 71.6)
        self.assertAlmostEqual(result["daily"][0]["precipitation"], 3.0 / 25.4)


def met_payload():
    def row(timestamp, temperature, wind, gust, symbol, rain, probability):
        return {
            "time": timestamp,
            "data": {
                "instant": {"details": {
                    "air_temperature": temperature,
                    "relative_humidity": 70.0,
                    "air_pressure_at_sea_level": 1008.0,
                    "wind_speed": wind,
                    "wind_speed_of_gust": gust,
                    "wind_from_direction": 240.0,
                }},
                "next_1_hours": {
                    "summary": {"symbol_code": symbol},
                    "details": {
                        "precipitation_amount": rain,
                        "probability_of_precipitation": probability,
                    },
                },
            },
        }

    return {
        "properties": {
            "meta": {"updated_at": "2026-09-02T21:58:00Z"},
            "timeseries": [
                row("2026-09-02T22:00:00Z", 20.0, 5.0, 7.0, "lightrainshowers_day", 1.0, 40.0),
                row("2026-09-02T23:00:00Z", 22.0, 6.0, 8.0, "heavyrain", 2.0, 60.0),
                row("2026-09-03T04:00:00Z", 10.0, 3.0, 4.0, "clearsky_night", 0.0, 0.0),
            ],
        },
    }


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

    def test_fetch_allows_the_fixed_met_norway_host(self):
        response = _Response(b"{}")
        with mock.patch.object(api.urllib.request, "urlopen", return_value=response) as opened:
            self.assertEqual(api.fetch_json("https://api.met.no/weatherapi/locationforecast/2.0/compact"), {})
        self.assertEqual(opened.call_count, 1)

    def test_open_meteo_streaming_timeout_body_is_provider_unavailability(self):
        response = _Response(b"Unexpected error while streaming data: timeoutReached")
        with mock.patch.object(api.urllib.request, "urlopen", return_value=response):
            with self.assertRaises(api.UpstreamError) as raised:
                api.fetch_json("https://api.open-meteo.com/v1/forecast")

        self.assertEqual(raised.exception.message, "Forecast service is unavailable")
        self.assertEqual(raised.exception.status, 200)

    def test_html_provider_error_body_is_sanitized_as_unavailability(self):
        response = _Response(b"<html><body>stack trace at https://private.example</body></html>")
        with mock.patch.object(api.urllib.request, "urlopen", return_value=response):
            with self.assertRaises(api.UpstreamError) as raised:
                api.fetch_json("https://api.open-meteo.com/v1/forecast")

        self.assertEqual(raised.exception.message, "Forecast service is unavailable")
        self.assertEqual(raised.exception.status, 200)
        self.assertNotIn("private.example", str(raised.exception))

    def test_malformed_json_looking_body_remains_invalid_json(self):
        response = _Response(b'  {"current": ')
        with mock.patch.object(api.urllib.request, "urlopen", return_value=response):
            with self.assertRaises(api.UpstreamError) as raised:
                api.fetch_json("https://api.open-meteo.com/v1/forecast")

        self.assertEqual(raised.exception.message, "Forecast service returned invalid JSON")
        self.assertEqual(raised.exception.status, 200)

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
            fallback_loader=lambda *_args: (_ for _ in ()).throw(api.UpstreamError("Fallback unavailable", 503)),
            alerts_loader=lambda *_args: self.alerts,
        )
        self.assertIsNone(snapshot["current"])
        self.assertEqual(snapshot["alerts"], self.alerts)
        self.assertEqual(snapshot["provider"]["forecast"]["status"], "error")
        self.assertEqual(snapshot["provider"]["alerts"]["status"], "ok")

    def test_open_meteo_failure_invokes_met_once_and_uses_met_provider_identity(self):
        calls = []

        def primary(*_args):
            calls.append("primary")
            raise api.UpstreamError("Forecast service returned HTTP 503", 503)

        def fallback(*_args):
            calls.append("fallback")
            return self.forecast

        snapshot = api.build_weather_snapshot(
            self.location, "metric", forecast_loader=primary,
            fallback_loader=fallback, alerts_loader=lambda *_args: self.alerts,
        )

        self.assertEqual(calls, ["primary", "fallback"])
        self.assertEqual(snapshot["current"]["temperature"], 21)
        self.assertEqual(snapshot["provider"]["forecast"], {"name": "MET Norway", "status": "ok"})

    def test_primary_success_does_not_invoke_met_fallback(self):
        fallback = mock.Mock(side_effect=AssertionError("fallback must not run"))
        snapshot = api.build_weather_snapshot(
            self.location, "metric", forecast_loader=lambda *_args: self.forecast,
            fallback_loader=fallback, alerts_loader=lambda *_args: self.alerts,
        )

        fallback.assert_not_called()
        self.assertEqual(snapshot["provider"]["forecast"], {"name": "Open-Meteo", "status": "ok"})

    def test_dual_forecast_failure_returns_one_sanitized_unavailable_state(self):
        snapshot = api.build_weather_snapshot(
            self.location,
            "metric",
            forecast_loader=lambda *_args: (_ for _ in ()).throw(api.UpstreamError("primary secret", 503)),
            fallback_loader=lambda *_args: (_ for _ in ()).throw(api.UpstreamError("fallback secret", 502)),
            alerts_loader=lambda *_args: self.alerts,
        )

        self.assertIsNone(snapshot["current"])
        self.assertEqual(snapshot["alerts"], self.alerts)
        self.assertEqual(snapshot["provider"]["forecast"], {
            "name": "MET Norway", "status": "error",
            "error": "Forecast services are unavailable", "statusCode": 502,
        })
        self.assertNotIn("secret", json.dumps(snapshot))

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
