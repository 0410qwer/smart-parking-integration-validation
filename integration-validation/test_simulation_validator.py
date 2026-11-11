import json
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from integration_adapters import (
    HttpJsonClient,
    OptionalMqttPublisher,
    SQLiteRecordAdapter,
    validate_event_record,
    validate_http_event_response,
    validate_mqtt_payload,
    validate_web_status,
)
from measurement_utils import (
    calculate_detection_accuracy,
    duplicate_event_decision,
    event_delivery_order,
    measure_http_request,
    measure_local_processing,
    measure_true_sensor_to_web_latency,
    recovery_duration,
)
from simulation_validator import (
    ParkingEventValidator,
    SimulatedEventChannel,
    parse_event_json,
)


FIXTURE_PATH = Path(__file__).with_name("simulated_events.json")


def load_simulated_events():
    with FIXTURE_PATH.open(encoding="utf-8") as fixture_file:
        fixture = json.load(fixture_file)
    if fixture.get("simulation") is not True:
        raise ValueError("fixture must be explicitly marked as a simulation")
    return fixture["events"]


def make_event(event_id="SIM-TEST-001", space="P-01", status="AVAILABLE",
               timestamp="2026-10-29T09:00:00Z"):
    return {
        "event_id": event_id,
        "parking_space_id": space,
        "status": status,
        "timestamp": timestamp,
    }


