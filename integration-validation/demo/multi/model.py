"""Isolated multi-source reference backend; not Saaket's production implementation."""
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import threading
import time
import uuid
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'backend'))
sys.path.insert(0,str(HERE.parent/'mqtt'))
from store import PersistentState
from transport import Journal,ReceivedState,MAPPING,utcnow,mqtt,client_id
from simulation_validator import parse_event_json

SOURCE_TYPE='Wokwi HC-SR04 (virtual)'
def prefix(session):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,48}',session):raise ValueError('Invalid session namespace')
    return 'smart-parking/integration-test/multi/'+session

class NodeState(PersistentState):
    def __init__(self,path,session,spot,journal):
        self.spot=spot
        super().__init__(path,session+'_'+MAPPING[spot],topic=prefix(session)+f'/{spot}/events',journal=journal)
        with self.db() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS delivery_keys(delivery_key TEXT PRIMARY KEY,
                stream_id TEXT NOT NULL,raw_hash TEXT NOT NULL,outcome TEXT NOT NULL,event_id INTEGER)''')

    def delivery(self,raw,key,topic,qos=1,retained=False,dup=False,mid=None):
        if len(key)>180:raise ValueError('Delivery key too long')
        fingerprint=hashlib.sha256(raw).hexdigest()
        with self.lock,self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            prior=db.execute('SELECT * FROM delivery_keys WHERE delivery_key=?',(key,)).fetchone()
            stream=db.execute('SELECT * FROM streams WHERE stream_id=?',(self.stream_id,)).fetchone()
            event_id=None;reason=None;now=utcnow()
            if prior:
                if prior['raw_hash']!=fingerprint or prior['stream_id']!=self.stream_id:
                    outcome='rejected';reason='Delivery identity reused with different data'
                else:
                    outcome='duplicate' if prior['outcome'] in ('accepted','duplicate') else 'rejected'
                    event_id=prior['event_id'];reason='Repeated transport delivery'
            else:
                logs=[];candidate=ReceivedState(lambda event,**fields:logs.append(dict(event=event,**fields)))
                candidate.previous=json.loads(stream['last_payload_json']) if stream['last_payload_json'] else None
                try:
                    payload=parse_event_json(raw.decode('utf-8'))
                    if payload.get('spot_id')!=self.spot or set(payload)!={'spot_id','occupied','batt_mv','status','ctr','heartbeat'}:
                        raise ValueError('Source/topic mapping or field mismatch')
                    outcome=candidate.receive(raw,topic=topic,qos=qos,retained=retained)
                    reason=logs[-1].get('error') if logs else None
                except (ValueError,UnicodeError) as exc:outcome='rejected';reason=str(exc)
                if outcome=='accepted':
                    event=candidate.previous;canonical=json.dumps(event,sort_keys=True,separators=(',',':'))
                    cursor=db.execute('''INSERT INTO events(event_uuid,stream_id,ordinal,spot_id,occupied,status,batt_mv,ctr,heartbeat,
                        payload_json,raw_payload,topic,qos,retained,mqtt_dup,mqtt_mid,source_timestamp,received_at,backend_run,connection_epoch)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,?,?,?)''',
                        (uuid.uuid4().hex,self.stream_id,stream['accepted']+1,self.spot,int(event['occupied']),event['status'],event['batt_mv'],
                         event['ctr'],int(event['heartbeat']),canonical,raw,topic,qos,int(retained),int(dup),mid,now,self.run,self.epoch))
                    event_id=cursor.lastrowid
                    db.execute('INSERT INTO bay_current(stream_id,spot_id,event_id) VALUES (?,?,?) ON CONFLICT(stream_id,spot_id) DO UPDATE SET event_id=excluded.event_id',
                               (self.stream_id,self.spot,event_id))
                    db.execute('UPDATE streams SET accepted=?,last_payload_json=?,last_event_id=? WHERE stream_id=?',
                               (stream['accepted']+1,canonical,event_id,self.stream_id))
                elif outcome=='duplicate':event_id=stream['last_event_id']
                db.execute('INSERT INTO delivery_keys VALUES (?,?,?,?,?)',(key,self.stream_id,fingerprint,outcome,event_id))
            db.execute('''INSERT INTO receipts(receipt_uuid,stream_id,outcome,event_id,reason,raw_payload,raw_size,
                topic,qos,retained,mqtt_dup,mqtt_mid,received_at,backend_run,connection_epoch) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (uuid.uuid4().hex,self.stream_id,outcome,event_id,reason,raw[:4096],len(raw),topic,qos,int(retained),int(dup),mid,now,self.run,self.epoch))
        self.journal('multi_delivery_committed',spot_id=self.spot,delivery_key=key,outcome=outcome,event_id=event_id)
        return dict(delivery_key=key,outcome=outcome,event_id=event_id,spot_id=self.spot,reason=reason)

