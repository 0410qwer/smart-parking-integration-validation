"""Compile actual firmware for host checks, then validate real Wokwi capture evidence."""
from datetime import datetime,timezone
from contextlib import redirect_stdout,redirect_stderr
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

here=Path(__file__).resolve().parent
output=here.parent/'evidence'/('sensor-tests-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
output.mkdir(parents=True,exist_ok=False)
env=dict(os.environ,ZIG_GLOBAL_CACHE_DIR=str(here/'tools'/'zig-cache'),MQTT_TEST_EVIDENCE=str(output),SENSOR_TEST_EVIDENCE=str(output))
os.environ.update({k:env[k] for k in ('MQTT_TEST_EVIDENCE','SENSOR_TEST_EVIDENCE')})
compiler=here/'tools'/'ziglang'/'zig.exe'
command=[str(compiler),'c++','-std=c++17','-I'+str(here/'host'),str(here/'host'/'main.cpp'),'-o',str(output/'host-test.exe'),'-lc++']
compile_result=subprocess.run(command,env=env,capture_output=True,text=True)
(output/'compile.txt').write_text(compile_result.stdout+compile_result.stderr)
if compile_result.returncode:raise SystemExit('Compiler failed: '+str(output/'compile.txt'))
host=subprocess.run([str(output/'host-test.exe')],capture_output=True,text=True)
(output/'host-synthetic-fixture.txt').write_text(host.stdout+host.stderr)
native_pass=sum(line.startswith(('[SELFTEST] PASS','[HOST] PASS')) for line in host.stdout.splitlines())
native_fail=sum(line.startswith(('[SELFTEST] FAIL','[HOST] FAIL')) for line in host.stdout.splitlines())
suite=unittest.defaultTestLoader.discover(str(here),pattern='test_sensor.py',top_level_dir=str(here))
with (output/'python.txt').open('w',encoding='utf-8') as stream,redirect_stdout(stream),redirect_stderr(stream):
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
summary=dict(native=dict(passed=native_pass,failed=native_fail,exit_code=host.returncode),
             python=dict(run=result.testsRun,passed=result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
                         failed=len(result.failures),errors=len(result.errors),skipped=len(result.skipped)),compile_command=command)
(output/'results.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(dict(evidence=str(output),results=summary),indent=2))
raise SystemExit(0 if result.wasSuccessful() and native_pass==21 and native_fail==0 and host.returncode==0 else 1)
