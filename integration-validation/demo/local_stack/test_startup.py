import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import time
import unittest
from urllib.request import urlopen

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent.parent.parent
OUTPUT=Path(os.environ['STACK_TEST_EVIDENCE'])
PS='C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe'

def wait(predicate,timeout=15):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            value=predicate()
            if value:return value
        except (OSError,ValueError):pass
        time.sleep(.1)
    raise AssertionError('Timed out waiting for launcher state')

def api(session,route='/api/availability'):
    from urllib.parse import urlsplit
    origin=urlsplit(session['url']);url=f'{origin.scheme}://{origin.netloc}'+route
    with urlopen(url,timeout=2) as response:return json.load(response)

class OwnedStack:
    def __init__(self,folder,mode='Reference',extra=None,database=None,stream='startup-test'):
        self.folder=Path(folder);self.folder.mkdir(parents=True)
        self.log=(self.folder/'launcher.txt').open('w',encoding='utf-8')
        self.database=database or self.folder/'parking.sqlite3'
        command=[PS,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'Start-LocalDemo.ps1'),
                 '-Mode',mode,'-BrokerPort','0','-HttpPort','0','-PythonPath',sys.executable,
                 '-SessionDirectory',str(self.folder),'-Database',str(self.database),'-StreamId',stream]
        command.extend(extra or [])
        self.process=subprocess.Popen(command,cwd=ROOT,stdout=self.log,stderr=subprocess.STDOUT)
    def ready(self):
        def read():
            if self.process.poll() is not None:raise AssertionError('Launcher exited; see '+str(self.folder/'launcher.txt'))
            if not (self.folder/'session.json').exists():return False
            data=json.loads((self.folder/'session.json').read_text())
            return data if data['status']=='ready' else False
        return wait(read)
    def stop(self):
        if self.process.poll() is None:
            subprocess.run([PS,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'Stop-LocalDemo.ps1'),
                            '-SessionDirectory',str(self.folder)],capture_output=True,text=True,check=True)
            self.process.wait(timeout=55)
        self.log.close()
        return json.loads((self.folder/'session.json').read_text()) if (self.folder/'session.json').exists() else None

