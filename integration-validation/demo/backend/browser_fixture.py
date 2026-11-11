"""Browser-test controller for separate real broker/backend processes and on-disk DB."""
import json
import sqlite3
import sys
from store import HERE
from transport import CAPTURE, Publisher, Journal, load_capture
from test_backend import BackendProcess, EVIDENCE, get
from test_transport import Broker,wait_for

broker=Broker('backend-browser-broker').start()
database=EVIDENCE/'parking.sqlite3'
backend=BackendProcess(database,broker.port,EVIDENCE).start()
publisher=Publisher(broker.port,journal=Journal(EVIDENCE/'publisher.jsonl'))
publisher.start()
records=load_capture(CAPTURE.read_text(encoding='utf-8-sig'))['records']

def disk():
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        return dict(events=[{**dict(row),'raw_payload':row['raw_payload'].hex()} for row in db.execute(
            'SELECT id,event_uuid,spot_id,occupied,status,batt_mv,ctr,heartbeat,source_timestamp,received_at,raw_payload FROM events ORDER BY id')],
            current=[dict(r) for r in db.execute('SELECT * FROM bay_current')],
            receipts=[dict(r) for r in db.execute('SELECT outcome,COUNT(*) AS n FROM receipts GROUP BY outcome')],
            integrity=db.execute('PRAGMA integrity_check').fetchone()[0])

try:
    print(json.dumps(dict(event='ready',url=backend.url,database=str(database),backend_pid=backend.process.pid)),flush=True)
    for line in sys.stdin:
        command=json.loads(line)
        try:
            action=command['action']
            if action in ('publish','raw'):
                before=get(backend.url+'/api/availability')['received']
                payload=records[command['index']]['raw_line'].strip().encode() if action=='publish' else command['raw'].encode()
                publisher.publish(payload)
                wait_for(lambda:get(backend.url+'/api/availability')['received']==before+1)
            elif action=='restart':
                backend.stop();backend.start()
            elif action=='disconnect':
                publisher.stop();broker.stop()
                wait_for(lambda:not get(backend.url+'/api/health')['broker_connected'])
            elif action=='reconnect':
                broker.start()
                wait_for(lambda:get(backend.url+'/api/health')['broker_connected'],timeout=10)
                publisher=Publisher(broker.port,journal=Journal(EVIDENCE/'publisher.jsonl'));publisher.start()
            elif action=='inspect':
                pass
            elif action=='stop':
                break
            else:
                raise ValueError('Unknown controller action')
            result=dict(ok=True,state=get(backend.url+'/api/availability'),health=get(backend.url+'/api/health'),
                        history=get(backend.url+'/api/events'),disk=disk(),backend_pid=backend.process.pid)
            print(json.dumps(result),flush=True)
        except Exception as exc:
            print(json.dumps(dict(ok=False,error=str(exc))),flush=True)
finally:
    publisher.stop();backend.stop();broker.stop()
