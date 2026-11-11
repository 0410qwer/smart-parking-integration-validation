"""Foreground owner of local child services. No unknown PID killing or automatic installs."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import queue
import shutil
import socket
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from urllib.request import urlopen

HERE=Path(__file__).resolve().parent
DEMO=HERE.parent
ROOT=DEMO.parent.parent
FLAGS=(subprocess.CREATE_NEW_PROCESS_GROUP|subprocess.CREATE_NO_WINDOW) if os.name=='nt' else 0

def write_manifest(path,data):
    pending=path.with_suffix('.pending')
    pending.write_text(json.dumps(data,indent=2),encoding='utf-8')
    deadline=time.monotonic()+2
    while True:
        try:os.replace(pending,path);return
        except PermissionError:
            if time.monotonic()>=deadline:raise
            time.sleep(.025)  # Windows readers may briefly hold the destination without delete-sharing.

def check_port(port):
    if not 0<=port<=65535:raise ValueError('Port must be 0..65535')
    with socket.socket() as probe:
        if os.name=='nt':probe.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
        try:probe.bind(('127.0.0.1',port))
        except OSError as exc:raise RuntimeError(f'Port {port} is already in use; choose a different port or 0. No existing service was stopped.') from exc

def preflight(mode,broker_port,http_port):
    node=shutil.which('node')
    if not node:raise RuntimeError('Node.js missing; install Node before launching')
    for file in (ROOT/'smart-parking-web/app.js',ROOT/'smart-parking-web/index.html',ROOT/'smart-parking-web/style.css'):
        if not file.is_file():raise RuntimeError('Missing frontend file: '+str(file))
    if mode in ('Multi','Live','Reference','Memory'):
        if not (DEMO/'mqtt/node_modules/aedes/package.json').is_file():raise RuntimeError('Broker dependency missing: npm.cmd ci --prefix integration-validation/demo/mqtt')
        if not (DEMO/'mqtt/vendor/paho/mqtt/client.py').is_file():raise RuntimeError('Paho missing: pip install --target integration-validation/demo/mqtt/vendor -r integration-validation/demo/mqtt/requirements.txt')
        check_port(broker_port)
    if mode in ('Multi','Live'):
        if not (DEMO/'browser/node_modules/playwright/package.json').is_file():raise RuntimeError('Playwright missing: npm.cmd ci --prefix integration-validation/demo/browser')
        if os.name=='nt' and not any(Path(p).is_file() for p in ('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe','C:/Program Files/Microsoft/Edge/Application/msedge.exe')):
            raise RuntimeError('Microsoft Edge is required for Live mode')
    check_port(http_port)
    if broker_port and broker_port==http_port and mode in ('Multi','Live','Reference','Memory'):
        raise RuntimeError('Broker and HTTP ports must be different')
    return node

class Child:
    def __init__(self,name,command,folder):
        self.name,self.command=name,command
        self.ready=queue.Queue()
        self.log=(folder/(name+'.txt')).open('a',encoding='utf-8')
        self.process=subprocess.Popen(command,cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
            text=True,encoding='utf-8',creationflags=FLAGS)
        self.thread=threading.Thread(target=self.read,daemon=True);self.thread.start()
    def read(self):
        for line in self.process.stdout:
            self.log.write(line);self.log.flush()
            try:
                record=json.loads(line)
                if record.get('event') in ('listening','ready'):self.ready.put(record)
            except ValueError:pass
    def wait_ready(self,timeout=12):
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if self.process.poll() is not None:raise RuntimeError(self.name+' exited; inspect its session log')
            try:return self.ready.get(timeout=.1)
            except queue.Empty:pass
        raise TimeoutError(self.name+' readiness timeout; inspect session logs')
    def stop(self,timeout=10):
        if self.process.poll() is None:
            try:self.process.stdin.write('stop\n');self.process.stdin.flush();self.process.stdin.close()
            except (BrokenPipeError,OSError):pass
            try:self.process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.process.terminate();self.process.wait(timeout=5)
        self.thread.join(timeout=2);self.process.stdout.close();self.log.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['Multi','Live','Reference','Memory','Replay','Simulation'],default='Multi')
    parser.add_argument('--broker-port',type=int,default=18890)
    parser.add_argument('--http-port',type=int,default=8780)
    parser.add_argument('--session-directory')
    parser.add_argument('--database')
    parser.add_argument('--stream')
    parser.add_argument('--duration',type=float,default=0)
    parser.add_argument('--headless',action='store_true')
    parser.add_argument('--seed-capture',action='store_true')
    parser.add_argument('--demo-cycle',action='store_true')
    args=parser.parse_args()
    if args.duration<0:raise ValueError('Duration must be >=0')
    node=preflight(args.mode,args.broker_port,args.http_port)
    if args.seed_capture and args.mode!='Reference':raise ValueError('--seed-capture is only for explicitly labelled Reference replay mode')
    stream=args.stream or 'session-'+uuid.uuid4().hex[:16]
    database=Path(args.database or HERE/('data/multi-demo.sqlite3' if args.mode=='Multi' else 'data/local-demo.sqlite3')).resolve()
    if database.exists() and (args.mode in ('Multi','Live') or args.seed_capture):
        with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as db:
            try:count=db.execute('SELECT SUM(accepted) FROM streams WHERE stream_id IN (?,?,?,?)',(stream,stream+'_A01',stream+'_A02',stream+'_A03')).fetchone()
            except sqlite3.Error:count=None
            if count and count[0]:raise ValueError('This stream already contains events; choose a NEW stream for a restarted sensor or capture replay')
    folder=Path(args.session_directory).resolve() if args.session_directory else DEMO/'evidence'/('local-session-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    folder.mkdir(parents=True,exist_ok=True)
    manifest=folder/'session.json'
    if manifest.exists():raise ValueError('Session directory already has a manifest; choose a new session directory')
    status=dict(mode=args.mode,stream=stream,database=str(database),session_directory=str(folder),status='starting',owned_children=[])
    def save():
        write_manifest(manifest,status)
    children=[];bridge=None;publisher=None;exit_code=0
    def add(name,command):
        child=Child(name,command,folder);children.append(child)
        status['owned_children'].append(dict(name=name,pid=child.process.pid,command=command));save();return child
    try:
        save();mqtt_port=0
        if args.mode in ('Multi','Live','Reference','Memory'):
            broker=add('broker',[node,str(HERE/'managed_broker.mjs'),str(args.broker_port),str(folder/'broker.jsonl')])
            mqtt_port=broker.wait_ready()['port']
        backend=add('backend',[sys.executable,str(HERE/'managed_backend.py'),'--mode',args.mode,'--mqtt-port',str(mqtt_port),
            '--port',str(args.http_port),'--db',str(database),'--stream',stream,'--log',str(folder/'backend.jsonl')])
        http_port=backend.wait_ready()['port']
        page={'Multi':'/backend/','Live':'/backend/','Reference':'/backend/','Memory':'/mqtt/','Replay':'/','Simulation':'/simulation/'}[args.mode]
        status.update(status='ready',broker_port=mqtt_port,http_port=http_port,url=f'http://127.0.0.1:{http_port}'+page)
        if args.mode in ('Multi','Live'):
            bridge_folder=folder/'bridge';bridge_folder.mkdir()
            command=[node,str(DEMO/('multi/run_live.cjs' if args.mode=='Multi' else 'live/run_live.cjs')),'--mqtt-port',str(mqtt_port),'--output',str(bridge_folder)]
            if args.mode=='Multi':command.extend(['--session',stream])
            if not args.headless:command.append('--headed')
            if args.demo_cycle:command.append('--demo-cycle')
            bridge=add('live-bridge',command);status['bridge_output']=str(bridge_folder)
        if args.seed_capture:
            publisher=add('capture-publisher',[sys.executable,str(DEMO/'mqtt/publish_capture.py'),'--port',str(mqtt_port),'--interval','.02','--log',str(folder/'publisher.jsonl')])
        save();print(json.dumps(dict(event='ready',**status)),flush=True)
        if args.mode in ('Multi','Live'):print('Services ready; live sensor data waits for Wokwi compilation. Health will show its actual status.',flush=True)
        print('Dashboard: '+status['url']+' | Stop: Ctrl+C or Stop-LocalDemo.ps1 -SessionDirectory "'+str(folder)+'"',flush=True)
        started=time.monotonic()
        while True:
            if (folder/'stop.request').exists() or (args.duration and time.monotonic()-started>=args.duration):break
            for child in children:
                code=child.process.poll()
                if code is not None and child is not publisher:
                    raise RuntimeError(child.name+f' exited ({code}); inspect session logs')
                if child is publisher and code not in (None,0):raise RuntimeError('Capture publisher failed')
            time.sleep(.2)
    except KeyboardInterrupt:
        status['stop_reason']='keyboard_interrupt'
    except Exception as exc:
        status['error']=str(exc);exit_code=1
    finally:
        status['status']='stopping'
        try:save()
        except OSError as exc:status['manifest_error']=str(exc);exit_code=1
        if bridge:
            Path(status['bridge_output'],'stop.request').touch()
            try:bridge.process.wait(timeout=45)
            except subprocess.TimeoutExpired:
                status['bridge_stop_timeout']=True;exit_code=1
        for child in reversed(children):
            try:child.stop()
            except (OSError,subprocess.TimeoutExpired) as exc:
                status.setdefault('shutdown_errors',[]).append(child.name+': '+str(exc));exit_code=1
        status.update(status='stopped',exit_code=exit_code,child_exit_codes={c.name:c.process.returncode for c in children})
        try:save()
        except OSError as exc:print('Manifest update failed after service cleanup: '+str(exc),file=sys.stderr);exit_code=1
        print(json.dumps(dict(event='stopped',session=str(manifest),exit_code=exit_code)),flush=True)
    return exit_code

if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,RuntimeError,OSError) as exc:print('STARTUP ERROR: '+str(exc),file=sys.stderr);raise SystemExit(1)
