"""Unified offline audit runner; no external service connections or writes."""
import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from evidence_utils import new_run_id
from wokwi_serial_adapter import SOURCE_HASHES, validate_capture, render_summary
from wokwi_hex_validator import validate_hex_pairs

ROOT = Path(__file__).resolve().parent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, help='optional user-supplied Serial capture; origin not authenticated')
    args = parser.parse_args(argv)
    run_id = new_run_id()
    output = ROOT / 'runs' / run_id
    output.mkdir(parents=True, exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()
    sources = {}
    for name, expected in SOURCE_HASHES.items():
        path = ROOT.parent / 'wokwi-source' / name
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        sources[name] = dict(expected_sha256=expected, actual_sha256=actual,
                             result='PASS' if actual == expected else 'FAIL')
    command = [sys.executable, str(ROOT / 'run_simulation_tests.py')]
    with (output / 'test_console.txt').open('w', encoding='utf-8') as log:
        completed = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    local = json.loads((ROOT / 'simulation_test_report.json').read_text(encoding='utf-8'))
    # Store self-contained immutable results, not links to mutable latest files.
    (output / 'local_tests.json').write_text(json.dumps(local, indent=2) + '\n', encoding='utf-8')
    (output / 'LOCAL_TEST_REPORT.md').write_bytes((ROOT / 'VALIDATION_REPORT.md').read_bytes())
    ids = [case['test_id'] for case in local['test_cases']]
    trace_ok = all(ids) and len(ids) == len(set(ids)) and set(local['simulation_test_ids']).issuperset(f'SIM-{i:03}' for i in range(1, 39))
    captures = {}
    inputs = [('sample', ROOT / 'fixtures' / 'wokwi_serial_SAMPLE.txt', 'SAMPLE_FIXTURE')]
    if args.capture:
        inputs.append(('supplied_capture', args.capture, 'UNVERIFIED_CAPTURE'))
    for label, path, kind in inputs:
        try:
            raw = path.read_bytes()
            text = raw.decode('utf-8-sig')
            if 'SAMPLE_FIXTURE' in text:
                kind = 'SAMPLE_FIXTURE'
            report = validate_capture(text, evidence_kind=kind)
            if label == 'supplied_capture':
                hex_report = validate_hex_pairs(text)
                report['hex_validation'] = hex_report
                report['checks'].append(dict(check='hex_consistency', result=hex_report['result'],
                                             reason=f"{len(hex_report['pairs'])} JSON/HEX pairs; {len(hex_report['issues'])} issues. Packed 11-byte little-endian source format."))
                if hex_report['result'] == 'FAIL':
                    report['overall_result'] = 'FAIL'
            report.update(input_path=str(path.resolve()), input_file_sha256=hashlib.sha256(raw).hexdigest())
            (output / (label + '_input.txt')).write_bytes(raw)
            (output / (label + '.json')).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
            (output / (label + '.md')).write_text(render_summary(report), encoding='utf-8')
            captures[label] = dict(result=report['overall_result'], evidence_kind=kind,
                                   assessed_checks_failed=any(c['result'] == 'FAIL' for c in report['checks']))
        except (OSError, UnicodeError, ValueError) as exc:
            captures[label] = dict(result='FAIL', reason=str(exc), assessed_checks_failed=True)
    evidence = {
        'source_review': dict(result='PASS' if all(s['result'] == 'PASS' for s in sources.values()) else 'FAIL', reason='Hash agreement with reviewed files, not firmware execution.'),
        'actual_wokwi_execution': dict(result='NOT RUN', reason='Runner does not execute Wokwi; optional capture origin requires independent verification.'),
        'sensor_integration': dict(result='NOT ASSESSED', reason='Source uses mocked inputs; no HC-SR04 reads.'),
        'real_end_to_end': dict(result='NOT RUN', reason='No integrated hardware, network, backend, database or web access.'),
        'accuracy_and_latency': dict(result='NOT ASSESSED', reason='No labelled real trials or correlated comparable timestamps.'),
    }
    failed = completed.returncode != 0 or not trace_ok or evidence['source_review']['result'] == 'FAIL' or any(c['assessed_checks_failed'] for c in captures.values())
    report = dict(run_id=run_id, started_at=started, finished_at=datetime.now(timezone.utc).isoformat(),
                  command=[sys.executable, str(Path(__file__).resolve()), *(argv if argv is not None else sys.argv[1:])],
                  environment=dict(python=platform.python_version(), platform=platform.platform()),
                  overall='FAIL' if failed else 'LOCAL CHECKS PASS; SYSTEM NOT ASSESSED',
                  real_system_validated=False, local_summary=local['summary'],
                  test_id_consistency='PASS' if trace_ok else 'FAIL', sources=sources,
                  captures=captures, evidence=evidence)
    (output / 'validation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    lines = ['# Unified validation report', '', f'Run: {run_id}', f'Start (UTC): {started}',
             f'Overall: {report["overall"]}', '', 'Local tests: ' + json.dumps(local['summary']),
             '', '| Evidence/check | Result | Reason |', '|---|---|---|']
    lines += [f"| {name} | {value['result']} | {value['reason']} |" for name, value in evidence.items()]
    lines += ['', 'Capture checks: ' + json.dumps(captures), '', 'Source hash and test ID details: validation.json.',
              'PASS means the named local assertion passed; SKIP is a unittest skip with its recorded reason.',
              'NOT RUN means execution was not attempted; NOT ASSESSED means evidence cannot support the check.',
              'No unavailable real test is counted as a skipped automated test or as PASS.']
    (output / 'VALIDATION_REPORT.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    manifest = {}
    for path in ROOT.rglob('*'):
        if path.is_file() and not {'runs', 'history', '__pycache__'}.intersection(path.relative_to(ROOT).parts):
            manifest[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    (output / 'workspace_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(output=str(output), summary=local['summary'], overall=report['overall'])))
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
