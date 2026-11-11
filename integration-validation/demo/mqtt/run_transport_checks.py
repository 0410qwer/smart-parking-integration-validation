"""Preserve new MQTT unit/real-broker test evidence on every run."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import unittest

HERE=Path(__file__).resolve().parent
output=HERE.parent/'evidence'/('mqtt-tests-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
output.mkdir(parents=True,exist_ok=False)
os.environ['MQTT_TEST_EVIDENCE']=str(output)
suite=unittest.defaultTestLoader.discover(str(HERE),pattern='test_transport.py',top_level_dir=str(HERE))
with (output/'console.txt').open('w',encoding='utf-8') as stream:
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
summary=dict(run=result.testsRun,passed=result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
             failed=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
             command=[sys.executable,str(Path(__file__).resolve())])
(output/'results.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(dict(evidence=str(output),results=summary),indent=2))
raise SystemExit(0 if result.wasSuccessful() else 1)
