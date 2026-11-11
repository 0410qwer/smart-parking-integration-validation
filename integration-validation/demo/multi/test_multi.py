import json
import os
from pathlib import Path
import sqlite3
import sys
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import urlopen
from model import MultiState,MultiSubscriber,MAPPING
from outbox import Outbox,Worker
import importlib.util
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('multi_http_tests',HERE/'server.py');web=importlib.util.module_from_spec(spec);spec.loader.exec_module(web)
sys.path.insert(0,str(HERE.parent/'mqtt'))
from test_transport import Broker,wait_for
from transport import mqtt,client_id
OUTPUT=Path(os.environ['MULTI_TEST_EVIDENCE'])

def event(spot=1001,ctr=0,occupied=False,heartbeat=True):
    return dict(spot_id=spot,ctr=ctr,occupied=occupied,heartbeat=heartbeat,status=int(occupied),batt_mv=3600)
def raw(e):return json.dumps(e,separators=(',',':')).encode()

class ModelTests(unittest.TestCase):
    def setUp(self):
        self.folder=OUTPUT/self._testMethodName;self.folder.mkdir()
        self.state=MultiState(self.folder/'parking.sqlite3','test');self.state.connection(True)
    def ingest(self,e,key=None):
        spot=e['spot_id'];return self.state.ingest(spot,raw(e),key or f'{spot}/events/source/{e["ctr"]}',self.state.prefix+f'/{spot}/events/source/{e["ctr"]}')
    def test_unsourced_bays_unknown(self):
        self.assertTrue(all(s['status']=='unknown' and s['occupied'] is None for s in self.state.snapshot()['spaces']))
    def test_performance_nearest_rank_and_failure_denominator(self):
        from performance_tools import distribution
        data=distribution(list(range(1,31)),32)
        self.assertEqual((data['minimum_ms'],data['median_ms'],data['p95_ms'],data['maximum_ms']),(1,15.5,29,30))
        self.assertEqual(data['failed'],2);self.assertEqual(data['failure_rate'],2/32)
        self.assertIsNone(distribution([])['p95_ms'])
    def test_resource_sampling_handles_disappearing_wal_file(self):
        from performance_tools import sampled_file_bytes
        from unittest.mock import Mock
        existing=Mock();existing.stat.return_value.st_size=123
        vanished=Mock();vanished.stat.side_effect=FileNotFoundError('WAL checkpointed')
        self.assertEqual(sampled_file_bytes([existing,vanished]),123)
    def test_invalid_health_types_do_not_mutate_health(self):
        for value in (None,[],True,{'state':'online','pending':True},{'state':'online','echo_us':-1},{'state':'online','observed_at':[]}):
            with self.subTest(value=value),self.assertRaises(ValueError):self.state.signal(1001,value)
        self.assertEqual(self.state.signals,{})
    def test_optional_journal_failure_does_not_interrupt_commit_ack(self):
        from types import SimpleNamespace
        def failed(*args,**kwargs):raise OSError('Injected log disk failure')
        state=MultiState(self.folder/'logfailure.sqlite3','logfailure',journal=failed)
        subscriber=MultiSubscriber(state,1);calls=[]
        client=SimpleNamespace(publish=lambda *a,**k:calls.append('commit_ack'),ack=lambda *a:calls.append('mqtt_ack'))
        message=SimpleNamespace(topic=state.prefix+'/1001/events/src/0',payload=raw(event()),qos=1,retain=False,dup=False,mid=1)
        subscriber.on_message(client,None,message)
        self.assertEqual(calls,['commit_ack','mqtt_ack']);self.assertEqual(state.snapshot()['accepted'],1)
        self.assertIn('Injected',state.snapshot()['journal_warning'])
    def test_optional_outbox_log_failure_does_not_kill_worker(self):
        from unittest.mock import patch
        worker=Worker.__new__(Worker);worker.folder=self.folder;worker.log_lock=threading.Lock()
        with patch('pathlib.Path.open',side_effect=OSError('Injected log failure')):worker.log('example')
        self.assertIn('Injected',worker.journal_warning)
    def test_malformed_commit_ack_cannot_complete_pending_delivery(self):
        from types import SimpleNamespace
        worker=Worker.__new__(Worker);worker.ack_lock=threading.Lock()
        pending=dict(event=threading.Event(),data=None);worker.acks={'key':pending}
        for value in (b'[]',b'null',b'1',b'{bad',b'{"delivery_key":[]}',b'{"delivery_key":"key","outcome":"accepted","event_id":true}',b'{"delivery_key":"key","outcome":"invented"}',b'{"delivery_key":"key","outcome":"rejected"}'):
            worker.ack(None,None,SimpleNamespace(payload=value))
        self.assertFalse(pending['event'].is_set())
        worker.ack(None,None,SimpleNamespace(payload=b'{"delivery_key":"key","outcome":"accepted","event_id":1}'))
        self.assertTrue(pending['event'].is_set())
    def test_failed_suback_does_not_mark_publisher_connected(self):
        from types import SimpleNamespace
        worker=Worker.__new__(Worker);worker.connected=threading.Event()
        worker.on_subscribe(None,None,1,[SimpleNamespace(is_failure=True)],None);self.assertFalse(worker.connected.is_set())
        worker.on_subscribe(None,None,1,[SimpleNamespace(is_failure=False)],None);self.assertTrue(worker.connected.is_set())
    def test_independent_counters_and_states(self):
        for spot in MAPPING:
            self.state.signal(spot,dict(state='online'));self.ingest(event(spot,occupied=spot==1002))
        data=self.state.snapshot();self.assertEqual([s['status'] for s in data['spaces']],['available','occupied','available'])
        self.ingest(event(1001,1,True,False));self.assertEqual([s['ctr'] for s in self.state.snapshot()['spaces']],[1,0,0])
    def test_offline_is_independent_and_last_known_separate(self):
        for spot in MAPPING:self.state.signal(spot,dict(state='online'));self.ingest(event(spot))
        self.state.signal(1002,dict(state='offline'))
        data=self.state.snapshot();self.assertEqual([s['status'] for s in data['spaces']],['available','unknown','available'])
        self.assertEqual(data['spaces'][1]['last_known_status'],'available')
        self.state.signals[1003]['seen']-=9;self.assertEqual(self.state.snapshot()['spaces'][2]['status'],'unknown')
    def test_duplicate_transport_identity_deduplicates_nonadjacent_delivery(self):
        first=self.ingest(event());self.ingest(event(1001,1));again=self.ingest(event())
        self.assertEqual(again['outcome'],'duplicate');self.assertEqual(first['event_id'],again['event_id'])
        self.assertEqual(self.state.snapshot()['accepted'],2)
    def test_identity_collision_and_same_counter_different_payload_rejected(self):
        self.ingest(event())
        changed=event();changed['batt_mv']=3500
        self.assertEqual(self.ingest(changed)['outcome'],'rejected')
        self.assertEqual(self.ingest(changed,'new-key')['outcome'],'rejected')
        self.assertEqual(self.state.snapshot()['accepted'],1)
    def test_malformed_and_topic_mapping_rejected(self):
        result=self.state.ingest(1001,b'{bad','broken',self.state.prefix+'/1001/events/src/1')
        self.assertEqual(result['outcome'],'rejected')
        result=self.state.ingest(1001,raw(event(1002)),'wrong-source',self.state.prefix+'/1001/events/src/2')
        self.assertEqual(result['outcome'],'rejected')
    def test_order_heartbeats_and_wrap_not_global_identity(self):
        for i in range(257):self.assertEqual(self.ingest(event(1001,i%256),f'frame-{i}')['outcome'],'accepted')
        self.assertEqual(self.state.nodes[1001].snapshot()['accepted'],257)
        self.assertEqual(self.ingest(event(1001,3),key='gap')['outcome'],'rejected')
    def test_database_restart_retains_per_source_checkpoint_and_delivery_ids(self):
        self.ingest(event());self.ingest(event(1002,occupied=True))
        reopened=MultiState(self.folder/'parking.sqlite3','test');reopened.connection(True)
        self.assertEqual(reopened.snapshot()['accepted'],2)
        self.assertTrue(all(s['status']=='unknown' for s in reopened.snapshot()['spaces']))
        result=reopened.ingest(1001,raw(event()),'1001/events/source/0',reopened.prefix+'/1001/events/source/0')
        self.assertEqual(result['outcome'],'duplicate')
    def test_atomic_failure_rolls_back_delivery_history_and_checkpoint(self):
        node=self.state.nodes[1001]
        with node.db() as db:db.execute("CREATE TRIGGER fault BEFORE INSERT ON delivery_keys BEGIN SELECT RAISE(ABORT,'fault'); END")
        with self.assertRaises(sqlite3.Error):self.ingest(event())
        self.assertEqual(self.state.snapshot()['accepted'],0)
        self.assertEqual(self.state.history()['records'],[])
    def test_outbox_survives_restart_and_serial_collision_fails(self):
        path=self.folder/'outbox.sqlite3';box=Outbox(path)
        request=dict(raw=raw(event()).decode(),serial_index=0,observed_at=time.time())
        key=box.enqueue(request);self.assertEqual(box.enqueue(request),key)
        reopened=Outbox(path);self.assertEqual(reopened.head(1001)['delivery_key'],key)
        request['raw']=raw(event(1001,1)).decode()
        with self.assertRaises(ValueError):reopened.enqueue(request)
    def test_api_history_bounds_and_security_headers(self):
        http=ThreadingHTTPServer(('127.0.0.1',0),web.handler_for(self.state));thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
        try:
            base=f'http://127.0.0.1:{http.server_port}'
            for route in ('/','/dashboard.js','/dashboard.css','/api/availability','/api/health','/api/events','/api/receipts'):
                with urlopen(base+route) as response:self.assertEqual(response.status,200);self.assertIn("default-src 'self'",response.headers['Content-Security-Policy'])
            for query in ('?spot_id=9','?limit=0','?after=-1','?limit=bad'):
                with self.assertRaises(HTTPError) as error:urlopen(base+'/api/events'+query)
                self.assertEqual(error.exception.code,400)
        finally:http.shutdown();http.server_close();thread.join()

