import json
import os
from pathlib import Path
import sqlite3
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.request import urlopen
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'mqtt'))
from test_transport import Broker,wait_for,EVENTS,raw
from transport import Publisher,TOPIC
from live_backend import LiveState,LiveSubscriber,live_handler,HEALTH_TOPIC
from mqtt_worker import validate_line
from store import PersistentState,DurableSubscriber
OUTPUT=Path(os.environ['LIVE_TEST_EVIDENCE'])

class LiveContractTests(unittest.TestCase):
    def test_foreign_database_refusal_does_not_modify_its_journal(self):
        path=OUTPUT/'foreign-database.sqlite3'
        db=sqlite3.connect(path);db.execute('CREATE TABLE teammate_data(value TEXT)');db.execute("INSERT INTO teammate_data VALUES ('preserve')");db.commit()
        before=db.execute('PRAGMA journal_mode').fetchone()[0];db.close()
        with self.assertRaises(ValueError):PersistentState(path)
        db=sqlite3.connect(path)
        try:
            self.assertEqual(db.execute('PRAGMA journal_mode').fetchone()[0],before)
            self.assertEqual(db.execute('SELECT value FROM teammate_data').fetchone()[0],'preserve')
        finally:db.close()

    def test_optional_journal_failure_does_not_undo_database_receipt(self):
        def broken_log(*args,**kwargs):raise OSError('injected evidence journal failure')
        state=PersistentState(OUTPUT/'journal-failure.sqlite3',journal=broken_log)
        self.assertEqual(state.receive(raw(EVENTS[0])),'accepted')
        self.assertEqual(state.snapshot()['accepted'],1)
        self.assertIn('injected',state.health()['journal_warning'])

    def test_subscriber_ack_follows_commit_even_if_optional_journal_fails(self):
        from types import SimpleNamespace
        def broken_log(*args,**kwargs):raise OSError('injected optional log failure')
        state=PersistentState(OUTPUT/'journal-ack.sqlite3',journal=broken_log)
        subscriber=DurableSubscriber(state);acks=[]
        def ack(mid,qos):
            self.assertEqual(state.snapshot()['accepted'],1);acks.append((mid,qos));return 0
        message=SimpleNamespace(payload=raw(EVENTS[0]),topic=TOPIC,qos=1,retain=False,dup=False,mid=11)
        subscriber.on_message(SimpleNamespace(ack=ack),None,message)
        self.assertEqual(acks,[(11,1)])

    def test_worker_strict_validation(self):
        self.assertEqual(validate_line(raw(EVENTS[0]).decode()),EVENTS[0])
        for text in ('{bad','[]','{}',raw(dict(EVENTS[0],occupied=0)).decode(),raw(dict(EVENTS[0],spot_id=9)).decode()):
            with self.assertRaises(ValueError):validate_line(text)

    def test_live_health_does_not_fabricate_unknown_bays(self):
        state=LiveState(OUTPUT/'unknown.sqlite3');state.connection(True);state.bridge_health(b'{"state":"streaming"}')
        self.assertTrue(all(s['occupied'] is None for s in state.snapshot()['spaces']))
        self.assertFalse(state.snapshot()['replay'])

    def test_untrusted_or_stale_health_keeps_last_known_not_fresh(self):
        state=LiveState(OUTPUT/'health.sqlite3');state.connection(True);state.receive(raw(EVENTS[0]))
        state.bridge_health(b'{"state":"streaming"}');self.assertTrue(state.snapshot()['spaces'][0]['fresh_this_connection'])
        state.bridge_health(b'{"state":"sensor_untrusted"}');self.assertFalse(state.snapshot()['spaces'][0]['fresh_this_connection'])
        self.assertEqual(state.snapshot()['spaces'][0]['status'],'available')
        state.bridge_seen-=11;self.assertEqual(state.snapshot()['bridge']['state'],'health_stale')

    def test_health_malformed_payload_rejected(self):
        state=LiveState(OUTPUT/'health-malformed.sqlite3')
        for payload in (b'{bad',b'{"state":"invented"}',b'{"state":"streaming","x":1}'):
            with self.assertRaises(ValueError):state.bridge_health(payload)

class LiveMqttTests(unittest.TestCase):
    def setUp(self):
        self.broker=Broker(self._testMethodName).start();self.addCleanup(self.broker.stop)
        self.path=OUTPUT/(self._testMethodName+'.sqlite3')
        self.state=LiveState(self.path)
        self.sub=LiveSubscriber(self.state,self.broker.port);self.addCleanup(self.sub.stop);self.assertTrue(self.sub.start())
        self.pub=Publisher(self.broker.port);self.addCleanup(self.pub.stop);self.pub.start()

    def health(self,state):
        info=self.pub.client.publish(HEALTH_TOPIC,json.dumps(dict(state=state)),qos=1,retain=False);info.wait_for_publish(timeout=5)
        wait_for(lambda:self.state.bridge_state==state)

    def test_actual_mqtt_health_and_state_topic_separation(self):
        self.health('streaming');self.pub.publish(raw(EVENTS[0]));wait_for(lambda:self.state.snapshot()['accepted']==1)
        self.health('offline');self.assertEqual(self.state.snapshot()['accepted'],1)
        self.assertFalse(self.state.snapshot()['spaces'][0]['fresh_this_connection'])
        self.assertEqual(len(self.state.history()['records']),1)

    def test_order_duplicate_counter_malformed_heartbeat_and_recovery(self):
        self.health('streaming')
        for payload in (raw(EVENTS[0]),raw(EVENTS[0]),raw(dict(EVENTS[0],batt_mv=3500)),b'{bad',raw(EVENTS[2]),raw(EVENTS[1])):
            self.pub.publish(payload)
        wait_for(lambda:self.state.snapshot()['received']==6)
        data=self.state.snapshot();self.assertEqual((data['accepted'],data['duplicates'],data['rejected']),(2,1,3))
        self.assertEqual([r['ctr'] for r in self.state.history()['records']],[0,1])

    def test_actual_broker_reconnect_and_persistence(self):
        self.health('streaming');self.pub.publish(raw(EVENTS[0]));wait_for(lambda:self.state.snapshot()['accepted']==1)
        self.pub.stop();self.broker.stop();wait_for(lambda:not self.state.connected)
        self.assertEqual(self.state.snapshot()['bridge']['state'],'broker_disconnected')
        self.broker.start();wait_for(lambda:self.sub.ready.is_set(),timeout=10)
        replacement=Publisher(self.broker.port)
        try:
            replacement.start();replacement.publish(raw(EVENTS[1]));wait_for(lambda:self.state.snapshot()['accepted']==2)
        finally:replacement.stop()
        reopened=LiveState(self.path);self.assertEqual(reopened.snapshot()['accepted'],2)
        self.assertFalse(reopened.snapshot()['spaces'][0]['fresh_this_connection'])

    def test_live_api_labels_and_unknown_state(self):
        http=ThreadingHTTPServer(('127.0.0.1',0),live_handler(self.state));thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        try:
            with urlopen(f'http://127.0.0.1:{http.server_port}/api/availability') as r:data=json.load(r)
            self.assertEqual(data['input_mode'],'LIVE_WOKWI_SERIAL_BRIDGE');self.assertEqual(data['accepted'],0)
            with urlopen(f'http://127.0.0.1:{http.server_port}/backend/') as r:html=r.read().decode()
            self.assertIn('live Wokwi Serial bridge',html);self.assertNotIn('captured MQTT events',html)
        finally:http.shutdown();http.server_close();thread.join()
