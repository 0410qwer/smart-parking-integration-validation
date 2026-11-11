"""Aggregate recorded test results; verify sensor source and original-file integrity."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from capture_adapter import HERE,validate_sensor_capture

root=HERE.parent/'evidence'
def latest(prefix):return sorted(p for p in root.iterdir() if p.is_dir() and p.name.startswith(prefix) and (p/'results.json').exists())[-1]
folders={key:latest(prefix) for key,prefix in dict(regression='2026',mqtt='mqtt-tests-',backend='backend-tests-',
    replay_browser='browser-',mqtt_browser='mqtt-browser-',backend_browser='backend-browser-',sensor='sensor-tests-').items()}
reports={key:json.loads((folder/'results.json').read_text()) for key,folder in folders.items()}
reg=reports['regression'];counts=[]
for key in ('existing','demo'):
    counts.append(dict(name=key,**{k:reg[key][k] for k in ('passed','failed','errors','skipped')}))
counts.append(dict(name='javascript',passed=reg['frontend']['pass'],failed=reg['frontend']['fail'],errors=0,skipped=reg['frontend']['skipped']))
for key in ('mqtt','backend','replay_browser','mqtt_browser','backend_browser'):
    r=reports[key];counts.append(dict(name=key,passed=r.get('passed',r.get('pass')),failed=r.get('failed',r.get('fail')),errors=r.get('errors',0),skipped=r['skipped']))
sensor=reports['sensor']
counts.append(dict(name='native_cpp',passed=sensor['native']['passed'],failed=sensor['native']['failed'],errors=0,skipped=0))
counts.append(dict(name='sensor_python',**{k:sensor['python'][k] for k in ('passed','failed','errors','skipped')}))
capture=root/'sensor-wokwi-capture-2026-11-11T13-43-58-176Z'
assert (capture/'sketch.ino').read_bytes()==(HERE/'firmware/sketch.ino').read_bytes()
assert json.loads((capture/'diagram.json').read_text())==json.loads((HERE/'firmware/diagram.json').read_text())
report=validate_sensor_capture((capture/'serial_actual.txt').read_text())
selftest=root/'sensor-wokwi-selftest-2026-11-11T13-43-59-425Z'
assert '[SELFTEST] SUMMARY passed=20 failed=0' in (selftest/'serial_actual.txt').read_text()
assert all(c['failed']==c['errors']==c['skipped']==0 for c in counts)
hashes={name:hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in reg['sha256']}
assert hashes==reg['sha256']
workspace=HERE.parents[2]
original_hashes={name:hashlib.sha256((workspace/'wokwi-source'/name).read_bytes()).hexdigest() for name in ('sketch.ino','diagram.json')}
output=root/('sensor-summary-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
output.mkdir(parents=True,exist_ok=False)
summary=dict(suites=counts,totals={k:sum(c[k] for c in counts) for k in ('passed','failed','errors','skipped')},
             evidence={k:str(v) for k,v in folders.items()},actual_wokwi_sensor_events=len(report['records']),
             wokwi_firmware_selftests=20,wokwi_selftests_also_run_on_host_not_counted_twice=True,
             direct_esp32_mqtt_verified=False,physical_sensor_accuracy_verified=False,
             original_source_sha256=original_hashes,original_frontend_capture_sha256=hashes)
(output/'results.json').write_text(json.dumps(summary,indent=2))
(output/'capture_validation.json').write_text(json.dumps(report,indent=2))
print(json.dumps(dict(evidence=str(output),totals=summary['totals']),indent=2))
