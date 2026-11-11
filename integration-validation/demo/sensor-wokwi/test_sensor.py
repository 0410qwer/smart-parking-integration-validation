import json
import os
from pathlib import Path
import sqlite3
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import urlopen
from capture_adapter import HERE,validate_sensor_capture
sys.path.insert(0,str(HERE.parent/'backend'))
sys.path.insert(0,str(HERE.parent/'mqtt'))
from store import PersistentState,DurableSubscriber
from backend_server import backend_handler
from transport import Publisher,Journal
from test_transport import Broker,wait_for

ROOT=HERE.parent/'evidence'
CAPTURE=ROOT/'sensor-wokwi-capture-2026-11-11T13-43-58-176Z'
TIMEOUT=ROOT/'sensor-wokwi-timeout-2026-11-11T13-40-00-359Z'
NETWORK=ROOT/'sensor-wokwi-network-2026-11-11T13-38-36-024Z'
OUTPUT=Path(os.environ['SENSOR_TEST_EVIDENCE'])

class SensorEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text=(CAPTURE/'serial_actual.txt').read_text()
        cls.report=validate_sensor_capture(cls.text)
        (OUTPUT/'capture_validation.json').write_text(json.dumps(cls.report,indent=2))

    def test_actual_capture_fields_and_counter(self):
        records=self.report['records']
        self.assertEqual(len(records),7)
        self.assertEqual([r['source_payload']['ctr'] for r in records],list(range(7)))
        self.assertFalse(any(c['result']=='FAIL' for c in self.report['checks']))

    def test_actual_wokwi_transitions_and_no_magnetic_fusion(self):
        events=[r['source_payload'] for r in self.report['records']]
        states=[events[0]['occupied']]+[e['occupied'] for e in events if not e['heartbeat']]
        self.assertEqual(states,[False,True,False,True,False])
        sketch=(HERE/'firmware/sketch.ino').read_text()
        self.assertNotIn('mockMagDelta',sketch)
        self.assertNotIn('mockToFmm',sketch)

    def test_actual_echo_values_vary_with_virtual_control(self):
        result=json.loads((CAPTURE/'result.json').read_text())
        self.assertEqual([a['distance_cm'] for a in result['actions']],[10,17,35,9,35,400])
        samples=self.report['samples']
        for low,high in ((90,110),(160,180),(340,365),(3400,3650),(4000,4100)):
            self.assertTrue(any(s['valid'] and low<=s['distance_mm']<=high for s in samples))

    def test_observed_debounce_before_each_transition(self):
        samples=[];verified=0
        for line in self.text.splitlines():
            if line.startswith('[SENSOR]'):
                import re
                values=list(map(int,re.findall(r'=(\d+)',line)))
                samples.append(dict(zip(('t','echo','mm','valid','known','trusted','occupied','fault'),values)))
            if line.startswith('{'):
                event=json.loads(line)
                if event['heartbeat']:continue
                target=lambda s:s['valid'] and (s['mm']<=120 if event['occupied'] else s['mm']>=220)
                recent=[]
                for sample in reversed(samples):
                    if not target(sample):break
                    recent.append(sample)
                self.assertTrue(recent)
                self.assertGreaterEqual(recent[0]['t']-recent[-1]['t'],1500 if event['occupied'] else 2500)
                verified+=1
        self.assertEqual(verified,4)

    def test_real_wokwi_disconnected_echo_timeout_no_occupancy_claim(self):
        text=(TIMEOUT/'serial_actual.txt').read_text()
        self.assertIn('echo_us=0 distance_mm=0 valid=0 known=0 trusted=0 occupied=0 fault=1',text)
        self.assertFalse(any(line.startswith('{') for line in text.splitlines()))

    def test_actual_public_gateway_local_connection_failed(self):
        text=(NETWORK/'serial_actual.txt').read_text()
        self.assertIn('wifi_ip=10.10.0.2',text)
        self.assertIn('tcp_connected=0',text)
        self.assertIn('no MQTT packets transmitted',text)

    def test_malformed_capture_measurements_and_json_rejected(self):
        for bad in (self.text.replace('distance_mm=3549','distance_mm=1',1),
                    self.text.replace('"occupied":false','"occupied":0',1),
                    self.text.replace('"ctr":1','"ctr":9',1),'{bad'):
            with self.assertRaises(ValueError):validate_sensor_capture(bad)

    def test_original_firmware_and_capture_preserved(self):
        import hashlib
        workspace=HERE.parents[2]
        for rel,sha in {'wokwi-source/sketch.ino':'b57e51aeb6a996b5cdb198f839addd116136a3f0ffd8c30b13846f6e7f68b918',
                        'wokwi-source/diagram.json':'d0ba612ce3d49a565ff82fcbb0e4550d6e7062f85c5ee856a4df616b9e38e7a6',
                        'integration-validation/captures/wokwi_serial_actual.txt':'dbfb098e800fe0d23a91beff2cec781350d23ea013597e625e85e7d73181e5c2'}.items():
            self.assertEqual(hashlib.sha256((workspace/rel).read_bytes()).hexdigest(),sha)

    def test_saved_sensor_capture_real_local_mqtt_to_sqlite_and_api(self):
        broker=Broker('sensor-capture-replay').start();self.addCleanup(broker.stop)
        dbpath=OUTPUT/'sensor-capture-replay.sqlite3'
        state=PersistentState(dbpath,'ultrasonic-capture-1',journal=Journal(OUTPUT/'subscriber.jsonl'))
        sub=DurableSubscriber(state,broker.port);self.addCleanup(sub.stop);self.assertTrue(sub.start())
        pub=Publisher(broker.port,journal=Journal(OUTPUT/'publisher.jsonl'));self.addCleanup(pub.stop);pub.start()
        for record in self.report['records']:pub.publish(record['raw_line'].strip().encode())
        wait_for(lambda:state.snapshot()['accepted']==7)
        with sqlite3.connect(dbpath) as db:
            rows=db.execute('SELECT payload_json FROM events ORDER BY ordinal').fetchall()
        self.assertEqual([json.loads(r[0]) for r in rows],[r['source_payload'] for r in self.report['records']])
        http=ThreadingHTTPServer(('127.0.0.1',0),backend_handler(state));thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        try:
            with urlopen(f'http://127.0.0.1:{http.server_port}/api/availability') as response:data=json.load(response)
            self.assertEqual(data['spaces'][0]['status'],'available')
            self.assertEqual(data['spaces'][0]['ctr'],6)
            self.assertTrue(all(s['status']=='unknown' for s in data['spaces'][1:]))
            (OUTPUT/'api_snapshot.json').write_text(json.dumps(data,indent=2))
        finally:http.shutdown();http.server_close();thread.join()
