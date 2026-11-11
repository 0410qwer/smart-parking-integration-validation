import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen
from http.server import ThreadingHTTPServer

from server import CAPTURE, FRONTEND, handler_for, load_capture, snapshot


class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = CAPTURE.read_text(encoding='utf-8-sig')
        cls.report = load_capture(cls.text)

    def test_actual_capture_json(self):
        self.assertEqual(len(self.report['records']), 22)
        self.assertEqual(sum(r['source_payload']['heartbeat'] for r in self.report['records']), 19)

    def test_mapping(self):
        self.assertEqual([(s['spotId'], s['id']) for s in snapshot(self.report, 1)['spaces']],
                         [(1001, 'A01'), (1002, 'A02'), (1003, 'A03')])

    def test_initial_unknown(self):
        self.assertTrue(all(not s['online'] for s in snapshot(self.report, 0)['spaces']))

    def test_uncaptured_bays_unknown(self):
        self.assertTrue(all(not s['online'] for s in snapshot(self.report, 22)['spaces'][1:]))

    def test_transitions(self):
        self.assertEqual([snapshot(self.report, n)['spaces'][0]['occupied'] for n in (1, 5, 13, 21)],
                         [False, True, False, True])

    def test_heartbeat_counter(self):
        a, b = [snapshot(self.report, n)['spaces'][0] for n in (5, 6)]
        self.assertEqual(a['occupied'], b['occupied'])
        self.assertTrue(b['heartbeat'])
        self.assertEqual((a['ctr'], b['ctr']), (4, 5))

    def test_completion_not_offline(self):
        state = snapshot(self.report, 22)
        self.assertTrue(state['spaces'][0]['online'])
        self.assertEqual(state['connectivity'], 'NOT_ASSESSED')
        self.assertIsNone(state['spaces'][0]['lastUpdate'])

    def test_invalid_count(self):
        for value in (-1, 23, True, 1.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                snapshot(self.report, value)

    def test_malformed_json(self):
        with self.assertRaises(ValueError):
            load_capture('{"spot_id":')

    def test_invalid_types_and_missing_fields(self):
        for event in ('{"spot_id":1001}', self.text.replace('"occupied":false', '"occupied":0', 1)):
            with self.subTest(event=event[:30]), self.assertRaises(ValueError):
                load_capture(event)

    def test_duplicate_json_key(self):
        with self.assertRaises(ValueError):
            load_capture(self.text.replace('"ctr":0', '"ctr":0,"ctr":0', 1))

    def test_unmapped_id(self):
        with self.assertRaisesRegex(ValueError, 'Unmapped'):
            load_capture(self.text.replace('1001', '9001'))

    def test_counter_gap(self):
        with self.assertRaises(ValueError):
            load_capture(self.text.replace('"ctr":1,', '"ctr":9,', 1))

    def test_counter_rollover(self):
        lines = []
        for ctr in (255, 0):
            lines.append(json.dumps(dict(spot_id=1001, occupied=False, batt_mv=3500,
                                        status=0, ctr=ctr, heartbeat=True)))
        self.assertEqual(snapshot(load_capture('\n'.join(lines)), 2)['spaces'][0]['ctr'], 0)

    def test_boot_counter_reset(self):
        event = json.dumps(dict(spot_id=1001, occupied=False, batt_mv=3500, status=0, ctr=0, heartbeat=True))
        report = load_capture(event + '\n[BOOT] Parking Node Simulator starting...\n' + event)
        self.assertEqual(len(report['records']), 2)

    def test_http_integration(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(self.report))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            for count, occupied in ((1, False), (5, True), (13, False), (22, True)):
                with urlopen(f'{base}/api/replay?count={count}') as response:
                    self.assertEqual(json.load(response)['spaces'][0]['occupied'], occupied)
            with urlopen(base) as response:
                html = response.read().decode()
                self.assertIn('Captured Wokwi replay', html)
                self.assertIn('integration.js', html)
            for route in ('/base.js', '/integration.js', '/style.css', '/simulation/', '/simulation/app.js'):
                with urlopen(base + route) as response:
                    self.assertEqual(response.status, 200)
            with urlopen(base + '/base.js') as response:
                self.assertNotIn('setInterval', response.read().decode())
            with urlopen(base + '/simulation/') as response:
                self.assertIn('Simulation Mode', response.read().decode())
            for route in ('/api/replay?count=-1', '/api/replay?count=bad', '/api/replay?count=23', '/missing'):
                with self.assertRaises(HTTPError):
                    urlopen(base + route)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main(verbosity=2)
