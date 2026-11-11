"""Run existing and demo suites into a new evidence directory; preserve old reports."""
import hashlib
import json
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import platform
import re
import subprocess
import sys
import unittest
from datetime import datetime, timezone
from server import ROOT, FRONTEND, CAPTURE, load_capture, snapshot


def main():
    output = Path(__file__).parent / 'evidence' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    output.mkdir(parents=True, exist_ok=False)
    results = {}
    for name, folder in [('existing', ROOT), ('demo', Path(__file__).parent)]:
        suite = unittest.defaultTestLoader.discover(str(folder), pattern='test_*.py', top_level_dir=str(folder))
        with (output / (name + '.txt')).open('w', encoding='utf-8') as stream, redirect_stdout(stream), redirect_stderr(stream):
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
        results[name] = dict(run=result.testsRun, passed=result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
                             failed=len(result.failures), errors=len(result.errors), skipped=len(result.skipped))
    command = ['node', '--test', '--test-reporter=tap', str(Path(__file__).with_name('test_frontend.cjs'))]
    node = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
    (output / 'frontend.txt').write_text(node.stdout + node.stderr, encoding='utf-8')
    results['frontend_exit_code'] = node.returncode
    results['frontend'] = {key: int(value) for key, value in re.findall(r'^# (tests|pass|fail|skipped|cancelled) (\d+)', node.stdout, re.MULTILINE)}
    results['environment'] = dict(python=sys.version, executable=sys.executable, platform=platform.platform())
    results['commands'] = dict(python=[sys.executable, str(Path(__file__).resolve())], frontend=command,
                               discovery=[str(ROOT), str(Path(__file__).parent)])
    report = load_capture(CAPTURE.read_text(encoding='utf-8-sig'))
    (output / 'capture_validation.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    (output / 'snapshots.json').write_text(json.dumps([snapshot(report, n) for n in (0,1,5,6,13,21,22)], indent=2), encoding='utf-8')
    files = [CAPTURE, *(FRONTEND / name for name in ('index.html','app.js','style.css'))]
    results['sha256'] = {str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in files}
    (output / 'results.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps(dict(evidence=str(output), results=results), indent=2))
    return int(node.returncode != 0 or any(results[n]['failed'] or results[n]['errors'] for n in ('existing','demo')))


if __name__ == '__main__':
    raise SystemExit(main())
