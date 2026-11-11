from datetime import datetime,timezone
import json,os,re,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
output=HERE.parent/'evidence'/('multi-browser-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));output.mkdir()
env=dict(os.environ,MULTI_BROWSER_OUTPUT=str(output))
with (output/'console.tap').open('w',encoding='utf-8') as log:
    result=subprocess.run(['node','--test','--test-reporter=tap',str(HERE/'browser.test.cjs')],env=env,stdout=log,stderr=subprocess.STDOUT,timeout=900)
counts={k:int(v) for k,v in re.findall(r'^# (tests|pass|fail|skipped|cancelled) (\d+)',(output/'console.tap').read_text(),re.MULTILINE)}
(output/'results.json').write_text(json.dumps(dict(exit_code=result.returncode,**counts),indent=2))
print(json.dumps(dict(evidence=str(output),exit_code=result.returncode,**counts),indent=2));raise SystemExit(result.returncode)
