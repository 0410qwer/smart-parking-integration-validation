"""Deterministic adapter checks; no observed simulator/hardware evidence."""

import json
import tempfile
import unittest
from pathlib import Path

from validate_wokwi_capture import main
from wokwi_serial_adapter import validate_capture


def event(spot=1001, occupied=False, ctr=0, **extra):
    payload = dict(spot_id=spot, occupied=occupied, ctr=ctr, batt_mv=3600,
                   status=int(occupied) if type(occupied) is bool else 0, heartbeat=True)
    payload.update(extra)
    return json.dumps(payload)


def result(report, name):
    return next(c["result"] for c in report["checks"] if c["check"] == name)


class WokwiAdapterTests(unittest.TestCase):
    def test_valid_fields_preserved(self):
        payload = event(extra="unchanged")
        record = validate_capture(payload)["records"][0]
        self.assertEqual(record["source_payload"], json.loads(payload))
        self.assertEqual(record["normalized"], {"parking_space_id": "1001", "status": "AVAILABLE", "sequence_counter": 0})

    def test_both_states_and_transitions(self):
        report = validate_capture("\n".join(event(occupied=s, ctr=i, heartbeat=(i == 0)) for i, s in enumerate([False, True, False])))
        self.assertEqual([r["normalized"]["status"] for r in report["records"]], ["AVAILABLE", "OCCUPIED", "AVAILABLE"])
        self.assertEqual(report["issues"], [])

    def test_hex_and_noise(self):
        report = validate_capture('HEX: FF 00 {bad}\nbooting\n{"message":"ready"}\n' + event())
        self.assertEqual(len(report["ignored_lines"]), 3)
        self.assertEqual(len(report["records"]), 1)

    def test_prefixed_json(self):
        report = validate_capture("12:00:00.123 -> " + event())
        self.assertEqual(len(report["records"]), 1)
        self.assertNotIn("timestamp", report["records"][0]["normalized"])

    def test_malformed_json(self):
        for payload in ('{"spot_id":', '{"ctr":NaN}', '{"ctr":1,"ctr":2}', '[]'):
            with self.subTest(payload=payload):
                self.assertEqual(result(validate_capture(payload), "json"), "FAIL")

    def test_each_missing_field(self):
        for field in ("spot_id", "occupied", "ctr", "batt_mv", "status", "heartbeat"):
            payload = json.loads(event())
            del payload[field]
            report = validate_capture(json.dumps(payload))
            self.assertTrue(any(i["message"] == "missing field: " + field for i in report["issues"]))

    def test_invalid_field_types_and_values(self):
        for field, values in {"spot_id": [None, True, -1, 4294967296, "1001", ""], "occupied": [0, 1, "false", None], "ctr": [True, 1.5, -1, "1", None]}.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    payload = json.loads(event())
                    payload[field] = value
                    self.assertEqual(result(validate_capture(json.dumps(payload)), "fields"), "FAIL")

    def test_duplicate_kept_with_distinct_local_ids(self):
        report = validate_capture(event() + "\n" + event())
        self.assertEqual(result(report, "duplicates"), "FAIL")
        self.assertEqual(len(report["records"]), 2)
        self.assertNotEqual(*[r["local_record_id"] for r in report["records"]])
        self.assertNotIn("event_id", report["records"][0]["normalized"])

    def test_progression(self):
        report = validate_capture(event(ctr=40) + "\n" + event(ctr=41))
        self.assertEqual(result(report, "sequence"), "PASS")

    def test_gap_repeat_and_decrease(self):
        for ctr in (5, 2, 0):
            self.assertEqual(result(validate_capture(event(ctr=2) + "\n" + event(ctr=ctr, occupied=True)), "sequence"), "FAIL")

    def test_source_rollover_default(self):
        text = event(ctr=255) + "\n" + event(ctr=0)
        self.assertEqual(result(validate_capture(text), "sequence"), "PASS")
        report = validate_capture(text, counter_modulus=256)
        self.assertEqual(result(report, "sequence"), "PASS")
        self.assertEqual(result(report, "counter_rollover"), "PASS")
        self.assertEqual(result(validate_capture(event(ctr=256), counter_modulus=256), "fields"), "FAIL")

    def test_id_changes_share_global_counter(self):
        report = validate_capture("\n".join([event(1001, ctr=10), event(2002, ctr=11), event(1001, ctr=12), event(2002, ctr=13)]))
        self.assertEqual(result(report, "sequence"), "PASS")

    def test_missing_timestamp_and_event_id_not_invented(self):
        report = validate_capture(event())
        self.assertEqual(result(report, "timestamp_ordering"), "NOT ASSESSED")
        self.assertEqual(report["records"][0]["source_identifiers"], {"spot_id": 1001})
        self.assertNotIn("timestamp", report["records"][0]["normalized"])

    def test_optional_metadata_not_interpreted(self):
        report = validate_capture(event(timestamp="not-a-clock", event_id="source-id"))
        self.assertEqual(report["records"][0]["source_identifiers"]["event_id"], "source-id")
        self.assertEqual(report["records"][0]["source_payload"]["timestamp"], "not-a-clock")
        self.assertEqual(result(report, "timestamp_ordering"), "NOT ASSESSED")

    def test_empty_capture_cannot_pass(self):
        self.assertEqual(validate_capture("boot only")["overall_result"], "FAIL")

    def test_invalid_record_does_not_advance_history(self):
        report = validate_capture("\n".join([event(ctr=0), event(ctr=99, occupied="true"), event(ctr=1)]))
        self.assertEqual(result(report, "sequence"), "PASS")
        self.assertEqual(result(report, "fields"), "FAIL")

    def test_configuration_validation(self):
        for modulus in (None, True, 0, 1, 2.5, 65536):
            with self.assertRaises(ValueError):
                validate_capture(event(), counter_modulus=modulus)

    def test_boot_and_cfg_diagnostics(self):
        text = '[BOOT] Parking Node Simulator starting...\n' + event(ctr=0) + '\n[CFG] Spot ID set to 2002\n' + event(2002, ctr=1)
        report = validate_capture(text)
        self.assertEqual(report['issues'], [])
        self.assertEqual(report['boot_markers'], 1)

    def test_boot_resets_counter_and_state(self):
        report = validate_capture(event(occupied=True, ctr=50) + '\n[BOOT] Parking Node Simulator starting...\n' + event(ctr=0))
        self.assertEqual(report['issues'], [])
        self.assertEqual(result(report, 'sequence'), 'NOT ASSESSED')

    def test_status_mask_consistency(self):
        for payload in (event(status=1), event(status=2), event(status=4), event(occupied=True, status=0)):
            self.assertEqual(result(validate_capture(payload), 'status_bits'), 'FAIL')

    def test_low_battery_heartbeat_and_transition_difference(self):
        for battery, status in ((3200, 0), (3199, 4)):
            self.assertEqual(result(validate_capture(event(batt_mv=battery, status=status)), 'status_bits'), 'PASS')
        self.assertEqual(result(validate_capture(event(occupied=True, heartbeat=False, batt_mv=3100, status=1)), 'status_bits'), 'PASS')
        self.assertEqual(result(validate_capture(event(occupied=True, heartbeat=False, batt_mv=3100, status=5)), 'status_bits'), 'FAIL')

    def test_extra_field_ranges(self):
        for field, values in {'batt_mv': [True, -1, 65536, '3600'], 'status': [True, -1, 8, '0'], 'heartbeat': [0, 1, 'true', None]}.items():
            for value in values:
                self.assertEqual(result(validate_capture(event(**{field: value})), 'fields'), 'FAIL')

    def test_uint32_boundaries_and_decimal_mapping(self):
        for space in (0, 4294967295):
            record = validate_capture(event(space))['records'][0]
            self.assertEqual(record['normalized']['parking_space_id'], str(space))
            self.assertEqual(record['source_payload']['spot_id'], space)

    def test_heartbeat_cannot_change_occupancy(self):
        report = validate_capture(event() + '\n' + event(occupied=True, ctr=1))
        self.assertEqual(result(report, 'output_state'), 'FAIL')

    def test_transition_and_same_loop_heartbeat(self):
        report = validate_capture('\n'.join([event(), event(occupied=True, ctr=1, heartbeat=False), event(occupied=True, ctr=2)]))
        self.assertEqual(report['issues'], [])

    def test_full_counter_cycle_is_not_duplicate(self):
        report = validate_capture('\n'.join(event(ctr=i % 256, batt_mv=3000, status=4) for i in range(257)))
        self.assertEqual(report['issues'], [])
        self.assertEqual(result(report, 'counter_rollover'), 'PASS')

    def test_per_space_counter_assumption_rejected(self):
        report = validate_capture(event(1001, ctr=10) + '\n' + event(2002, ctr=0))
        self.assertEqual(result(report, 'sequence'), 'FAIL')

    def test_cli_fixture_label_and_reports(self):
        fixture = Path(__file__).parent / "fixtures" / "wokwi_serial_SAMPLE.txt"
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(main([str(fixture), "--output-dir", folder]), 0)
            report = json.loads((Path(folder) / "wokwi_validation_report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["evidence_kind"], "SAMPLE_FIXTURE")
            self.assertFalse(report["real_system_validated"])
            self.assertIn("NOT ASSESSED", (Path(folder) / "WOKWI_VALIDATION_REPORT.md").read_text(encoding="utf-8"))

    def test_cli_failure_exit(self):
        with tempfile.TemporaryDirectory() as folder:
            capture = Path(folder) / "input.txt"
            capture.write_text(event(occupied="bad"), encoding="utf-8")
            self.assertEqual(main([str(capture), "--output-dir", folder]), 1)

    def test_cli_missing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(SystemExit) as exc:
                main([str(Path(folder) / "missing.txt"), "--output-dir", folder])
            self.assertEqual(exc.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
