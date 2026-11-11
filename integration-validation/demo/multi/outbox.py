"""Durable local transport outbox for newly observed live Serial data; not a capture player."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import threading
import time
import uuid
from model import prefix,MAPPING,mqtt,client_id,parse_event_json,ReceivedState

class Outbox:
    def __init__(self,path):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True);self.lock=threading.RLock()
        with self.db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY,serial_index INTEGER UNIQUE,
                spot_id INTEGER NOT NULL,raw TEXT NOT NULL,observed_at REAL NOT NULL,delivery_key TEXT UNIQUE,
                state TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,last_error TEXT)''')
            db.execute('CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
            db.execute("INSERT OR IGNORE INTO metadata VALUES ('bridge_id',?)",(uuid.uuid4().hex,))
            self.bridge_id=db.execute("SELECT value FROM metadata WHERE key='bridge_id'").fetchone()[0]
    def db(self):
        # Connections are short-lived and explicitly closed by callers via this context manager.
        from contextlib import contextmanager
        @contextmanager
        def opened():
            db=sqlite3.connect(self.path,timeout=5);db.row_factory=sqlite3.Row
            try:
                db.execute('PRAGMA journal_mode=WAL');db.execute('PRAGMA synchronous=FULL')
                with db:yield db
            finally:db.close()
        return opened()
    def enqueue(self,request):
        raw=request['raw'];index=request['serial_index'];spot=parse_event_json(raw).get('spot_id')
        if spot not in MAPPING or type(index) is not int or index<0 or len(raw)>4096:raise ValueError('Invalid source/index/size')
        event=parse_event_json(raw)
        if set(event)!={'spot_id','occupied','batt_mv','status','ctr','heartbeat'}:raise ValueError('Six fields required')
        if ReceivedState().receive(raw.encode())!='accepted':raise ValueError('Invalid source fields')
        key=f'{spot}/events/{self.bridge_id}/{index}'
        with self.lock,self.db() as db:
            old=db.execute('SELECT raw FROM outbox WHERE serial_index=?',(index,)).fetchone()
            if old and old[0]!=raw:raise ValueError('Serial identity collision; start a new source session')
            db.execute('INSERT OR IGNORE INTO outbox(serial_index,spot_id,raw,observed_at,delivery_key) VALUES (?,?,?,?,?)',
                       (index,spot,raw,request['observed_at'],key))
        return key
    def head(self,spot):
        with self.lock,self.db() as db:
            row=db.execute("SELECT * FROM outbox WHERE spot_id=? AND state='pending' ORDER BY serial_index LIMIT 1",(spot,)).fetchone()
            return dict(row) if row else None
    def update(self,key,state=None,error=None,attempt=False):
        with self.lock,self.db() as db:
            db.execute('UPDATE outbox SET state=COALESCE(?,state),last_error=?,attempts=attempts+? WHERE delivery_key=?',
                       (state,error,int(attempt),key))
    def counts(self,spot):
        with self.lock,self.db() as db:
            return {r[0]:r[1] for r in db.execute('SELECT state,COUNT(*) FROM outbox WHERE spot_id=? GROUP BY state',(spot,))}

class Worker:
    def __init__(self,port,session,outbox,folder):
        self.prefix=prefix(session);self.outbox=outbox;self.folder=Path(folder)
        self.stop_event=threading.Event();self.connected=threading.Event();self.subscribed=threading.Event()
        self.signals={spot:dict(state='untrusted') for spot in MAPPING};self.paused=set();self.acks={};self.ack_lock=threading.Lock();self.log_lock=threading.Lock()
        self.client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id=client_id('multi-pub-'),protocol=mqtt.MQTTv311,clean_session=True)
        self.client.reconnect_delay_set(1,2)
        # Non-retained health will shared by all three channels; subscriber also has per-source TTL.
        self.client.will_set(self.prefix+'/1001/health',json.dumps(dict(state='offline')),qos=1,retain=False)
        self.client.on_connect=lambda c,u,f,r,p:c.subscribe(self.prefix+'/ack',qos=1) if not r.is_failure else None
        self.client.on_subscribe=self.on_subscribe
        self.client.on_disconnect=lambda *args:self.connected.clear()
        self.client.on_message=self.ack
        self.client.connect_async('127.0.0.1',port,keepalive=5);self.client.loop_start()
        if not self.connected.wait(5):
            self.client.disconnect();self.client.loop_stop()
            raise TimeoutError('Outbox publisher did not connect/subscribe')
        self.threads=[threading.Thread(target=self.deliver,args=(spot,),daemon=True) for spot in MAPPING]
        self.threads.append(threading.Thread(target=self.health_loop,daemon=True))
        for thread in self.threads:thread.start()
    def log(self,event,**fields):
        try:
            with self.log_lock,(self.folder/'delivery.jsonl').open('a',encoding='utf-8') as log:
                log.write(json.dumps(dict(at=time.time(),event=event,**fields))+'\n')
        except OSError as exc:
            # Optional text evidence must not kill a worker after a durable DB commit.
            self.journal_warning=str(exc)
    def on_subscribe(self,client,userdata,mid,reasons,properties):
        if reasons and not any(reason.is_failure for reason in reasons):self.connected.set()
        else:self.connected.clear()
    def ack(self,c,u,message):
        try:
            if len(message.payload)>4096:raise ValueError('Oversize acknowledgement')
            data=json.loads(message.payload);key=data['delivery_key']
            if not isinstance(key,str) or data.get('outcome') not in ('accepted','duplicate','rejected'):raise ValueError('Invalid acknowledgement')
            identity=data.get('event_id')
            if 'event_id' not in data or (identity is not None and (type(identity) is not int or identity<1)):raise ValueError('Invalid event identity')
            if data['outcome'] in ('accepted','duplicate') and (type(identity) is not int or identity<1):raise ValueError('Invalid committed identity')
            with self.ack_lock:
                if key in self.acks:self.acks[key]['data']=data;self.acks[key]['event'].set()
        except (ValueError,KeyError,TypeError,UnicodeError):pass
    def read_control(self):
        file=self.folder/'control.json'
        if file.exists():
            try:self.paused=set(json.loads(file.read_text()).get('paused_ids',[]))
            except (ValueError,OSError):pass
    def deliver(self,spot):
        while not self.stop_event.is_set():
            self.read_control()
            row=self.outbox.head(spot)
            if not row or spot in self.paused or not self.connected.is_set():self.stop_event.wait(.1);continue
            key=row['delivery_key'];pending=dict(event=threading.Event(),data=None)
            with self.ack_lock:self.acks[key]=pending
            try:
                self.outbox.update(key,attempt=True)
                self.log('mqtt_publish_started',delivery_key=key,spot_id=spot,publish_wall_ms=time.time_ns()/1000000)
                info=self.client.publish(self.prefix+'/'+key,row['raw'],qos=1,retain=False);info.wait_for_publish(timeout=3)
                if not info.is_published():raise TimeoutError('Broker PUBACK timeout')
                if not pending['event'].wait(3):raise TimeoutError('Backend commit ACK timeout')
                ack=pending['data'];status='delivered' if ack['outcome'] in ('accepted','duplicate') else 'quarantined'
                self.outbox.update(key,state=status,error=ack.get('reason'))
                self.log('backend_commit_ack',delivery_key=key,spot_id=spot,outcome=ack['outcome'],event_id=ack['event_id'])
            except (RuntimeError,TimeoutError) as exc:
                self.outbox.update(key,error=str(exc));self.log('retry_pending',spot_id=spot,delivery_key=key,error=str(exc));self.stop_event.wait(.4)
            finally:
                with self.ack_lock:self.acks.pop(key,None)
    def publish_health(self,spot,state=None):
        data=dict(self.signals[spot]);data['state']=state or ('offline' if spot in self.paused else data['state'])
        data['pending']=self.outbox.counts(spot).get('pending',0)
        self.client.publish(self.prefix+f'/{spot}/health',json.dumps(data),qos=1,retain=False)
    def health_loop(self):
        while not self.stop_event.is_set():
            self.read_control()
            if self.connected.is_set():
                for spot in MAPPING:self.publish_health(spot)
            self.stop_event.wait(1)
    def stop(self):
        self.stop_event.set()
        for thread in self.threads:thread.join(timeout=4)
        if self.connected.is_set():
            for spot in MAPPING:
                info=self.client.publish(self.prefix+f'/{spot}/health',json.dumps(dict(state='offline')),qos=1,retain=False)
                try:info.wait_for_publish(timeout=2)
                except RuntimeError:pass
        self.client.disconnect();self.client.loop_stop()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mqtt-port',type=int,required=True);parser.add_argument('--session',required=True)
    parser.add_argument('--journal',required=True);args=parser.parse_args()
    folder=Path(args.journal).parent;outbox=Outbox(folder/'outbox.sqlite3');worker=Worker(args.mqtt_port,args.session,outbox,folder)
    try:
        print(json.dumps(dict(ready=True,input_mode='LIVE_MULTI_WOKWI',replay=False)),flush=True)
        for line in sys.stdin:
            try:
                request=json.loads(line)
                if request.get('kind')=='health':
                    for spot in MAPPING:
                        signal=request['sources'].get(str(spot))
                        if signal:worker.signals[spot]=signal
                    response=dict(ok=True,kind='health')
                else:response=dict(ok=True,delivery_key=outbox.enqueue(request),durably_queued=True)
                if request.get('kind')!='health':worker.log('outbox_queued',delivery_key=response['delivery_key'],queued_wall_ms=time.time_ns()/1000000)
            except (ValueError,KeyError,TypeError) as exc:response=dict(ok=False,error=str(exc))
            print(json.dumps(response),flush=True)
    finally:worker.stop()

if __name__=='__main__':main()
