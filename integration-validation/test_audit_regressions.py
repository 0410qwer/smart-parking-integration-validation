import io
import tempfile
import unittest
from pathlib import Path

from evidence_utils import archive_existing
from firmware_state_model import OccupancyModel
from integration_adapters import validate_event_record
from run_simulation_tests import JsonReportResult, build_summary


class AuditRegressionTests(unittest.TestCase):
    def test_missing_database_fields_cannot_match(self):
        with self.assertRaises(ValueError):
            validate_event_record({}, {})

    def test_failed_subtests_appear_in_report(self):
        class Example(unittest.TestCase):
            def runTest(self):
                with self.subTest(case='bad'):
                    self.assertEqual(1, 2)
        result = unittest.TextTestRunner(stream=io.StringIO(), resultclass=JsonReportResult).run(Example())
        self.assertEqual(build_summary(result)['failed'], 1)
        self.assertEqual(result.case_results[0]['outcome'], 'FAIL')
        self.assertIn('bad', result.case_results[0]['details'])
        class Mixed(unittest.TestCase):
            def runTest(self):
                with self.subTest(case='error'):
                    raise ValueError('injected subtest error')
                self.fail('outer failure')
        mixed = unittest.TextTestRunner(stream=io.StringIO(), resultclass=JsonReportResult).run(Mixed())
        self.assertEqual(len(mixed.case_results), 1)
        self.assertEqual(build_summary(mixed)['errors'], 1)
        self.assertIn('outer failure', mixed.case_results[0]['details'])

    def test_report_history_retains_original_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'report.json'
            path.write_bytes(b'{"old":true}\r\n')
            archive = archive_existing([path])
            path.write_text('{}', encoding='utf-8')
            self.assertEqual((archive / path.name).read_bytes(), b'{"old":true}\r\n')



class SourceDerivedModelTests(unittest.TestCase):
    def test_provisional_confirmation_boundaries(self):
        model = OccupancyModel()
        self.assertIsNone(model.step(100, 80, 90))
        self.assertEqual(model.state, 'PROV_OCC')
        self.assertFalse(model.occupied)
        self.assertIsNone(model.step(1599, 80, 90))
        self.assertIs(model.step(1600, 80, 90), True)
        self.assertIsNone(model.step(2000, 10, 350))
        self.assertEqual(model.state, 'PROV_FREE')
        self.assertTrue(model.occupied)
        self.assertIsNone(model.step(4499, 10, 350))
        self.assertIs(model.step(4500, 10, 350), False)

    def test_interrupted_confirmation_restarts_timer(self):
        model = OccupancyModel()
        model.step(0, 80, 90)
        model.step(1400, 10, 350)
        self.assertEqual(model.state, 'FREE')
        model.step(1500, 80, 90)
        self.assertIsNone(model.step(2999, 80, 90))
        self.assertIs(model.step(3000, 80, 90), True)
        model.step(4000, 10, 350)
        model.step(6400, 80, 90)
        self.assertEqual(model.state, 'OCCUPIED')

    def test_strict_thresholds_and_repeated_state(self):
        for mag, distance in ((60, 90), (80, 120), (10, 90), (80, 350)):
            model = OccupancyModel()
            model.step(0, mag, distance)
            self.assertEqual(model.state, 'FREE')
        model = OccupancyModel()
        model.step(0, 80, 90)
        model.step(1500, 80, 90)
        for mag, distance in ((25, 350), (10, 220), (80, 90)):
            self.assertIsNone(model.step(5000, mag, distance))
            self.assertEqual(model.state, 'OCCUPIED')

    def test_unsigned_millis_rollover(self):
        model = OccupancyModel()
        model.step(0xFFFFFF00, 80, 90)
        self.assertIsNone(model.step((0xFFFFFF00 + 1499) & 0xFFFFFFFF, 80, 90))
        self.assertIs(model.step((0xFFFFFF00 + 1500) & 0xFFFFFFFF, 80, 90), True)
