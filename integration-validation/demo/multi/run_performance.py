"""Real Edge/Wokwi controlled trials plus a bounded, explicitly timed soak."""
from datetime import datetime,timezone
import argparse,json,os,re,subprocess,sys
from pathlib import Path
from performance_tools import distribution
HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--rounds',type=int,default=10)
parser.add_argument('--soak-seconds',type=int,default=180)
args=parser.parse_args()
if not 1<=args.rounds<=100 or not 0<=args.soak_seconds<=1800:parser.error('rounds 1..100, soak 0..1800')
output=HERE.parent/'evidence'/('performance-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));output.mkdir()
env=dict(os.environ,MULTI_BROWSER_OUTPUT=str(output),PARKING_PYTHON=sys.executable,PERF_ROUNDS=str(args.rounds),PERF_SOAK=str(args.soak_seconds))
print('Real virtual-sensor performance evidence: '+str(output),flush=True)
with (output/'console.tap').open('w',encoding='utf-8') as log:
    result=subprocess.run(['node','--test','--test-reporter=tap',str(HERE/'performance.test.cjs')],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=1800)
counts={k:int(v) for k,v in re.findall(r'^# (tests|pass|fail|skipped|cancelled) (\d+)',(output/'console.tap').read_text(),re.MULTILINE)}
proof_path=output/'trials.json';trials=json.loads(proof_path.read_text()) if proof_path.exists() else []
summary={}
for cadence in (500,200):
    summary[str(cadence)]={}
    for direction in ('occupied','available'):
        group=[t for t in trials if t['poll_ms']==cadence and t['expected']==direction]
        summary[str(cadence)][direction]={metric:distribution([t[metric] for t in group if t.get(metric) is not None],len(group))
            for metric in ('control_to_dom_ms','observed_confirmed_serial_to_dom_ms','control_to_serial_ms','publish_to_receive_ms','validation_transaction_ms','commit_to_dom_ms','simulated_confirmation_ms','api_fetch_parse_ms','dom_build_ms','commit_to_poll_start_ms')}
report=dict(exit_code=result.returncode,counts=counts,performance=summary,physical_latency_verified=False,
            original_3136_attribution='Free transition includes 2500 ms configured debounce; historical run lacked boundary instrumentation for exact remaining attribution.')
(output/'results.json').write_text(json.dumps(report,indent=2));print(json.dumps(dict(evidence=str(output),**report),indent=2))
raise SystemExit(result.returncode)
