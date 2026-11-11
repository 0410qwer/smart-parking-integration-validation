"""Read-only final technical audit of a specific consolidated run and original sources."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
from urllib.request import urlopen

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent.parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('system_results',type=Path)
args=parser.parse_args()
system=json.loads(args.system_results.read_text())
assert system['overall']=='PASS' and system['full_verification']
assert all(s.get('exit_code')==0 for s in system['suites'])
assert system['totals']['failed']==system['totals']['errors']==system['totals']['skipped']==0
live=next(s for s in system['suites'] if s['name']=='live_e2e')
proof=json.loads((Path(live['evidence'])/'proof.json').read_text())
assert proof['saved_capture_input'] is False
assert [s['api']['spaces'][0]['occupied'] for s in proof['states']]==[False,True,False]
assert proof['after_stop_health']['bridge']['state']=='offline'
assert proof['after_stop_health']['sensors'][0]['fresh_this_connection'] is False
expected={'wokwi-source/sketch.ino':'b57e51aeb6a996b5cdb198f839addd116136a3f0ffd8c30b13846f6e7f68b918',
          'wokwi-source/diagram.json':'d0ba612ce3d49a565ff82fcbb0e4550d6e7062f85c5ee856a4df616b9e38e7a6',
          'integration-validation/captures/wokwi_serial_actual.txt':'dbfb098e800fe0d23a91beff2cec781350d23ea013597e625e85e7d73181e5c2'}
for rel,sha in expected.items():assert hashlib.sha256((ROOT/rel).read_bytes()).hexdigest()==sha
git=subprocess.run(['git','-c','safe.directory='+str(ROOT/'smart-parking-web'),'-C',str(ROOT/'smart-parking-web'),'status','--porcelain'],capture_output=True,text=True)
assert git.returncode==0 and not git.stdout.strip()
measures=[m['value'] for m in proof['metrics']]
output=HERE/'evidence'/('technical-audit-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));output.mkdir()
files=[ROOT/'Start-LocalDemo.ps1',ROOT/'Stop-LocalDemo.ps1',HERE/'run_system_checks.py',HERE/'audit_system.py',HERE/'backend/store.py']
files.extend(p for folder in ('live','local_stack') for p in (HERE/folder).iterdir() if p.is_file())
audit=dict(system_evidence=str(args.system_results.resolve()),test_totals=system['totals'],live_evidence=live['evidence'],
           live_data_path_verified=True,capture_replay_used_in_live_test=False,teammate_frontend_git_clean=True,
           metrics=dict(name='browser_live_serial_observation_to_dashboard_wall_ms',n=len(measures),min=min(measures),
                        median=statistics.median(measures),max=max(measures),physical_sensor_latency=False),
           fixed_bugs=['Windows manifest sharing race','Partial live UART JSON frame forwarding',
                       'Foreign DB journal changed before refusal','Optional evidence log error broke post-commit acknowledgement'],
           remaining_limits=['No physical sensor/ESP32 acceptance','No direct ESP32 MQTT (browser Serial bridge is the live path)',
                'Saaket production backend/database unavailable','No production TLS/auth or durable broker/outbox',
                'No durable source event/session identity beyond explicit stream namespace',
                'Wokwi DOM/API/build availability dependency; buffer reset/truncation fails closed',
                'Last-known occupancy is retained and labelled; bridge health is not physical connectivity'],
           original_hashes=expected,changed_source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
try:
    with urlopen('http://127.0.0.1:8767/api/availability',timeout=2) as response:original=json.load(response)
    audit['preserved_original_reference_state']={k:original[k] for k in ('accepted','duplicates','rejected')}
except OSError:audit['preserved_original_reference_service']='Not running; no data was modified by this audit'
(output/'audit.json').write_text(json.dumps(audit,indent=2))
print(json.dumps(dict(evidence=str(output),totals=system['totals'],metrics=audit['metrics']),indent=2))
