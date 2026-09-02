"""Tests for authoritative alert policy and normalization."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).parents[1] / "dashboard" / "plugin_api.py"
spec = importlib.util.spec_from_file_location("weather_alert_api", MODULE_PATH)
api = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(api)


class AlertNormalizationTests(unittest.TestCase):
    def test_eccc_wording_is_preserved_and_marked_official(self):
        wording = "Take cover immediately.\nFollow local authority instructions."
        payload = {
            "features": [{
                "id": "alert-123",
                "properties": {
                    "event": "Severe Thunderstorm Warning",
                    "description": wording,
                    "severity": "Severe",
                    "onset": "2026-09-02T18:00:00Z",
                    "expires": "2026-09-02T20:00:00Z",
                    "url": "https://weather.gc.ca/warnings/report_e.html?on61",
                },
            }]
        }
        alert = api.normalize_alerts(payload)[0]
        self.assertEqual(alert["id"], "alert-123")
        self.assertEqual(alert["title"], "Severe Thunderstorm Warning")
        self.assertEqual(alert["description"], wording)
        self.assertEqual(alert["severity"], "severe")
        self.assertEqual(alert["sourceName"], "Environment and Climate Change Canada")
        self.assertTrue(alert["isOfficial"])

    def test_current_eccc_fields_map_without_changing_wording(self):
        wording = "Official first line.\n\nOfficial second line."
        payload = {
            "features": [{
                "id": "eccc-live-shape",
                "properties": {
                    "alert_type": "warning",
                    "alert_name_en": "air quality warning",
                    "publication_datetime": "2026-08-13T18:46:35.991Z",
                    "validity_datetime": "2026-08-13T18:45:00.000Z",
                    "expiration_datetime": "2026-08-14T10:46:35.991Z",
                    "alert_text_en": wording,
                },
            }]
        }
        alert = api.normalize_alerts(payload)[0]
        self.assertEqual(alert["description"], wording)
        self.assertEqual(alert["severity"], "severe")
        self.assertEqual(alert["onset"], "2026-08-13T18:45:00.000Z")
        self.assertEqual(alert["expires"], "2026-08-14T10:46:35.991Z")

    def test_alerts_are_filtered_to_polygons_covering_the_location(self):
        def feature(identifier, coordinates):
            return {
                "id": identifier,
                "geometry": {"type": "Polygon", "coordinates": [coordinates]},
                "properties": {"event": "Warning", "description": "Official text"},
            }

        inside = feature("inside", [[-80, 43], [-79, 43], [-79, 44], [-80, 44], [-80, 43]])
        outside = feature("outside", [[-78, 43], [-77, 43], [-77, 44], [-78, 44], [-78, 43]])
        alerts = api.normalize_alerts_for_point({"features": [inside, outside]}, 43.65, -79.38)
        self.assertEqual([alert["id"] for alert in alerts], ["inside"])

    def test_alert_results_are_bounded_and_incomplete_rows_are_skipped(self):
        features = [{"id": "missing", "properties": {"severity": "Minor"}}]
        features.extend(
            {"id": f"a-{index}", "properties": {"event": "Warning", "description": "Official text"}}
            for index in range(100)
        )
        alerts = api.normalize_alerts({"features": features})
        self.assertEqual(len(alerts), api.MAX_ALERT_RESULTS)
        self.assertNotIn("missing", {alert["id"] for alert in alerts})


if __name__ == "__main__":
    unittest.main()
