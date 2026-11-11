"""Own real broker/backend processes for one full three-sensor browser scenario."""
import json,os,sqlite3,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'mqtt'));sys.path.insert(0,str(HERE.parent/'local_stack'))
from test_transport import Broker,wait_for
from supervisor import Child
from urllib.request import urlopen
folder=Path(os.environ['MULTI_BROWSER_OUTPUT']);database=folder/'parking.sqlite3'
broker=Broker('multi-browser').start();backend=None;port=0
def api(route='/api/availability'):
    with urlopen(f'http://127.0.0.1:{port}'+route,timeout=3) as r:return json.load(r)
def start_backend():
    global backend,port
    backend=Child('backend',[sys.executable,str(HERE.parent/'local_stack/managed_backend.py'),'--mode','Multi',
        '--port',str(port),'--mqtt-port',str(broker.port),'--db',str(database),'--stream','browser-multi','--log',str(folder/'backend.jsonl')],folder)
    port=backend.wait_ready()['port']
    with (folder/'backend-processes.jsonl').open('a') as stream:stream.write(json.dumps(dict(pid=backend.process.pid,port=port))+'\n')
def disk():
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        return dict(events=[dict(r) for r in db.execute('SELECT id,event_uuid,spot_id,occupied,ctr,heartbeat,status,batt_mv,payload_json,received_at FROM events ORDER BY id')],
            delivery_keys=db.execute('SELECT COUNT(*) FROM delivery_keys').fetchone()[0],integrity=db.execute('PRAGMA integrity_check').fetchone()[0])
try:
    start_backend();print(json.dumps(dict(ready=True,url=f'http://127.0.0.1:{port}',mqtt_port=broker.port)),flush=True)
    for line in sys.stdin:
        command=json.loads(line)
        try:
            action=command['action']
            if action=='stop':break
            if action=='broker_down':broker.stop();wait_for(lambda:not api()['broker_connected'])
            elif action=='broker_up':broker.start();wait_for(lambda:api()['broker_connected'],timeout=12)
            elif action=='backend_restart':backend.stop();start_backend()
            elif action=='metrics':
                from performance_tools import process_rss,sampled_file_bytes
                pids=dict(backend=backend.process.pid,broker=broker.process.pid,**command.get('pids',{}))
                print(json.dumps(dict(ok=True,at=time.time(),rss_bytes={k:process_rss(v) for k,v in pids.items()},
                    process_alive=dict(backend=backend.process.poll() is None,broker=broker.process.poll() is None),
                    database_bytes=sampled_file_bytes(folder.glob('parking.sqlite3*')),api=api())),flush=True)
                continue
            elif action!='inspect':raise ValueError('Unknown fixture action')
            print(json.dumps(dict(ok=True,api=api(),disk=disk())),flush=True)
        except Exception as exc:print(json.dumps(dict(ok=False,error=str(exc))),flush=True)
finally:
    if backend:backend.stop()
    broker.stop()