class ParkingEventValidatorTests(unittest.TestCase):
    def test_sim_001_accepts_available_event(self):
        validator = ParkingEventValidator()
        validator.accept(make_event())
        self.assertEqual(validator.latest_status_by_space, {"P-01": "AVAILABLE"})

    def test_sim_002_accepts_occupied_event(self):
        validator = ParkingEventValidator()
        validator.accept(make_event(status="OCCUPIED"))
        self.assertEqual(validator.latest_status_by_space, {"P-01": "OCCUPIED"})

    def test_sim_003_accepts_both_status_transitions(self):
        validator = ParkingEventValidator()
        validator.accept(make_event(status="AVAILABLE"))
        self.assertEqual(validator.latest_status_by_space["P-01"], "AVAILABLE")
        validator.accept(make_event(
            event_id="SIM-TEST-002",
            status="OCCUPIED",
            timestamp="2026-10-29T09:00:01Z",
        ))
        self.assertEqual(validator.latest_status_by_space["P-01"], "OCCUPIED")
        validator.accept(make_event(
            event_id="SIM-TEST-003",
            status="AVAILABLE",
            timestamp="2026-10-29T09:00:02Z",
        ))
        self.assertEqual(validator.latest_status_by_space["P-01"], "AVAILABLE")

    def test_sim_004_accepts_repeated_identical_status_updates(self):
        validator = ParkingEventValidator()
        validator.accept(make_event(status="AVAILABLE"))
        validator.accept(make_event(
            event_id="SIM-TEST-002",
            status="AVAILABLE",
            timestamp="2026-10-29T09:00:01Z",
        ))
        self.assertEqual(validator.latest_status_by_space["P-01"], "AVAILABLE")
        self.assertEqual(
            validator.latest_timestamp_by_space["P-01"].isoformat(),
            "2026-10-29T09:00:01+00:00",
        )

    def test_sim_005_rejects_invalid_status_values(self):
        for invalid_status in ("RESERVED", "available", "", None, 1):
            with self.subTest(status=invalid_status):
                with self.assertRaises(ValueError):
                    ParkingEventValidator().accept(make_event(status=invalid_status))

    def test_sim_006_rejects_each_missing_required_field(self):
        for field in ("event_id", "parking_space_id", "status", "timestamp"):
            with self.subTest(field=field):
                event = make_event()
                del event[field]
                with self.assertRaisesRegex(ValueError, field):
                    ParkingEventValidator().accept(event)

    def test_sim_007_rejects_blank_required_fields(self):
        for field in ("event_id", "parking_space_id", "status", "timestamp"):
            with self.subTest(field=field):
                event = make_event()
                event[field] = "  "
                with self.assertRaises(ValueError):
                    ParkingEventValidator().accept(event)

    def test_sim_008_rejects_malformed_timestamps(self):
        for timestamp in (
            "not-a-date",
            "2026-02-30T09:00:00Z",
            "2026-10-29",
            "2026-10-29T25:00:00Z",
        ):
            with self.subTest(timestamp=timestamp):
                with self.assertRaises(ValueError):
                    ParkingEventValidator().accept(make_event(timestamp=timestamp))

    def test_sim_009_requires_timezone_in_timestamp(self):
        with self.assertRaisesRegex(ValueError, "timezone"):
            ParkingEventValidator().accept(
                make_event(timestamp="2026-10-29T09:00:00")
            )

    def test_sim_010_rejects_duplicate_event_ids(self):
        validator = ParkingEventValidator()
        validator.accept(make_event())
        with self.assertRaisesRegex(ValueError, "duplicate event_id"):
            validator.accept(make_event(
                status="OCCUPIED",
                timestamp="2026-10-29T09:00:01Z",
            ))

    def test_sim_011_rejects_out_of_order_events(self):
        validator = ParkingEventValidator()
        validator.accept(make_event(timestamp="2026-10-29T09:00:05Z"))
        with self.assertRaisesRegex(ValueError, "timestamp must be later"):
            validator.accept(make_event(
                event_id="SIM-TEST-002",
                timestamp="2026-10-29T09:00:04Z",
            ))

    def test_sim_012_rejects_equal_timestamps_for_same_space(self):
        validator = ParkingEventValidator()
        validator.accept(make_event())
        with self.assertRaisesRegex(ValueError, "timestamp must be later"):
            validator.accept(make_event(event_id="SIM-TEST-002"))

    def test_sim_013_keeps_multiple_parking_spaces_independent(self):
        validator = ParkingEventValidator()
        validator.accept(make_event(space="P-01", timestamp="2026-10-29T09:00:05Z"))
        validator.accept(make_event(
            event_id="SIM-TEST-002",
            space="P-02",
            timestamp="2026-10-29T08:00:00Z",
            status="OCCUPIED",
        ))
        self.assertEqual(
            validator.latest_status_by_space,
            {"P-01": "AVAILABLE", "P-02": "OCCUPIED"},
        )
        self.assertEqual(
            validator.latest_timestamp_by_space["P-01"].isoformat(),
            "2026-10-29T09:00:05+00:00",
        )
        self.assertEqual(
            validator.latest_timestamp_by_space["P-02"].isoformat(),
            "2026-10-29T08:00:00+00:00",
        )

    def test_sim_014_rejects_delayed_stale_event(self):
        validator = ParkingEventValidator()
        validator.accept(make_event(timestamp="2026-10-29T09:00:05Z"))
        with self.assertRaisesRegex(ValueError, "timestamp must be later"):
            validator.accept(make_event(
                event_id="SIM-DELAYED",
                status="OCCUPIED",
                timestamp="2026-10-29T09:00:03Z",
            ))
        self.assertEqual(validator.latest_status_by_space, {"P-01": "AVAILABLE"})
        self.assertEqual(
            validator.latest_timestamp_by_space["P-01"].isoformat(),
            "2026-10-29T09:00:05+00:00",
        )

    def test_sim_015_rejected_duplicate_does_not_change_state(self):
        validator = ParkingEventValidator()
        validator.accept(make_event(status="AVAILABLE"))
        with self.assertRaises(ValueError):
            validator.accept(make_event(status="OCCUPIED"))
        self.assertEqual(validator.latest_status_by_space, {"P-01": "AVAILABLE"})

    def test_sim_016_buffers_events_while_disconnected(self):
        channel = SimulatedEventChannel()
        channel.disconnect()
        with self.assertRaisesRegex(ValueError, "valid ISO 8601"):
            channel.send(make_event(timestamp="invalid"))
        event = make_event()
        channel.send(event)
        with self.assertRaisesRegex(ValueError, "duplicate buffered event_id"):
            channel.send(event)
        self.assertEqual(channel.buffered_count, 1)
        self.assertEqual(channel.delivered, [])

    def test_sim_017_resumes_delivery_after_reconnection(self):
        channel = SimulatedEventChannel()
        channel.disconnect()
        event = make_event()
        channel.send(event)
        recovered = channel.reconnect()
        self.assertEqual(channel.buffered_count, 0)
        self.assertEqual(len(channel.delivered), 1)
        self.assertEqual(recovered, [event])
        self.assertEqual(channel.delivered[0]["event_id"], event["event_id"])
        self.assertTrue(channel.connected)

    def test_sim_018_orders_buffered_events_during_recovery(self):
        channel = SimulatedEventChannel()
        channel.disconnect()
        channel.send(make_event(
            event_id="SIM-LATE",
            status="OCCUPIED",
            timestamp="2026-10-29T09:00:02Z",
        ))
        channel.send(make_event(
            event_id="SIM-EARLY",
            timestamp="2026-10-29T09:00:01Z",
        ))
        recovered = channel.reconnect()
        self.assertEqual(
            [event["event_id"] for event in recovered],
            ["SIM-EARLY", "SIM-LATE"],
        )
        self.assertEqual(channel.buffered_count, 0)

        class FailOnceValidator(ParkingEventValidator):
            def __init__(self):
                super().__init__()
                self.failed_once = False

            def accept(self, event):
                if event["event_id"] == "SIM-RETRY" and not self.failed_once:
                    self.failed_once = True
                    raise ValueError("simulated transient delivery failure")
                super().accept(event)

        retry_channel = SimulatedEventChannel(FailOnceValidator())
        retry_channel.disconnect()
        retry_channel.send(make_event(event_id="SIM-RETRY"))
        with self.assertRaisesRegex(ValueError, "transient"):
            retry_channel.reconnect()
        self.assertEqual(retry_channel.buffered_count, 1)
        self.assertEqual(retry_channel.delivered, [])
        self.assertEqual(
            [event["event_id"] for event in retry_channel.reconnect()],
            ["SIM-RETRY"],
        )
        self.assertEqual(retry_channel.buffered_count, 0)

    def test_sim_019_rejects_invalid_parking_space_ids(self):
        for space_id in ("", " P-01", "P 01", "P/01", "P-01!", "P-01\n"):
            with self.subTest(space_id=space_id):
                with self.assertRaisesRegex(ValueError, "parking_space_id"):
                    ParkingEventValidator().accept(
                        make_event(space=space_id)
                    )

    def test_sim_020_accepts_boundary_space_id_and_rejects_too_long(self):
        validator = ParkingEventValidator()
        validator.accept(make_event(space="A" + ("x" * 31)))
        with self.assertRaisesRegex(ValueError, "parking_space_id"):
            ParkingEventValidator().accept(make_event(space="A" + ("x" * 32)))

    def test_sim_021_rejects_malformed_json(self):
        for payload in (
            '{"event_id":',
            b"\xff",
            '{"status":"AVAILABLE","status":"OCCUPIED"}',
            '{"value":NaN}',
        ):
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(ValueError, "valid JSON"):
                    parse_event_json(payload)

    def test_sim_022_requires_json_object_root(self):
        for payload in ("[]", '"event"', "null", "42"):
            with self.subTest(payload=payload):
                with self.assertRaisesRegex(ValueError, "object"):
                    parse_event_json(payload)

    def test_sim_023_calculates_accuracy_from_labelled_data(self):
        result = calculate_detection_accuracy([
            {"expected": "OCCUPIED", "observed": "OCCUPIED"},
            {"expected": "AVAILABLE", "observed": "AVAILABLE"},
            {"expected": "OCCUPIED", "observed": "AVAILABLE"},
        ])
        self.assertEqual(result["correct"], 2)
        self.assertEqual(result["total"], 3)
        self.assertAlmostEqual(result["accuracy_percent"], 200 / 3)
        self.assertEqual(result["evidence_type"], "LABELLED_INPUT_REQUIRED")
        labelled_sample = [
            {
                "expected": "OCCUPIED" if index < 10 else "AVAILABLE",
                "observed": "OCCUPIED" if index < 9 else "AVAILABLE",
            }
            for index in range(20)
        ]
        boundary_result = calculate_detection_accuracy(labelled_sample)
        self.assertEqual(boundary_result["correct"], 19)
        self.assertEqual(boundary_result["total"], 20)
        self.assertEqual(boundary_result["accuracy_percent"], 95.0)
        for correct, expected_percent in ((18, 90.0), (20, 100.0)):
            sample = [{"expected": "OCCUPIED", "observed": "OCCUPIED" if i < correct else "AVAILABLE"} for i in range(20)]
            self.assertEqual(calculate_detection_accuracy(sample)["accuracy_percent"], expected_percent)

    def test_sim_024_accuracy_rejects_empty_or_incomplete_samples(self):
        with self.assertRaisesRegex(ValueError, "at least one"):
            calculate_detection_accuracy([])
        with self.assertRaisesRegex(ValueError, "expected and observed"):
            calculate_detection_accuracy([{"expected": "AVAILABLE"}])
        for invalid_label in ("UNKNOWN", None, ["OCCUPIED"]):
            with self.subTest(invalid_label=invalid_label):
                with self.assertRaisesRegex(ValueError, "label must be"):
                    calculate_detection_accuracy([
                        {"expected": invalid_label, "observed": "AVAILABLE"}
                    ])
                with self.assertRaisesRegex(ValueError, "label must be"):
                    calculate_detection_accuracy([
                        {"expected": "AVAILABLE", "observed": invalid_label}
                    ])

    def test_sim_025_measures_local_processing_without_target_comparison(self):
        with patch("measurement_utils.perf_counter", side_effect=[10.0, 10.125]):
            result, elapsed = measure_local_processing(sum, [1, 2, 3])
        self.assertEqual(result, 6)
        self.assertEqual(elapsed, 0.125)

    def test_sim_026_measures_http_operation_as_request_response(self):
        operation = Mock(return_value=(204, {"accepted": True}))
        with patch("measurement_utils.perf_counter", side_effect=[20.0, 20.25]):
            result, elapsed = measure_http_request(operation)
        self.assertEqual(result, (204, {"accepted": True}))
        self.assertEqual(elapsed, 0.25)
        operation.assert_called_once_with()

    def test_sim_027_calculates_sensor_to_web_timestamp_interval(self):
        result = measure_true_sensor_to_web_latency(
            "2026-10-29T09:00:00Z",
            "2026-10-29T09:00:02.500Z",
        )
        self.assertEqual(
            result["measurement_type"],
            "TIMESTAMP_BASED_SENSOR_TO_WEB_INTERVAL",
        )
        self.assertEqual(result["latency_seconds"], 2.5)
        self.assertTrue(result["evidence_required"])
        self.assertNotIn("meets_target", result)

        boundary = measure_true_sensor_to_web_latency(
            "2026-10-29T09:00:00Z",
            "2026-10-29T09:00:03Z",
            observations_are_real=True,
            clocks_comparable=True,
        )
        self.assertTrue(boundary["meets_target"])
        self.assertEqual(boundary["latency_seconds"], 3.0)

        over_target = measure_true_sensor_to_web_latency(
            "2026-10-29T09:00:00Z",
            "2026-10-29T09:00:03.001Z",
            observations_are_real=True,
            clocks_comparable=True,
        )
        self.assertFalse(over_target["meets_target"])

        offset_interval = measure_true_sensor_to_web_latency(
            "2026-10-29T17:00:00+08:00",
            "2026-10-29T09:00:02Z",
        )
        self.assertEqual(offset_interval["latency_seconds"], 2.0)

        with self.assertRaisesRegex(ValueError, "precedes"):
            measure_true_sensor_to_web_latency(
                "2026-10-29T09:00:02Z",
                "2026-10-29T09:00:01Z",
            )
        with self.assertRaisesRegex(ValueError, "must be boolean"):
            measure_true_sensor_to_web_latency(
                "2026-10-29T09:00:00Z",
                "2026-10-29T09:00:01Z",
                observations_are_real="false",
                clocks_comparable=True,
            )

    def test_sim_028_sorts_event_delivery_order_by_space_and_timestamp(self):
        events = load_simulated_events()
        order = event_delivery_order([events[2], events[0], events[1]])
        self.assertEqual(order, [events[0]["event_id"], events[2]["event_id"],
                                 events[1]["event_id"]])

    def test_sim_029_measures_recovery_duration(self):
        self.assertEqual(recovery_duration(10.0, 12.5), 2.5)
        with self.assertRaisesRegex(ValueError, "cannot precede"):
            recovery_duration(12.0, 11.0)

    def test_sim_030_deduplicates_event_ids(self):
        seen = set()
        self.assertTrue(duplicate_event_decision(seen, "SIM-001"))
        self.assertFalse(duplicate_event_decision(seen, "SIM-001"))

    def test_sim_031_validates_http_event_response(self):
        event = make_event()
        validate_http_event_response(202, {"event_id": event["event_id"]}, event)
        with self.assertRaisesRegex(ValueError, "not accepted"):
            validate_http_event_response(500, {}, event)
        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_http_event_response(200, {"event_id": "OTHER"}, event)

    def test_sim_032_validates_web_snapshot_consistency(self):
        validate_web_status(
            {"space_id": "P-01", "availability": "AVAILABLE"},
            "P-01",
            "AVAILABLE",
            space_field="space_id",
            status_field="availability",
        )
        with self.assertRaisesRegex(ValueError, "status"):
            validate_web_status(
                {"parking_space_id": "P-01", "status": "OCCUPIED"},
                "P-01",
                "AVAILABLE",
            )

    def test_sim_033_validates_sqlite_record_using_fixture_schema(self):
        connection = sqlite3.connect(":memory:")
        self.addCleanup(connection.close)
        connection.execute(
            "CREATE TABLE fixture_events "
            "(id TEXT, space TEXT, state TEXT, event_time TEXT)"
        )
        event = make_event()
        connection.execute(
            "INSERT INTO fixture_events VALUES (?, ?, ?, ?)",
            (event["event_id"], event["parking_space_id"],
             event["status"], event["timestamp"]),
        )
        adapter = SQLiteRecordAdapter(
            connection,
            "fixture_events",
            {
                "event_id": "id",
                "parking_space_id": "space",
                "status": "state",
                "timestamp": "event_time",
            },
        )
        self.assertEqual(adapter.validate_event_record(event)["event_id"],
                         event["event_id"])
        validate_event_record(adapter.find_event(event["event_id"]), event)

        connection.execute(
            "INSERT INTO fixture_events VALUES (?, ?, ?, ?)",
            (event["event_id"], "P-02", "OCCUPIED", event["timestamp"]),
        )
        with self.assertRaisesRegex(ValueError, "multiple database records"):
            adapter.find_event(event["event_id"])

    def test_sim_034_validates_mqtt_payload_without_broker(self):
        event = make_event()
        payload = json.dumps(event).encode("utf-8")
        self.assertEqual(validate_mqtt_payload(payload), event)
        invalid_payload = json.dumps(dict(event, status="RESERVED"))
        with self.assertRaisesRegex(ValueError, "status must be"):
            validate_mqtt_payload(invalid_payload)

    def test_sim_035_mqtt_adapter_is_disabled_by_default(self):
        with self.assertRaisesRegex(RuntimeError, "disabled"):
            OptionalMqttPublisher().connect()

    def test_sim_036_rejects_unsafe_sql_identifier_configuration(self):
        connection = sqlite3.connect(":memory:")
        self.addCleanup(connection.close)
        with self.assertRaisesRegex(ValueError, "identifiers"):
            SQLiteRecordAdapter(
                connection,
                "events; DROP TABLE events",
                {
                    "event_id": "event_id",
                    "parking_space_id": "parking_space_id",
                    "status": "status",
                    "timestamp": "timestamp",
                },
            )
        with self.assertRaisesRegex(ValueError, "identifiers"):
            SQLiteRecordAdapter(
                connection,
                "events",
                {
                    "event_id": "event_id",
                    "parking_space_id": "space; DROP TABLE events",
                    "status": "status",
                    "timestamp": "timestamp",
                },
            )

    def test_sim_037_http_client_requires_explicit_configuration(self):
        with self.assertRaisesRegex(ValueError, "base URL"):
            HttpJsonClient("REPLACE_WITH_PROJECT_APPROVED_BASE_URL")
        client = HttpJsonClient("http://127.0.0.1:8080")
        with self.assertRaisesRegex(ValueError, "positive"):
            HttpJsonClient("http://127.0.0.1:8080", timeout_seconds=0)
        with self.assertRaisesRegex(ValueError, "HTTP path"):
            client.get_json("REPLACE_WITH_PROJECT_APPROVED_PATH")

    def test_sim_038_http_client_uses_configured_url_and_parses_json(self):
        class FakeResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self):
                return b'{"ok": true}'

        with patch("integration_adapters.urlopen", return_value=FakeResponse()) as open_url:
            client = HttpJsonClient("http://127.0.0.1:8080")
            status, body = client.get_json("/configured/test-path")

        self.assertEqual(status, 200)
        self.assertEqual(body, {"ok": True})
        self.assertEqual(
            open_url.call_args.args[0].full_url,
            "http://127.0.0.1:8080/configured/test-path",
        )
        open_url.assert_called_once()


if __name__ == "__main__":
    unittest.main()