class MultiState:
    def __init__(self,database,session,journal=None,health_timeout=8):
        self.session=session;self.prefix=prefix(session);self.journal_warning=None
        sink=journal or Journal()
        def safe_journal(event,**fields):
            try:sink(event,**fields)
            except OSError as exc:self.journal_warning=str(exc)
        self.journal=safe_journal
        self.nodes={spot:NodeState(database,session,spot,self.journal) for spot in MAPPING}
        self.connected=False;self.health_timeout=health_timeout
        self.lock=threading.RLock();self.signals={};self.fresh={spot:False for spot in MAPPING}

    def connection(self,connected):
        with self.lock:
            self.connected=connected
            for spot,node in self.nodes.items():node.connection(connected);self.fresh[spot]=False

    def signal(self,spot,data):
        if not isinstance(data,dict) or data.get('state') not in ('online','offline','untrusted','stalled'):raise ValueError('Invalid source health')
        for field in ('pending','distance_mm','echo_us'):
            value=data.get(field)
            if value is not None and (type(value) is not int or not 0<=value<=10000000):raise ValueError('Invalid health '+field)
        if data.get('observed_at') is not None and (not isinstance(data['observed_at'],str) or len(data['observed_at'])>80):raise ValueError('Invalid health observation time')
        with self.lock:
            self.signals[spot]=dict(data,seen=time.monotonic())
            if data['state']!='online':self.fresh[spot]=False

    def ingest(self,spot,raw,key,topic,**metadata):
        with self.lock:
            result=self.nodes[spot].delivery(raw,key,topic,**metadata)
            if result['outcome']=='accepted':self.fresh[spot]=True
            return result

    def snapshot(self):
        with self.lock:
            spaces=[];totals={k:0 for k in ('accepted','duplicates','rejected','received')}
            for spot,node in self.nodes.items():
                data=node.snapshot();last=next(s for s in data['spaces'] if s['spot_id']==spot)
                for key in totals:totals[key]+=data[key]
                signal=self.signals.get(spot);age=time.monotonic()-signal['seen'] if signal else None
                health='broker_offline' if not self.connected else ('waiting' if not signal else
                    'offline' if age>self.health_timeout else signal['state'])
                online=health=='online' and self.fresh[spot] and last['has_persisted_data']
                status=last['status'] if online else 'unknown'
                spaces.append(dict(last,status=status,last_known_status=last['status'],online=online,health=health,
                    source_type=SOURCE_TYPE,health_age_seconds=age,source_observed_at=signal.get('observed_at') if signal else None,
                    distance_mm=signal.get('distance_mm') if signal else None,echo_us=signal.get('echo_us') if signal else None,
                    pending=signal.get('pending',0) if signal else 0,fresh_this_connection=online,
                    connection='Online' if online else 'No data' if not last['has_persisted_data'] else 'Offline / last known retained'))
            return dict(mode='MULTI_WOKWI_REFERENCE',reference_backend=True,session=self.session,input_mode='LIVE_VIRTUAL_HCSR04',
                physical_hardware=False,broker_connected=self.connected,journal_warning=self.journal_warning,server_received_at=utcnow(),spaces=spaces,**totals)

    def history(self,spot=None,after=0,limit=50,receipts=False):
        if spot is not None and spot not in self.nodes:raise ValueError('Unknown spot_id')
        if not 0<=after or not 1<=limit<=100:raise ValueError('after >=0; limit 1..100')
        rows=[]
        for key,node in self.nodes.items():
            if spot is None or key==spot:
                for row in node.history(after,limit,receipts)['records']:
                    row['bay']=MAPPING[key];row['source_type']=SOURCE_TYPE;rows.append(row)
        rows=sorted(rows,key=lambda row:row['id'])[:limit]
        return dict(records=rows,next_after=rows[-1]['id'] if rows else after,session=self.session)

class MultiSubscriber:
    def __init__(self,state,port):
        self.state=state;self.port=port;self.ready=threading.Event()
        self.client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id=client_id('multi-sub-'),protocol=mqtt.MQTTv311,clean_session=True)
        self.client.manual_ack_set(True);self.client.reconnect_delay_set(1,2)
        self.client.on_connect=self.on_connect;self.client.on_disconnect=self.on_disconnect
        self.client.on_subscribe=self.on_subscribe;self.client.on_message=self.on_message
    def on_connect(self,client,userdata,flags,reason,properties):
        if not reason.is_failure:client.subscribe([(self.state.prefix+'/+/events/+/+',1),(self.state.prefix+'/+/health',1)])
    def on_subscribe(self,client,userdata,mid,reasons,properties):
        if reasons and not any(r.is_failure for r in reasons):self.state.connection(True);self.ready.set()
    def on_disconnect(self,*args):self.ready.clear();self.state.connection(False)
    def on_message(self,client,userdata,message):
        try:
            if len(message.payload)>4096:raise ValueError('Transport payload exceeds 4096 bytes')
            relative=message.topic[len(self.state.prefix)+1:].split('/');spot=int(relative[0])
            if spot not in self.state.nodes:raise ValueError('Unmapped topic')
            if relative[1]=='health':self.state.signal(spot,json.loads(message.payload));client.ack(message.mid,message.qos);return
            if len(relative)!=4 or relative[1]!='events':raise ValueError('Bad event topic')
            key='/'.join(relative)
            received_wall_ms=time.time_ns()/1000000;started=time.perf_counter_ns()
            result=self.state.ingest(spot,message.payload,key,message.topic,qos=message.qos,retained=message.retain,dup=message.dup,mid=message.mid)
            self.state.journal('multi_delivery_timing',delivery_key=key,event_id=result['event_id'],outcome=result['outcome'],
                subscriber_received_wall_ms=received_wall_ms,commit_finished_wall_ms=time.time_ns()/1000000,
                validation_transaction_ms=(time.perf_counter_ns()-started)/1000000)
            # Application ACK follows atomic history/checkpoint/delivery-key commit.
            client.publish(self.state.prefix+'/ack',json.dumps(result),qos=1,retain=False)
            client.ack(message.mid,message.qos)
        except (ValueError,KeyError,UnicodeError) as exc:
            self.state.journal('multi_invalid_transport',error=str(exc));client.ack(message.mid,message.qos)
        except sqlite3.Error as exc:
            self.state.journal('multi_storage_failure',error=str(exc));client.disconnect()
    def start(self,timeout=5):
        self.client.connect_async('127.0.0.1',self.port,keepalive=5);self.client.loop_start();return self.ready.wait(timeout)
    def stop(self):self.client.disconnect();self.client.loop_stop();self.state.connection(False)
