"""Audit real demo broker bytes, database rows, API state, ACK order and test counts."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from urllib.request import urlopen
from store import HERE
from transport import CAPTURE,load_capture

evidence=HERE.parent/'evidence'
output=evidence/('backend-audit-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
output.mkdir(parents=True,exist_ok=False)
def read_lines(path):return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
def latest(prefix):return sorted(p for p in evidence.iterdir() if p.is_dir() and p.name.startswith(prefix) and (p/'results.json').exists())[-1]
def api(route):
    with urlopen('http://127.0.0.1:8767'+route,timeout=4) as response:return json.load(response)

records=load_capture(CAPTURE.read_text(encoding='utf-8-sig'))['records']
payloads=[r['source_payload'] for r in records]
raw=[r['raw_line'].strip().encode() for r in records]
database=HERE/'data'/'parking-reference.sqlite3'
# sqlite backup includes committed WAL data and produces a self-contained evidence DB.
with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as source,sqlite3.connect(output/'database-snapshot.sqlite3') as target:
    source.backup(target)
    target.row_factory=sqlite3.Row
    rows=target.execute('SELECT * FROM events WHERE stream_id=? ORDER BY ordinal',('capture-1',)).fetchall()
    assert [json.loads(r['payload_json']) for r in rows]==payloads
    assert [r['raw_payload'] for r in rows]==raw
    assert all(r['source_timestamp'] is None for r in rows)
    assert target.execute('SELECT COUNT(*) FROM bay_current WHERE stream_id=?',('capture-1',)).fetchone()[0]==1
    assert target.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert target.execute('PRAGMA foreign_key_check').fetchall()==[]
broker=read_lines(evidence/'backend-demo-broker.jsonl')
publisher=read_lines(evidence/'backend-demo-publisher.jsonl')
assert [r['payload'].encode() for r in broker if r['event']=='publish']==raw
assert [bytes.fromhex(r['payload_hex']) for r in publisher if r['event']=='puback']==raw
journal=read_lines(evidence/'backend-demo-journal.jsonl')
commits=[(i,r) for i,r in enumerate(journal) if r['event']=='sqlite_committed']
acks=[(i,r) for i,r in enumerate(journal) if r['event']=='subscriber_ack_after_commit']
assert len(commits)==len(acks)==22
assert all(ci<ai and c['outcome']==a['outcome']=='accepted' for (ci,c),(ai,a) in zip(commits,acks))
availability,health,history=api('/api/availability'),api('/api/health'),api('/api/events')
before_history=evidence/'backend-demo-before-restart-history.json'
demo_restart_verified=False
if before_history.exists():
    assert json.loads(before_history.read_text(encoding='utf-8'))==history
    assert availability['spaces'][0]['fresh_this_connection'] is False
    demo_restart_verified=True
assert availability['accepted']==22 and availability['spaces'][0]['ctr']==21
assert availability['spaces'][0]['status']=='occupied'
assert all(s['status']=='unknown' and s['occupied'] is None for s in availability['spaces'][1:])
assert [r['payload'] for r in history['records']]==payloads
assert [r['id'] for r in history['records']]==[r['id'] for r in rows]
for name,data in [('availability',availability),('health',health),('history',history)]:
    (output/(name+'.json')).write_text(json.dumps(data,indent=2),encoding='utf-8')
paths=dict(regression=latest('2026'),replay_browser=latest('browser-'),mqtt_transport=latest('mqtt-tests-'),
           mqtt_browser=latest('mqtt-browser-'),backend_python=latest('backend-tests-'),backend_browser=latest('backend-browser-'))
reports={key:json.loads((folder/'results.json').read_text(encoding='utf-8')) for key,folder in paths.items()}
reg=reports['regression']
counts=[]
for key in ('existing','demo'):
    counts.append(dict(name=key,**{k:reg[key][k] for k in ('passed','failed','errors','skipped')}))
counts.append(dict(name='javascript',passed=reg['frontend']['pass'],failed=reg['frontend']['fail'],errors=0,skipped=reg['frontend']['skipped']))
for key,report in reports.items():
    if key=='regression':continue
    counts.append(dict(name=key,passed=report.get('passed',report.get('pass')),failed=report.get('failed',report.get('fail')),
                       errors=report.get('errors',0),skipped=report['skipped']))
assert all(c['failed']==c['errors']==0 for c in counts)
files=[CAPTURE,*(HERE.parent.parent.parent/'smart-parking-web'/name for name in ('app.js','index.html','style.css'))]
files.extend(p for p in HERE.iterdir() if p.is_file())
hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
for name,expected in reg['sha256'].items():assert hashes[name]==expected
summary=dict(overall='PASS: isolated SQLite reference backend only',suites=counts,
             totals={k:sum(c[k] for c in counts) for k in ('passed','failed','errors','skipped')},
             evidence={k:str(v) for k,v in paths.items()},demo_events=22,database_integrity='ok',
             raw_capture_broker_database_api_match=True,subscriber_ack_after_commit_verified=True,
             standalone_backend_restart_history_unchanged=demo_restart_verified,
             file_sha256=hashes,physical_sensor_verified=False,saaket_backend_available=False,production_acceptance=False)
(output/'results.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(dict(evidence=str(output),totals=summary['totals']),indent=2))
