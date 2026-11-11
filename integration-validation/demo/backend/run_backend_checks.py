"""Save isolated reference-backend tests and SQLite artifacts in a new evidence run."""
from contextlib import redirect_stdout,redirect_stderr
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sys
import unittest

here=Path(__file__).resolve().parent
output=here.parent/'evidence'/('backend-tests-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
output.mkdir(parents=True,exist_ok=False)
os.environ['BACKEND_TEST_EVIDENCE']=str(output)
os.environ['MQTT_TEST_EVIDENCE']=str(output)
# Existing transport test utilities are reused; their test classes are not rerun by this loader.
sys.path.insert(0,str(here.parent/'mqtt'))
suite=unittest.defaultTestLoader.discover(str(here),pattern='test_backend.py',top_level_dir=str(here))
with (output/'console.txt').open('w',encoding='utf-8') as stream,redirect_stdout(stream),redirect_stderr(stream):
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
summary=dict(run=result.testsRun,passed=result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
             failed=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
             command=[sys.executable,str(Path(__file__).resolve())])
(output/'results.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(dict(evidence=str(output),results=summary),indent=2))
raise SystemExit(0 if result.wasSuccessful() else 1)
