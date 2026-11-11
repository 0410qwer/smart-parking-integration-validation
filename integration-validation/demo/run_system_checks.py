"""Consolidated existing + live integration suites; each execution preserves a new manifest."""
from datetime import datetime,timezone
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import urlopen

HERE=Path(__file__).resolve().parent
def fetch_replay():
    try:
        with urlopen('http://127.0.0.1:8765/api/replay?count=0',timeout=2) as r:return json.load(r).get('mode')=='CAPTURE_REPLAY'
    except Exception:return False

def normalize(name,data):
    def python(d):return {k:d[k] for k in ('passed','failed','errors','skipped')}
    def node(d):return dict(passed=d['pass'],failed=d['fail'],errors=0,skipped=d['skipped'])
    if name=='regression':return [python(data['existing']),python(data['demo']),node(data['frontend'])]
    if name=='sensor':return [dict(passed=data['native']['passed'],failed=data['native']['failed'],errors=0,skipped=0),python(data['python'])]
    if name=='live_contract':return [python(data['python']),node(data['node'])]
    if 'passed' in data:return [python(data)]
    return [node(data)]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--without-live',action='store_true',help='Explicitly report live Wokwi E2E NOT RUN; not a full verification')
    args=parser.parse_args()
    output=HERE/'evidence'/('system-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));output.mkdir(parents=True)
    jobs=[('regression',[sys.executable,str(HERE/'run_checks.py')],'2026'),
          ('mqtt',[sys.executable,str(HERE/'mqtt/run_transport_checks.py')],'mqtt-tests-'),
          ('backend',[sys.executable,str(HERE/'backend/run_backend_checks.py')],'backend-tests-'),
          ('sensor',[sys.executable,str(HERE/'sensor-wokwi/run_checks.py')],'sensor-tests-'),
          ('replay_browser',['node',str(HERE/'browser/run.cjs')],'browser-'),
          ('mqtt_browser',['node',str(HERE/'mqtt/run_browser.cjs')],'mqtt-browser-'),
          ('backend_browser',['node',str(HERE/'backend/run_browser.cjs')],'backend-browser-'),
          ('live_contract',[sys.executable,str(HERE/'live/run_checks.py')],'live-tests-'),
          ('multi_contract',[sys.executable,str(HERE/'multi/run_checks.py')],'multi-tests-')]
    if not args.without_live:
        jobs.append(('live_e2e',[sys.executable,str(HERE/'live/run_e2e.py')],'live-browser-'))
        jobs.append(('startup',[sys.executable,str(HERE/'local_stack/run_checks.py')],'startup-tests-'))
        jobs.append(('multi_browser',[sys.executable,str(HERE/'multi/run_browser.py')],'multi-browser-'))
    replay=None;reports=[];failed=False
    try:
        if not fetch_replay():
            replay=subprocess.Popen([sys.executable,str(HERE/'server.py')],stdout=(output/'replay-server.txt').open('w'),stderr=subprocess.STDOUT)
            deadline=time.monotonic()+5
            while not fetch_replay() and time.monotonic()<deadline:time.sleep(.1)
            if not fetch_replay():raise RuntimeError('Port 8765 unavailable or occupied by a different service; no unknown process was stopped')
        for name,command,prefix in jobs:
            print('Running '+name,flush=True)
            before=set(HERE.joinpath('evidence').iterdir());started=time.monotonic()
            with (output/(name+'.txt')).open('w',encoding='utf-8') as log:
                try:completed=subprocess.run(command,env=dict(os.environ,PARKING_PYTHON=sys.executable),stdout=log,stderr=subprocess.STDOUT,timeout=900)
                except subprocess.TimeoutExpired:
                    reports.append(dict(name=name,workflow_error='timeout',command=command));failed=True;continue
            candidates=[p for p in set(HERE.joinpath('evidence').iterdir())-before if p.is_dir() and p.name.startswith(prefix) and (p/'results.json').exists()]
            if len(candidates)!=1:
                reports.append(dict(name=name,command=command,exit_code=completed.returncode,workflow_error='Expected one new result directory'));failed=True;continue
            folder=candidates[0];data=json.loads((folder/'results.json').read_text())
            counts=normalize(name,data)
            entry=dict(name=name,command=command,exit_code=completed.returncode,evidence=str(folder),counts=counts,duration_seconds=time.monotonic()-started)
            reports.append(entry)
            failed|=completed.returncode!=0 or any(c['failed'] or c['errors'] for c in counts)
        totals={k:sum(c[k] for r in reports for c in r.get('counts',[])) for k in ('passed','failed','errors','skipped')}
        files=[HERE.parent/'captures/wokwi_serial_actual.txt',HERE.parent.parent/'wokwi-source/sketch.ino',HERE.parent.parent/'wokwi-source/diagram.json']
        files.extend(HERE.parent.parent/'smart-parking-web'/n for n in ('app.js','index.html','style.css'))
        summary=dict(overall='FAIL' if failed else 'PASS',full_verification=not args.without_live,
            live_e2e='NOT RUN' if args.without_live else 'see suite result',
            startup='NOT RUN' if args.without_live else 'see suite result',suites=reports,totals=totals,
            preserved_file_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},physical_accuracy_verified=False)
        (output/'results.json').write_text(json.dumps(summary,indent=2))
        print(json.dumps(dict(evidence=str(output),overall=summary['overall'],totals=totals),indent=2))
        return int(failed)
    finally:
        if replay and replay.poll() is None:replay.terminate();replay.wait(timeout=5)

if __name__=='__main__':raise SystemExit(main())
