"""Cross-check publisher, actual broker, subscriber and regression evidence."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen
from transport import HERE, CAPTURE, TOPIC, load_capture

evidence=HERE.parent/'evidence'
def latest(prefix):
    return sorted(p for p in evidence.iterdir() if p.is_dir() and p.name.startswith(prefix) and (p/'results.json').exists())[-1]
def read_lines(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]

output=evidence/('mqtt-audit-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
output.mkdir(parents=True,exist_ok=False)
records=load_capture(CAPTURE.read_text(encoding='utf-8-sig'))['records']
payloads=[r['source_payload'] for r in records]
raw=[r['raw_line'].strip() for r in records]
broker=read_lines(evidence/'mqtt-broker-demo.jsonl')
publisher=read_lines(evidence/'mqtt-publisher-demo.jsonl')
session=sorted(evidence.glob('mqtt-session-*/subscriber.jsonl'))[-1]
subscriber=read_lines(session)
assert [r['payload'] for r in broker if r['event']=='publish' and r['topic']==TOPIC]==raw
assert [r['payload_hex'] for r in publisher if r['event']=='puback']==[s.encode().hex() for s in raw]
accepted=[r for r in subscriber if r['event']=='accepted']
assert [r['payload'] for r in accepted]==payloads
assert all(r['qos']==1 and not r['retained'] for r in accepted)
assert len([r for r in subscriber if r['event'] in ('rejected','duplicate')])==0
assert any(r['event']=='suback' for r in subscriber)
with urlopen('http://127.0.0.1:8766/api/mqtt',timeout=3) as response:
    snapshot=json.load(response)
assert snapshot['accepted']==22 and snapshot['spaces'][0]['ctr']==21
assert snapshot['spaces'][0]['id']=='A01' and not any(s['online'] for s in snapshot['spaces'][1:])
(output/'api_snapshot.json').write_text(json.dumps(snapshot,indent=2),encoding='utf-8')
paths=dict(regression=latest('2026'), replay_browser=latest('browser-'),
           mqtt_transport=latest('mqtt-tests-'), mqtt_browser=latest('mqtt-browser-'))
summaries={key:json.loads((folder/'results.json').read_text(encoding='utf-8')) for key,folder in paths.items()}
reg=summaries['regression']
counts=[dict(name='existing',passed=reg['existing']['passed'],failed=reg['existing']['failed'],errors=reg['existing']['errors'],skipped=reg['existing']['skipped']),
        dict(name='demo',passed=reg['demo']['passed'],failed=reg['demo']['failed'],errors=reg['demo']['errors'],skipped=reg['demo']['skipped']),
        dict(name='javascript',passed=reg['frontend']['pass'],failed=reg['frontend']['fail'],errors=0,skipped=reg['frontend']['skipped'])]
for name in ('replay_browser','mqtt_transport','mqtt_browser'):
    report=summaries[name]
    counts.append(dict(name=name,passed=report.get('pass',report.get('passed')),failed=report.get('fail',report.get('failed')),
                       errors=report.get('errors',0),skipped=report['skipped']))
assert all(c['failed']==0 and c['errors']==0 for c in counts)
files=[CAPTURE,*(HERE.parent.parent.parent/'smart-parking-web'/name for name in ('app.js','index.html','style.css'))]
files.extend(p for p in HERE.iterdir() if p.is_file())
hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
for name,expected in reg['sha256'].items():
    assert hashes[name]==expected
result=dict(overall='PASS: local MQTT capture transport only',suites=counts,
            totals={key:sum(c[key] for c in counts) for key in ('passed','failed','errors','skipped')},
            evidence={key:str(value) for key,value in paths.items()},subscriber_journal=str(session),
            broker_messages=22,publisher_pubacks=22,subscriber_accepted=22,byte_exact_capture_publish=True,
            file_sha256=hashes,physical_sensor_verified=False,production_backend_verified=False,database_verified=False)
(output/'results.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(dict(output=str(output),totals=result['totals']),indent=2))