class StartupTests(unittest.TestCase):
    def test_multi_one_command_three_sources_and_dashboard(self):
        stack=OwnedStack(OUTPUT/self._testMethodName,'Multi',['-Headless','-DemoCycle']);self.addCleanup(stack.stop)
        session=stack.ready()
        def complete():
            if stack.process.poll() is not None:raise AssertionError('Multi launcher exited; inspect logs')
            data=api(session)
            return data if [s['status'] for s in data['spaces']]==['occupied','available','occupied'] and all(s['online'] for s in data['spaces']) else None
        data=wait(complete,timeout=700);self.assertEqual(data['mode'],'MULTI_WOKWI_REFERENCE')
        result=subprocess.run(['node',str(HERE/'verify_stack.cjs'),str(stack.folder/'session.json')],capture_output=True,text=True)
        (stack.folder/'browser.txt').write_text(result.stdout+result.stderr);self.assertEqual(result.returncode,0)
        final=stack.stop();self.assertEqual(final['exit_code'],0);self.assertTrue(all(code==0 for code in final['child_exit_codes'].values()))

    def test_windows_manifest_sharing_violation_is_retried(self):
        from unittest.mock import patch
        from supervisor import write_manifest
        folder=OUTPUT/self._testMethodName;folder.mkdir()
        path=folder/'session.json';path.write_text('{}')
        original=os.replace;attempts=[]
        def shared(source,target):
            attempts.append(1)
            if len(attempts)<3:raise PermissionError('Injected Windows sharing violation')
            return original(source,target)
        with patch('supervisor.os.replace',side_effect=shared):write_manifest(path,{'status':'ready'})
        self.assertEqual(len(attempts),3);self.assertEqual(json.loads(path.read_text())['status'],'ready')

    def test_reference_one_command_seed_shutdown_and_restore(self):
        stack=OwnedStack(OUTPUT/self._testMethodName,extra=['-SeedCapture']);self.addCleanup(stack.stop)
        session=stack.ready();wait(lambda:api(session)['accepted']==22)
        final=stack.stop();self.assertEqual(final['exit_code'],0)
        self.assertTrue(all(code==0 for code in final['child_exit_codes'].values()))
        with socket.socket() as probe:self.assertNotEqual(probe.connect_ex(('127.0.0.1',session['http_port'])),0)
        with sqlite3.connect(stack.database) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0],22)
        restored=OwnedStack(OUTPUT/(self._testMethodName+'-restored'),database=stack.database);self.addCleanup(restored.stop)
        data=api(restored.ready());self.assertEqual(data['accepted'],22);self.assertFalse(data['spaces'][0]['fresh_this_connection'])

    def test_port_conflict_does_not_stop_an_existing_listener(self):
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0));listener.listen()
            result=subprocess.run([PS,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'Start-LocalDemo.ps1'),
                '-Mode','Reference','-BrokerPort',str(listener.getsockname()[1]),'-HttpPort','0','-PythonPath',sys.executable],capture_output=True,text=True)
            (OUTPUT/'port-conflict.txt').write_text(result.stdout+result.stderr)
            self.assertNotEqual(result.returncode,0);self.assertIn('already in use',result.stdout+result.stderr)
            with socket.create_connection(listener.getsockname(),timeout=1):pass

    def test_missing_python_has_clear_error(self):
        result=subprocess.run([PS,'-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'Start-LocalDemo.ps1'),
            '-PythonPath',str(OUTPUT/'missing-python.exe')],capture_output=True,text=True)
        (OUTPUT/'missing-python.txt').write_text(result.stdout+result.stderr)
        self.assertNotEqual(result.returncode,0);self.assertIn('Python executable missing',result.stdout+result.stderr)

    def test_replay_and_simulation_launcher_modes(self):
        for mode,expected in [('Replay','Captured Wokwi replay'),('Simulation','Simulation Mode')]:
            stack=OwnedStack(OUTPUT/(self._testMethodName+'-'+mode),mode);self.addCleanup(stack.stop)
            with urlopen(stack.ready()['url']) as response:self.assertIn(expected,response.read().decode())
            final=stack.stop();self.assertEqual(final['exit_code'],0)

    def test_live_one_command_virtual_cycle_database_and_real_browser(self):
        stack=OwnedStack(OUTPUT/self._testMethodName,'Live',['-Headless','-DemoCycle']);self.addCleanup(stack.stop)
        session=stack.ready()
        def cycle_done():
            if stack.process.poll() is not None:raise AssertionError('Live launcher exited; inspect '+str(stack.folder/'live-bridge.txt'))
            return (Path(session['bridge_output'])/'demo-cycle-complete.json').exists()
        wait(cycle_done,timeout=700)
        data=api(session);self.assertGreaterEqual(data['accepted'],3)
        self.assertEqual(data['spaces'][0]['status'],'available');self.assertFalse(data['replay'])
        result=subprocess.run(['node',str(HERE/'verify_stack.cjs'),str(stack.folder/'session.json')],capture_output=True,text=True)
        (stack.folder/'browser.txt').write_text(result.stdout+result.stderr);self.assertEqual(result.returncode,0)
        with sqlite3.connect(stack.database) as db:
            states=[row[0] for row in db.execute('SELECT occupied FROM events ORDER BY id')]
        self.assertIn(1,states);self.assertEqual(states[-1],0)
        final=stack.stop();self.assertEqual(final['exit_code'],0)
        self.assertTrue(all(code==0 for code in final['child_exit_codes'].values()))

    def test_live_cancel_during_startup_cleans_owned_services(self):
        stack=OwnedStack(OUTPUT/self._testMethodName,'Live',['-Headless']);self.addCleanup(stack.stop)
        session=stack.ready();final=stack.stop()
        self.assertEqual(final['exit_code'],0)
        self.assertNotIn('bridge_stop_timeout',final)
        with socket.socket() as probe:self.assertNotEqual(probe.connect_ex(('127.0.0.1',session['broker_port'])),0)
