from contextlib import redirect_stdout,redirect_stderr
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
HERE=Path(__file__).resolve().parent
output=HERE.parent/'evidence'/('live-tests-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));output.mkdir(parents=True)
os.environ['LIVE_TEST_EVIDENCE']=os.environ['MQTT_TEST_EVIDENCE']=str(output)
suite=unittest.defaultTestLoader.discover(str(HERE),pattern='test_live.py',top_level_dir=str(HERE))
with (output/'python.txt').open('w',encoding='utf-8') as stream,redirect_stdout(stream),redirect_stderr(stream):
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
node=subprocess.run(['node','--test','--test-reporter=tap',str(HERE/'bridge.test.cjs')],capture_output=True,text=True,encoding='utf-8')
(output/'node.tap').write_text(node.stdout+node.stderr,encoding='utf-8')
import re
counts={k:int(v) for k,v in re.findall(r'^# (tests|pass|fail|skipped|cancelled) (\d+)',node.stdout,re.MULTILINE)}
summary=dict(python=dict(run=result.testsRun,passed=result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
    failed=len(result.failures),errors=len(result.errors),skipped=len(result.skipped)),node=counts,node_exit_code=node.returncode)
(output/'results.json').write_text(json.dumps(summary,indent=2));print(json.dumps(dict(evidence=str(output),results=summary),indent=2))
raise SystemExit(0 if result.wasSuccessful() and node.returncode==0 else 1)
