"""Unit contracts and real TCP MQTT tests. No physical-device claims."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
import uuid
from urllib.request import urlopen
from http.server import ThreadingHTTPServer

from transport import HERE, CAPTURE, Journal, Publisher, ReceivedState, Subscriber, load_capture
from dashboard_server import mqtt_handler
from simulation_validator import ParkingEventValidator

EVIDENCE = Path(os.environ.get('MQTT_TEST_EVIDENCE', tempfile.mkdtemp(prefix='parking-mqtt-')))
EVIDENCE.mkdir(parents=True, exist_ok=True)
EVENTS = [r['source_payload'] for r in load_capture(CAPTURE.read_text(encoding='utf-8-sig'))['records']]


def wait_for(predicate, timeout=7):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.02)
    raise AssertionError('Timed out waiting for observable MQTT state')


def raw(event):
    return json.dumps(event, separators=(',', ':')).encode()


class Broker:
    def __init__(self, name):
        self.name, self.process, self.port = name, None, 0

    def start(self):
        self.log = EVIDENCE / f'{self.name}-{uuid.uuid4().hex[:6]}.jsonl'
        self.console = self.log.with_suffix('.console.txt').open('w', encoding='utf-8')
        self.process = subprocess.Popen(['node', str(HERE / 'broker.mjs'), str(self.port), str(self.log)],
                                        stdout=self.console, stderr=subprocess.STDOUT)
        def ready():
            if self.process.poll() is not None:
                raise AssertionError('Broker exited; see ' + str(self.log.with_suffix('.console.txt')))
            if not self.log.exists():
                return False
            records = [json.loads(line) for line in self.log.read_text(encoding='utf-8').splitlines()]
            listening = next((r for r in records if r['event'] == 'listening'), None)
            if listening:
                self.port = listening['port']
                return True
            return False
        wait_for(ready)
        return self

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=5)
        if hasattr(self, 'console'):
            self.console.close()


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.state = ReceivedState(Journal(EVIDENCE / (self._testMethodName + '.jsonl')))
        self.state.connection(True)

    def test_initial_unknown(self):
        self.assertTrue(all(not s['online'] for s in self.state.snapshot()['spaces']))

    def test_strict_malformed_rejection(self):
        bad = [b'{bad', b'[]', b'{}', b'\xff', b'{"spot_id":1001,"spot_id":1001}',
               raw(dict(EVENTS[0], occupied=0)), raw(dict(EVENTS[0], status=1)),
               raw(dict(EVENTS[0], spot_id=9999)), raw(dict(EVENTS[0], ctr=256)), b' ' * 4097]
        for value in bad:
            with self.subTest(value=value[:40]):
                self.assertEqual(self.state.receive(value), 'rejected')
        self.assertEqual(self.state.accepted, 0)

    def test_all_capture_fields_and_transitions(self):
        for event in EVENTS:
            self.assertEqual(self.state.receive(raw(event)), 'accepted')
            space = self.state.snapshot()['spaces'][0]
            self.assertEqual((space['id'], space['spotId']), ('A01', 1001))
            for field in ('occupied','ctr','heartbeat','batt_mv','status'):
                self.assertEqual(space[field], event[field])
        self.assertEqual(self.state.accepted, 22)
        self.assertTrue(all(not s['online'] for s in self.state.snapshot()['spaces'][1:]))

    def test_duplicate_ignored(self):
        self.state.receive(raw(EVENTS[0]))
        self.assertEqual(self.state.receive(raw(EVENTS[0])), 'duplicate')
        self.assertEqual((self.state.accepted,self.state.duplicates), (1,1))

    def test_gap_reorder_rejected_then_missing_event_recovers(self):
        self.state.receive(raw(EVENTS[0]))
        self.assertEqual(self.state.receive(raw(EVENTS[2])), 'rejected')
        self.assertEqual(self.state.receive(raw(EVENTS[1])), 'accepted')
        self.assertEqual(self.state.receive(raw(EVENTS[0])), 'rejected')
        self.assertEqual(self.state.previous['ctr'],1)

    def test_heartbeat_cannot_change_occupancy(self):
        self.state.receive(raw(EVENTS[0]))
        self.assertEqual(self.state.receive(raw(dict(EVENTS[1], occupied=True, status=1))), 'rejected')

    def test_task2_conversion_is_receipt_not_source_identity(self):
        self.state.receive(raw(EVENTS[0]))
        conversion = self.state.bays[1001]['normalized']
        self.assertEqual(conversion['parking_space_id'], '1001')
        self.assertEqual(conversion['bay_label'], 'A01')
        self.assertEqual(conversion['timestamp_basis'], 'subscriber_received_at')
        validator = ParkingEventValidator()
        self.assertEqual(validator.validate_event(conversion).isoformat(), conversion['timestamp'])

    def test_counter_rollover_fixture(self):
        for ctr in (255, 0):
            self.assertEqual(self.state.receive(raw(dict(EVENTS[0],ctr=ctr))), 'accepted')

    def test_global_counter_across_spot_id_change(self):
        self.state.receive(raw(EVENTS[0]))
        self.assertEqual(self.state.receive(raw(dict(EVENTS[1],spot_id=1002))), 'accepted')
        self.assertTrue(self.state.snapshot()['spaces'][1]['online'])

    def test_low_battery_source_specific_status_bits(self):
        self.assertEqual(self.state.receive(raw(dict(EVENTS[0],batt_mv=3100,status=4))), 'accepted')
        self.assertEqual(self.state.receive(raw(dict(EVENTS[1],batt_mv=3099,status=0))), 'rejected')

    def test_disconnect_reconnect_requires_new_receipt(self):
        self.state.receive(raw(EVENTS[0]))
        self.state.connection(False)
        self.assertFalse(self.state.snapshot()['spaces'][0]['online'])
        self.state.connection(True)
        self.assertFalse(self.state.snapshot()['spaces'][0]['online'])
        self.assertEqual(self.state.receive(raw(EVENTS[0])), 'duplicate')
        self.assertFalse(self.state.snapshot()['spaces'][0]['online'])
        self.state.receive(raw(EVENTS[1]))
        self.assertTrue(self.state.snapshot()['spaces'][0]['online'])

    def test_retained_and_wrong_qos_rejected(self):
        self.assertEqual(self.state.receive(raw(EVENTS[0]),retained=True), 'rejected')
        self.assertEqual(self.state.receive(raw(EVENTS[0]),qos=0), 'rejected')


class RealMqttTests(unittest.TestCase):
    def setUp(self):
        self.broker = Broker(self._testMethodName).start()
        self.addCleanup(self.broker.stop)
        self.state = ReceivedState(Journal(EVIDENCE / (self._testMethodName + '-subscriber.jsonl')))
        self.topic = 'smart-parking/integration-test/tests/' + uuid.uuid4().hex
        self.subscriber = Subscriber(self.state, self.broker.port, self.topic)
        self.addCleanup(self.subscriber.stop)
        self.assertTrue(self.subscriber.start(), 'Actual CONNACK and SUBACK required')
        self.publisher = Publisher(self.broker.port, self.topic,
                                   Journal(EVIDENCE / (self._testMethodName + '-publisher.jsonl')))
        self.addCleanup(self.publisher.stop)
        self.publisher.start()

    def test_real_connect_subscribe_publish_all_22(self):
        for index, event in enumerate(EVENTS):
            self.publisher.publish(raw(event))
            wait_for(lambda:self.state.accepted == index+1)
            self.assertEqual(self.state.snapshot()['spaces'][0]['occupied'],event['occupied'])
        self.assertEqual(self.state.received,22)
        self.assertEqual(self.state.previous['ctr'],21)
        self.assertEqual((self.state.duplicates,self.state.rejected),(0,0))

    def test_real_duplicate_malformed_gap_and_recovery(self):
        for value in (raw(EVENTS[0]), raw(EVENTS[0]), b'{broken', raw(EVENTS[2]), raw(EVENTS[1])):
            self.publisher.publish(value)
        wait_for(lambda:self.state.received == 5)
        self.assertEqual((self.state.accepted,self.state.duplicates,self.state.rejected),(2,1,2))
        self.assertEqual(self.state.previous['ctr'],1)

    def test_real_topic_isolation(self):
        other = Publisher(self.broker.port, self.topic+'/other')
        try:
            other.start(); other.publish(raw(EVENTS[0]))
            self.publisher.publish(raw(EVENTS[0]))
            wait_for(lambda:self.state.received==1)
            self.assertEqual(self.state.accepted,1)
        finally:
            other.stop()

    def test_real_broker_disconnect_automatic_reconnect(self):
        self.publisher.publish(raw(EVENTS[0]))
        wait_for(lambda:self.state.accepted==1)
        self.publisher.stop()
        self.broker.stop()
        wait_for(lambda:not self.state.connected)
        self.assertFalse(self.state.snapshot()['spaces'][0]['online'])
        self.broker.start()
        wait_for(lambda:self.subscriber.ready.is_set() and self.state.generation==2,timeout=10)
        self.assertFalse(self.state.snapshot()['spaces'][0]['online'])
        replacement=Publisher(self.broker.port,self.topic)
        try:
            replacement.start(); replacement.publish(raw(EVENTS[1]))
            wait_for(lambda:self.state.accepted==2)
            self.assertTrue(self.state.snapshot()['spaces'][0]['online'])
        finally:
            replacement.stop()

    def test_real_mqtt_to_http_snapshot_and_frontend_assets(self):
        http=ThreadingHTTPServer(('127.0.0.1',0),mqtt_handler(self.state))
        thread=threading.Thread(target=http.serve_forever,daemon=True); thread.start()
        try:
            self.publisher.publish(raw(EVENTS[0])); wait_for(lambda:self.state.accepted==1)
            url=f'http://127.0.0.1:{http.server_port}'
            with urlopen(url+'/api/mqtt') as response:
                data=json.load(response)
            self.assertEqual(data['spaces'][0]['ctr'],0)
            self.assertEqual(data['mode'],'MQTT_CAPTURE_TRANSPORT')
            for route in ('/mqtt/','/mqtt.js','/base.js','/','/simulation/'):
                with urlopen(url+route) as response:
                    self.assertEqual(response.status,200)
        finally:
            http.shutdown(); http.server_close(); thread.join()

    def test_real_subscriber_restart_has_no_persistent_state(self):
        self.publisher.publish(raw(EVENTS[0])); wait_for(lambda:self.state.accepted==1)
        self.subscriber.stop()
        replacement_state=ReceivedState()
        replacement=Subscriber(replacement_state,self.broker.port,self.topic)
        try:
            self.assertTrue(replacement.start())
            self.assertEqual(replacement_state.accepted,0)
            self.assertTrue(all(not s['online'] for s in replacement_state.snapshot()['spaces']))
            self.publisher.publish(raw(EVENTS[1])); wait_for(lambda:replacement_state.accepted==1)
        finally:
            replacement.stop()


if __name__ == '__main__':
    unittest.main(verbosity=2)
