"""SQLite contracts, transaction durability, actual MQTT and backend process restarts."""
import json
import os
from pathlib import Path
import queue
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import urlopen
from http.server import ThreadingHTTPServer

from store import HERE, PersistentState, DurableSubscriber, Journal
from backend_server import backend_handler
from transport import CAPTURE, TOPIC, Publisher, load_capture
from test_transport import Broker, wait_for, raw, EVENTS

EVIDENCE=Path(os.environ['BACKEND_TEST_EVIDENCE']) if os.environ.get('BACKEND_TEST_EVIDENCE') else Path(tempfile.mkdtemp(prefix='parking-backend-'))
EVIDENCE.mkdir(parents=True,exist_ok=True)


class BackendProcess:
    def __init__(self, database, mqtt_port, folder, port=0):
        self.database,self.mqtt_port,self.folder,self.port=database,mqtt_port,Path(folder),port
        self.process=None

    def start(self):
        self.folder.mkdir(parents=True,exist_ok=True)
        self.stderr=(self.folder/'http-console.txt').open('a',encoding='utf-8')
        self.process=subprocess.Popen([sys.executable,str(HERE/'backend_server.py'),'--port',str(self.port),
            '--mqtt-port',str(self.mqtt_port),'--db',str(self.database),'--log',str(self.folder/'backend-journal.jsonl')],
            stdout=subprocess.PIPE,stderr=self.stderr,text=True,encoding='utf-8')
        lines=queue.Queue()
        threading.Thread(target=lambda:lines.put(self.process.stdout.readline()),daemon=True).start()
        line=lines.get(timeout=12)
        match=re.search(r'http://127.0.0.1:(\d+)/backend/',line)
        if not match:
            self.stop()
            raise AssertionError('Backend failed: '+line+'; see '+str(self.folder/'http-console.txt'))
        self.port=int(match[1]);self.url=f'http://127.0.0.1:{self.port}'
        with (self.folder/'process-starts.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(dict(pid=self.process.pid,url=self.url,database=str(self.database),ready=line.strip()))+'\n')
        return self

    def stop(self):
        if self.process:
            if self.process.poll() is None:
                self.process.terminate();self.process.wait(timeout=5)
            self.process.stdout.close()
        if hasattr(self,'stderr'):
            self.stderr.close()


def get(url):
    with urlopen(url,timeout=4) as response:
        return json.load(response)


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.folder=EVIDENCE/self._testMethodName;self.folder.mkdir(parents=True,exist_ok=True)
        self.path=self.folder/'parking.sqlite3'
        self.state=PersistentState(self.path)
        self.state.connection(True)

    def test_schema_created_and_uncaptured_unknown(self):
        data=self.state.snapshot()
        self.assertTrue(all(s['status']=='unknown' and s['occupied'] is None for s in data['spaces']))
        with self.state.db() as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],1)
            self.assertEqual(db.execute('PRAGMA journal_mode').fetchone()[0],'wal')

    def test_all_22_exact_payloads_history_and_current_mapping(self):
        records=load_capture(CAPTURE.read_text(encoding='utf-8-sig'))['records']
        for record in records:
            self.assertEqual(self.state.receive(record['raw_line'].strip().encode(),mqtt_dup=False,mqtt_mid=42),'accepted')
        history=self.state.history()['records']
        self.assertEqual([r['payload'] for r in history],EVENTS)
        self.assertEqual([bytes.fromhex(r['raw_payload_hex']).decode() for r in history],[r['raw_line'].strip() for r in records])
        self.assertTrue(all(r['source_timestamp'] is None and r['received_at'] and r['mqtt_mid']==42 for r in history))
        self.assertEqual(sum(r['heartbeat'] for r in history),19)
        data=self.state.snapshot()
        self.assertEqual((data['accepted'],data['spaces'][0]['id'],data['spaces'][0]['ctr']),(22,'A01',21))
        self.assertTrue(all(s['status']=='unknown' for s in data['spaces'][1:]))

    def test_malformed_receipts_persist_without_event(self):
        for value in (b'{bad',b'[]',b'\xff',raw(dict(EVENTS[0],occupied=0)),raw(dict(EVENTS[0],spot_id=9999))):
            self.assertEqual(self.state.receive(value),'rejected')
        self.assertEqual(len(self.state.history(receipts=True)['records']),5)
        self.assertEqual(self.state.history()['records'],[])
        self.assertEqual(self.state.snapshot()['rejected'],5)

    def test_duplicates_are_receipts_not_new_events(self):
        self.state.receive(raw(EVENTS[0]));self.state.receive(raw(EVENTS[0]),mqtt_dup=True,mqtt_mid=7)
        self.assertEqual(len(self.state.history()['records']),1)
        receipts=self.state.history(receipts=True)['records']
        self.assertEqual([r['outcome'] for r in receipts],['accepted','duplicate'])
        self.assertEqual(receipts[0]['event_id'],receipts[1]['event_id'])
        self.assertEqual(receipts[1]['mqtt_dup'],1)

    def test_repeated_heartbeats_have_distinct_history(self):
        self.state.receive(raw(EVENTS[0]));self.state.receive(raw(EVENTS[1]))
        self.assertEqual(len(self.state.history()['records']),2)
        self.assertFalse(self.state.snapshot()['spaces'][0]['occupied'])
        self.assertEqual(self.state.snapshot()['spaces'][0]['ctr'],1)

    def test_gap_reorder_and_missing_record_recovery(self):
        for value,expected in ((EVENTS[0],'accepted'),(EVENTS[2],'rejected'),(EVENTS[1],'accepted'),(EVENTS[0],'rejected')):
            self.assertEqual(self.state.receive(raw(value)),expected)
        self.assertEqual(self.state.snapshot()['accepted'],2)

    def test_rollover_counter_is_not_unique_identity(self):
        for i in range(257):
            self.assertEqual(self.state.receive(raw(dict(EVENTS[0],ctr=i%256))),'accepted')
        with self.state.db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM events WHERE ctr=0').fetchone()[0],2)
            self.assertEqual(db.execute('SELECT COUNT(DISTINCT event_uuid) FROM events').fetchone()[0],257)

    def test_checkpoint_and_duplicate_survive_reopen(self):
        self.state.receive(raw(EVENTS[0]))
        reopened=PersistentState(self.path)
        self.assertEqual(reopened.receive(raw(EVENTS[0])),'duplicate')
        self.assertEqual(reopened.receive(raw(EVENTS[2])),'rejected')
        self.assertEqual(reopened.receive(raw(EVENTS[1])),'accepted')
        self.assertEqual(reopened.snapshot()['accepted'],2)

    def test_restart_retains_last_known_but_not_freshness(self):
        for value in EVENTS[:5]:self.state.receive(raw(value))
        reopened=PersistentState(self.path);reopened.connection(True)
        bay=reopened.snapshot()['spaces'][0]
        self.assertEqual(bay['status'],'occupied')
        self.assertFalse(bay['fresh_this_connection'])
        self.assertEqual(bay['availability_basis'],'LAST_PERSISTED_OBSERVATION')
        reopened.receive(raw(EVENTS[5]));self.assertTrue(reopened.snapshot()['spaces'][0]['fresh_this_connection'])

    def test_reconnect_freshness_requires_accepted_receipt(self):
        self.state.receive(raw(EVENTS[0]));self.state.connection(False);self.state.connection(True)
        self.assertFalse(self.state.snapshot()['spaces'][0]['fresh_this_connection'])
        self.state.receive(raw(EVENTS[0]))
        self.assertFalse(self.state.snapshot()['spaces'][0]['fresh_this_connection'])
        self.state.receive(raw(EVENTS[1]))
        self.assertTrue(self.state.snapshot()['spaces'][0]['fresh_this_connection'])

    def test_streams_isolate_new_capture_sessions(self):
        self.state.receive(raw(EVENTS[0]))
        other=PersistentState(self.path,'capture-2')
        self.assertEqual(other.snapshot()['accepted'],0)
        other.receive(raw(EVENTS[0]))
        self.assertEqual(other.snapshot()['accepted'],1)
        self.assertEqual(self.state.snapshot()['accepted'],1)

    def test_global_counter_and_multiple_bays(self):
        self.state.receive(raw(EVENTS[0]))
        self.state.receive(raw(dict(EVENTS[1],spot_id=1002)))
        spaces=self.state.snapshot()['spaces']
        self.assertEqual([s['status'] for s in spaces],['available','available','unknown'])

    def test_transaction_rollback_prevents_partial_state(self):
        with self.state.db() as db:
            db.execute("CREATE TRIGGER force_fault BEFORE INSERT ON receipts BEGIN SELECT RAISE(ABORT,'injected storage failure'); END")
        with self.assertRaises(sqlite3.Error):self.state.receive(raw(EVENTS[0]))
        with self.state.db() as db:
            for table in ('events','receipts','bay_current'):
                self.assertEqual(db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT accepted FROM streams').fetchone()[0],0)
            db.execute('DROP TRIGGER force_fault')
        self.assertEqual(self.state.receive(raw(EVENTS[0])),'accepted')

    def test_refuses_foreign_database(self):
        foreign=self.folder/'foreign.sqlite3'
        with sqlite3.connect(foreign) as db:db.execute('CREATE TABLE teammate_data(value TEXT)')
        with self.assertRaisesRegex(ValueError,'unrecognized'):PersistentState(foreign)
        with sqlite3.connect(foreign) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM teammate_data').fetchone()[0],0)

    def test_malformed_stream_and_topic_mismatch(self):
        with self.assertRaises(ValueError):PersistentState(self.path,'bad/stream')
        with self.assertRaises(ValueError):PersistentState(self.path,topic=TOPIC+'/other')
        self.assertEqual(self.state.receive(raw(EVENTS[0]),topic=TOPIC+'/other'),'rejected')

    def test_history_pagination_validation(self):
        for event in EVENTS[:3]:self.state.receive(raw(event))
        first=self.state.history(limit=2);second=self.state.history(after=first['next_after'],limit=2)
        self.assertEqual([r['ctr'] for r in first['records']+second['records']],[0,1,2])
        for kwargs in ({'after':-1},{'limit':0},{'limit':101}):
            with self.assertRaises(ValueError):self.state.history(**kwargs)

    def test_raw_payload_and_mqtt_metadata_preserved(self):
        self.state.receive(raw(EVENTS[0]),mqtt_mid=123,mqtt_dup=True)
        row=self.state.history()['records'][0]
        self.assertEqual((row['mqtt_mid'],row['mqtt_dup'],row['qos'],row['retained']),(123,True,1,False))
        self.assertEqual(bytes.fromhex(row['raw_payload_hex']),raw(EVENTS[0]))

    def test_retained_qos_status_and_oversized_rejected(self):
        self.assertEqual(self.state.receive(raw(EVENTS[0]),retained=True),'rejected')
        self.assertEqual(self.state.receive(raw(EVENTS[0]),qos=0),'rejected')
        self.assertEqual(self.state.receive(raw(dict(EVENTS[0],status=1))),'rejected')
        self.assertEqual(self.state.receive(b' '*4097),'rejected')
        row=self.state.history(receipts=True)['records'][-1]
        self.assertEqual((row['raw_size'],len(bytes.fromhex(row['raw_payload_hex']))),(4097,4096))


class ApiTests(unittest.TestCase):
    def setUp(self):
        folder=EVIDENCE/self._testMethodName;folder.mkdir(parents=True,exist_ok=True)
        self.state=PersistentState(folder/'api.sqlite3')
        self.http=ThreadingHTTPServer(('127.0.0.1',0),backend_handler(self.state))
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.http.server_port}'

    def tearDown(self):
        self.http.shutdown();self.http.server_close();self.thread.join()

    def test_availability_health_history_and_assets(self):
        self.state.receive(raw(EVENTS[0]))
        self.assertEqual(get(self.url+'/api/availability')['spaces'][0]['status'],'available')
        self.assertFalse(get(self.url+'/api/health')['sensors'][0]['fresh_this_connection'])
        self.assertEqual(get(self.url+'/api/events')['records'][0]['ctr'],0)
        self.assertEqual(get(self.url+'/api/receipts')['records'][0]['outcome'],'accepted')
        for route in ('/backend/','/backend.js','/base.js','/style.css','/','/simulation/'):
            with urlopen(self.url+route) as response:self.assertEqual(response.status,200)

    def test_api_bad_parameters_and_storage_health(self):
        for query in ('after=-1','limit=0','after=bad','limit=101'):
            with self.assertRaises(HTTPError) as error:get(self.url+'/api/events?'+query)
            self.assertEqual(error.exception.code,400)
        self.state.fail_storage(sqlite3.OperationalError('injected failure'))
        for route in ('/api/health','/api/availability'):
            with self.assertRaises(HTTPError) as error:get(self.url+route)
            self.assertEqual(error.exception.code,503)

    def test_api_reads_independently_committed_database_state(self):
        independent=PersistentState(self.state.path)
        independent.receive(raw(EVENTS[0]))
        self.assertEqual(get(self.url+'/api/availability')['accepted'],1)
        self.assertEqual(get(self.url+'/api/events')['records'][0]['payload'],EVENTS[0])


class RealMqttDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.folder=EVIDENCE/self._testMethodName;self.folder.mkdir(parents=True,exist_ok=True)
        self.path=self.folder/'integrated.sqlite3'
        self.broker=Broker(self._testMethodName).start();self.addCleanup(self.broker.stop)
        self.state=PersistentState(self.path,journal=Journal(self.folder/'commits-and-acks.jsonl'))
        self.sub=DurableSubscriber(self.state,self.broker.port);self.addCleanup(self.sub.stop)
        self.assertTrue(self.sub.start())
        self.pub=Publisher(self.broker.port);self.addCleanup(self.pub.stop);self.pub.start()

    def test_real_22_events_database_rows_and_api(self):
        for event in EVENTS:self.pub.publish(raw(event))
        wait_for(lambda:self.state.snapshot()['accepted']==22)
        self.assertEqual([r['payload'] for r in self.state.history()['records']],EVENTS)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0],22)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM bay_current').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT ctr FROM events ORDER BY id DESC LIMIT 1').fetchone()[0],21)

    def test_real_duplicate_malformed_and_missing_event_recovery(self):
        for value in (raw(EVENTS[0]),raw(EVENTS[0]),b'{bad',raw(EVENTS[2]),raw(EVENTS[1])):self.pub.publish(value)
        wait_for(lambda:self.state.snapshot()['received']==5)
        data=self.state.snapshot()
        self.assertEqual((data['accepted'],data['duplicates'],data['rejected']),(2,1,2))
        self.assertEqual(len(self.state.history()['records']),2)

    def test_real_reconnect_keeps_db_history_and_separates_freshness(self):
        self.pub.publish(raw(EVENTS[0]));wait_for(lambda:self.state.snapshot()['accepted']==1)
        self.pub.stop();self.broker.stop();wait_for(lambda:not self.state.connected)
        self.assertEqual(self.state.snapshot()['spaces'][0]['status'],'available')
        self.broker.start();wait_for(lambda:self.sub.ready.is_set(),timeout=10)
        self.assertFalse(self.state.snapshot()['spaces'][0]['fresh_this_connection'])
        replacement=Publisher(self.broker.port)
        try:
            replacement.start();replacement.publish(raw(EVENTS[1]));wait_for(lambda:self.state.snapshot()['accepted']==2)
            self.assertTrue(self.state.snapshot()['spaces'][0]['fresh_this_connection'])
        finally:replacement.stop()

    def test_real_db_failure_rolls_back_and_withholds_subscriber_ack(self):
        with self.state.db() as db:
            db.execute("CREATE TRIGGER force_fault BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT,'injected DB fault'); END")
        self.pub.publish(raw(EVENTS[0]))  # publisher PUBACK is broker-only, not subscriber commit
        wait_for(lambda:self.state.storage_error is not None)
        self.assertEqual(self.state.snapshot()['accepted'],0)
        journal=[json.loads(line) for line in (self.folder/'commits-and-acks.jsonl').read_text().splitlines()]
        self.assertFalse(any(r['event']=='subscriber_ack_after_commit' for r in journal))
        self.assertTrue(any(r['event']=='storage_failure_no_subscriber_ack' for r in journal))

    def test_actual_backend_process_restart_retains_all_22_and_checkpoint(self):
        self.sub.stop()  # a separate process now owns this stream/DB
        process=BackendProcess(self.path,self.broker.port,self.folder).start()
        self.addCleanup(process.stop)
        for event in EVENTS:self.pub.publish(raw(event))
        wait_for(lambda:get(process.url+'/api/availability')['accepted']==22)
        first_pid=process.process.pid
        before=get(process.url+'/api/events')
        process.stop();process.start()
        self.assertNotEqual(first_pid,process.process.pid)
        after=get(process.url+'/api/events')
        self.assertEqual(before,after)
        data=get(process.url+'/api/availability')
        self.assertEqual((data['accepted'],data['spaces'][0]['status'],data['spaces'][0]['ctr']),(22,'occupied',21))
        self.assertFalse(data['spaces'][0]['fresh_this_connection'])
        self.pub.publish(raw(EVENTS[-1]))
        wait_for(lambda:get(process.url+'/api/availability')['duplicates']==1)
        self.assertEqual(len(get(process.url+'/api/events')['records']),22)


if __name__=='__main__':
    unittest.main(verbosity=2)
