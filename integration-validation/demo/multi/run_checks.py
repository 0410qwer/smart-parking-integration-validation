from contextlib import redirect_stdout,redirect_stderr
from datetime import datetime,timezone
import json,os
from pathlib import Path
import unittest
HERE=Path(__file__).resolve().parent
output=HERE.parent/'evidence'/('multi-tests-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));output.mkdir()
os.environ['MULTI_TEST_EVIDENCE']=os.environ['MQTT_TEST_EVIDENCE']=str(output)
suite=unittest.defaultTestLoader.discover(str(HERE),pattern='test_multi.py',top_level_dir=str(HERE))
with (output/'console.txt').open('w',encoding='utf-8') as log,redirect_stdout(log),redirect_stderr(log):result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
summary=dict(run=result.testsRun,passed=result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),failed=len(result.failures),errors=len(result.errors),skipped=len(result.skipped))
(output/'results.json').write_text(json.dumps(summary,indent=2));print(json.dumps(dict(evidence=str(output),results=summary),indent=2))
raise SystemExit(0 if result.wasSuccessful() else 1)
