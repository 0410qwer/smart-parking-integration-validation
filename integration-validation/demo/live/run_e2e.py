"""Isolated real Wokwi → live Serial → real MQTT → SQLite → Edge Dashboard test."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
from http.server import ThreadingHTTPServer
HERE=Path(__file__).resolve().parent
output=HERE.parent/'evidence'/('live-browser-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'));output.mkdir(parents=True)
os.environ['MQTT_TEST_EVIDENCE']=str(output)
sys.path.insert(0,str(HERE.parent/'mqtt'))
from test_transport import Broker
from live_backend import LiveState,LiveSubscriber,live_handler
from transport import Journal
broker=Broker('live-wokwi-broker').start()
state=LiveState(output/'live.sqlite3','live-test',journal=Journal(output/'backend.jsonl'))
sub=LiveSubscriber(state,broker.port)
http=None
try:
    if not sub.start():raise RuntimeError('Live test subscriber failed SUBACK')
    http=ThreadingHTTPServer(('127.0.0.1',0),live_handler(state))
    threading.Thread(target=http.serve_forever,daemon=True).start()
    env=dict(os.environ,LIVE_TEST_OUTPUT=str(output),LIVE_TEST_URL=f'http://127.0.0.1:{http.server_port}',LIVE_MQTT_PORT=str(broker.port),PARKING_PYTHON=sys.executable)
    command=['node','--test','--test-reporter=tap',str(HERE/'verify_live.cjs')]
    with (output/'console.tap').open('w',encoding='utf-8') as stream:
        result=subprocess.run(command,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=800)
    log=(output/'console.tap').read_text(encoding='utf-8')
    counts={k:int(v) for k,v in re.findall(r'^# (tests|pass|fail|cancelled|skipped) (\d+)',log,re.MULTILINE)}
    summary=dict(command=command,exit_code=result.returncode,**counts)
    (output/'results.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(dict(evidence=str(output),results=summary),indent=2))
finally:
    if http:http.shutdown();http.server_close()
    sub.stop();broker.stop()
raise SystemExit(result.returncode)
