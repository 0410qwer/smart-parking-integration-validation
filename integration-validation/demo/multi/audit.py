"""Build a traceable final audit from actual consolidated results, not new test counts."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('results', type=Path)
    args = parser.parse_args()
    results = json.loads(args.results.read_text(encoding='utf-8'))
    multi = next(s for s in results['suites'] if s['name'] == 'multi_browser')
    proof_path = Path(multi['evidence']) / 'proof.json'
    proof = json.loads(proof_path.read_text(encoding='utf-8')) if proof_path.exists() else {}
    protected = results.get('preserved_file_sha256', {})
    unchanged = {p: hashlib.sha256(Path(p).read_bytes()).hexdigest() == digest for p, digest in protected.items()}
    git = subprocess.run(['git', '-c', 'safe.directory=' + str(ROOT / 'smart-parking-web'), '-C', str(ROOT / 'smart-parking-web'), 'status', '--porcelain'], capture_output=True, text=True)
    normal = [c['elapsed_wall_ms'] for c in proof.get('cases', []) if c.get('phase') == 'normal']
    outage = [c['elapsed_wall_ms'] for c in proof.get('cases', []) if 'elapsed_wall_ms' in c and c.get('phase') != 'normal']
    audit = dict(created_at=datetime.now(timezone.utc).isoformat(), reference_backend=True,
                 source_type='three measured virtual HC-SR04 sensors on one simulated ESP32',
                 saved_capture_input=False, physical_hardware_verified=False,
                 direct_esp32_mqtt_verified=False, production_backend_available=False,
                 consolidated_results=str(args.results.resolve()), overall=results['overall'],
                 counts=results['totals'], suites=results['suites'], browser_proof=str(proof_path),
                 handoff_browser_check=str(HERE.parent/'evidence/multi-handoff-20261111-final/browser-check.json'),
                 handoff_url='http://127.0.0.1:8780/backend/',
                 virtual_correctness=proof.get('correctness'),
                 timing=dict(start='before browser virtual distance control setter', end='matching Dashboard DOM',
                             normal_ms=normal, broker_outage_recovery_ms=outage,
                             note='Wall time including virtual debounce; no physical latency guarantee.'),
                 protected_files_unchanged=unchanged,
                 teammate_frontend_git_clean=git.returncode == 0 and not git.stdout.strip(),
                 verified_path='live Wokwi Serial -> durable outbox -> TCP MQTT QoS1 -> committed SQLite -> API -> Edge Dashboard',
                 ready_for_local_virtual_demo=results['overall']=='PASS' and proof.get('passed') is True,
                 production_ready=False,
                 changed_files=sorted(str(p.relative_to(ROOT)) for p in HERE.rglob('*')
                                      if p.is_file() and '__pycache__' not in p.parts and p.name != 'FINAL_AUDIT.json') + [
                     'Start-LocalDemo.ps1', 'integration-validation/demo/live/bridge.cjs',
                     'integration-validation/demo/live/verify_live.cjs', 'integration-validation/demo/local_stack/supervisor.py',
                     'integration-validation/demo/local_stack/managed_backend.py', 'integration-validation/demo/local_stack/verify_stack.cjs',
                     'integration-validation/demo/local_stack/test_startup.py', 'integration-validation/demo/run_system_checks.py',
                     'INTEGRATION_DEMO_README.md', 'integration-validation/demo/multi/FINAL_AUDIT.json'])
    target = HERE / 'FINAL_AUDIT.json'
    target.write_text(json.dumps(audit, indent=2), encoding='utf-8')
    print(json.dumps(dict(audit=str(target), counts=audit['counts'], ready=audit['ready_for_local_virtual_demo']), indent=2))

if __name__ == '__main__':
    main()
