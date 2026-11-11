"""Synthetic transport stress only: no physical or Wokwi sensor accuracy claim."""
from datetime import datetime,timezone
from contextlib import redirect_stdout,redirect_stderr
import json,os,sqlite3,sys,threading,time,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
output=HERE.parent/'evidence'/('volume-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));output.mkdir()
os.environ['MQTT_TEST_EVIDENCE']=str(output)
sys.path.insert(0,str(HERE.parent/'mqtt'))
from test_transport import Broker,wait_for
from model import MultiState,MultiSubscriber
from outbox import Outbox,Worker
from performance_tools import process_rss,sampled_file_bytes

class Volume(unittest.TestCase):
    def test_real_mqtt_high_volume_rollover_dedup_and_durable_drain(self):
        started=time.monotonic();broker=Broker('volume').start();self.addCleanup(broker.stop)
        state=MultiState(output/'parking.sqlite3','volume');sub=MultiSubscriber(state,broker.port);self.addCleanup(sub.stop);self.assertTrue(sub.start())
        box=Outbox(output/'outbox.sqlite3');worker=Worker(broker.port,'volume',box,output);self.addCleanup(worker.stop)
        for spot in (1001,1002,1003):worker.signals[spot]=dict(state='online')
        samples=[];stopping=threading.Event()
        def monitor():
            while not stopping.is_set():
                samples.append(dict(elapsed_seconds=time.monotonic()-started,rss_bytes=process_rss(os.getpid()),
                    broker_rss_bytes=process_rss(broker.process.pid),database_bytes=sampled_file_bytes(output.glob('*.sqlite3*')),
                    connected=state.connected,worker_threads_alive=all(t.is_alive() for t in worker.threads)))
                stopping.wait(2)
        thread=threading.Thread(target=monitor);thread.start();self.addCleanup(lambda:(stopping.set(),thread.join(timeout=4)))
        count=900;first=[]
        for i in range(count):
            spot=1001+i%3;sequence=i//3
            event=dict(spot_id=spot,occupied=bool(sequence%2),batt_mv=3600,status=sequence%2,ctr=sequence%256,heartbeat=sequence==0)
            raw=json.dumps(event,separators=(',',':'))
            key=box.enqueue(dict(raw=raw,serial_index=i,observed_at=time.time()*1000))
            if i<3:first.append((key,raw))
        wait_for(lambda:all(box.counts(s).get('delivered')==300 for s in (1001,1002,1003)),timeout=180)
        for key,raw in first:worker.client.publish(state.prefix+'/'+key,raw,qos=1).wait_for_publish(timeout=3)
        wait_for(lambda:state.snapshot()['duplicates']==3)
        # Malformed payload and late old counter cannot overwrite the latest valid checkpoint.
        for spot in (1001,1002,1003):
            worker.client.publish(state.prefix+f'/{spot}/events/bad/json',b'{bad',qos=1).wait_for_publish(timeout=3)
            stale=json.dumps(dict(spot_id=spot,occupied=False,batt_mv=3600,status=0,ctr=1,heartbeat=True))
            worker.client.publish(state.prefix+f'/{spot}/events/old/frame',stale,qos=1).wait_for_publish(timeout=3)
        wait_for(lambda:state.snapshot()['rejected']==6)
        with sqlite3.connect(output/'parking.sqlite3') as db:
            rows=db.execute('SELECT COUNT(*),COUNT(DISTINCT event_uuid) FROM events').fetchone()
            integrity=db.execute('PRAGMA integrity_check').fetchone()[0]
        self.assertEqual(rows,(count,count));self.assertEqual(integrity,'ok')
        snapshot=state.snapshot();self.assertEqual(snapshot['accepted'],count)
        self.assertEqual([s['ctr'] for s in snapshot['spaces']],[43,43,43])
        self.assertTrue(thread.is_alive(),'Resource monitor must still be running')
        self.assertGreaterEqual(len(samples),2,'Resource monitoring must not silently be omitted')
        self.assertTrue(all(s['connected'] and s['worker_threads_alive'] for s in samples))
        stopping.set();thread.join(timeout=4)
        report=dict(traffic_kind='HARNESS_GENERATED_NOT_SENSOR_MEASUREMENTS',passed=True,generated=count,
            accepted=snapshot['accepted'],duplicate_deliveries=snapshot['duplicates'],rejected=snapshot['rejected'],
            missing_confirmed_events=count-rows[0],integrity=integrity,duration_seconds=time.monotonic()-started,
            resource_samples=samples,final_state=snapshot)
        (output/'volume.json').write_text(json.dumps(report,indent=2))

with (output/'console.txt').open('w',encoding='utf-8') as log,redirect_stdout(log),redirect_stderr(log):
    result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Volume))
summary=dict(passed=result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),failed=len(result.failures),errors=len(result.errors),skipped=len(result.skipped))
(output/'results.json').write_text(json.dumps(summary,indent=2));print(json.dumps(dict(evidence=str(output),**summary),indent=2))
raise SystemExit(0 if result.wasSuccessful() else 1)