class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.folder=OUTPUT/self._testMethodName;self.folder.mkdir()
        self.broker=Broker(self._testMethodName).start();self.addCleanup(self.broker.stop)
        self.state=MultiState(self.folder/'parking.sqlite3','reliability')
        self.sub=MultiSubscriber(self.state,self.broker.port);self.addCleanup(self.sub.stop);self.assertTrue(self.sub.start())
        self.box=Outbox(self.folder/'outbox.sqlite3');self.worker=Worker(self.broker.port,'reliability',self.box,self.folder);self.addCleanup(self.worker.stop)
        for spot in MAPPING:self.worker.signals[spot]=dict(state='online')
        # The worker starts by advertising untrusted. Await the real subscribed
        # online health, so that an older startup health frame cannot invalidate
        # a subsequently asserted fresh observation. No occupancy assertion is relaxed.
        wait_for(lambda:all(self.state.signals.get(spot,{}).get('state')=='online' for spot in MAPPING))
    def enqueue(self,spot,index,ctr,occupied=False,heartbeat=True):
        return self.box.enqueue(dict(raw=raw(event(spot,ctr,occupied,heartbeat)).decode(),serial_index=index,observed_at=time.time()))
    def test_three_actual_mqtt_channels_and_backend_ack(self):
        for i,spot in enumerate(MAPPING):self.enqueue(spot,i,0,occupied=spot==1002)
        wait_for(lambda:self.state.snapshot()['accepted']==3)
        wait_for(lambda:all(self.box.counts(s).get('delivered')==1 for s in MAPPING))
        self.assertEqual([s['status'] for s in self.state.snapshot()['spaces']],['available','occupied','available'])
    def test_malformed_health_over_real_mqtt_does_not_kill_subscriber(self):
        for payload in (b'[]',b'null',b'{bad',b' '*4097):
            self.worker.client.publish(self.state.prefix+'/1001/health',payload,qos=1).wait_for_publish(timeout=3)
        self.enqueue(1001,0,0);wait_for(lambda:self.box.counts(1001).get('delivered')==1)
        self.assertEqual(self.state.snapshot()['accepted'],1)
    def test_one_paused_source_queues_without_blocking_others_then_recovers(self):
        control=self.folder/'control.json';control.write_text('{"paused_ids":[1002]}');self.worker.read_control()
        for i,spot in enumerate(MAPPING):self.enqueue(spot,i,0)
        wait_for(lambda:self.box.counts(1001).get('delivered')==1 and self.box.counts(1003).get('delivered')==1)
        self.assertEqual(self.box.counts(1002).get('pending'),1)
        control.write_text('{"paused_ids":[]}');self.worker.read_control();wait_for(lambda:self.box.counts(1002).get('delivered')==1)
    def test_broker_disconnect_outbox_retries_and_recovers(self):
        self.enqueue(1001,0,0);wait_for(lambda:self.box.counts(1001).get('delivered')==1)
        self.broker.stop();wait_for(lambda:not self.state.connected)
        self.enqueue(1001,1,1);time.sleep(.3);self.assertEqual(self.box.counts(1001).get('pending'),1)
        self.broker.start();wait_for(lambda:self.box.counts(1001).get('delivered')==2,timeout=15)
        self.assertEqual(self.state.snapshot()['accepted'],2)
    def test_backend_ack_loss_retries_without_duplicate_history(self):
        original=self.sub.client.publish
        self.sub.client.publish=lambda *args,**kwargs:None
        self.enqueue(1001,0,0);wait_for(lambda:self.state.snapshot()['accepted']==1)
        self.assertEqual(self.box.counts(1001).get('pending'),1)
        self.sub.client.publish=original
        wait_for(lambda:self.box.counts(1001).get('delivered')==1,timeout=10)
        self.assertEqual(self.state.snapshot()['accepted'],1);self.assertGreaterEqual(self.state.snapshot()['duplicates'],1)
