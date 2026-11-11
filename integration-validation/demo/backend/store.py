"""Isolated SQLite reference backend. Not Saaket's production implementation."""
import json
from pathlib import Path
import re
import sqlite3
import sys
import threading
import uuid
from contextlib import contextmanager,closing

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'mqtt'))
from transport import Journal, MAPPING, ReceivedState, Subscriber, TOPIC, utcnow


class PersistentState:
    def __init__(self, database, stream_id='capture-1', topic=TOPIC, journal=None):
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', stream_id):
            raise ValueError('stream_id must be 1..64 letters/digits/underscore/hyphen')
        self.path = Path(database).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream_id, self.topic = stream_id, topic
        self.journal_warning = None
        journal_sink = journal or Journal()
        def safe_journal(event,**fields):
            try:return journal_sink(event,**fields)
            except OSError as exc:
                # Receipt auditing is transactional in SQLite. An optional text log must not
                # kill the MQTT network thread after a durable commit or prevent its ACK.
                self.journal_warning = str(exc)
        self.journal = safe_journal
        self.lock = threading.RLock()
        self.run = uuid.uuid4().hex
        self.epoch = uuid.uuid4().hex
        self.connected = False
        self.storage_error = None
        if self.path.exists():
            # Inspect before applying journal-mode pragmas: refusal must not mutate a foreign DB.
            with closing(sqlite3.connect(self.path.as_uri()+'?mode=ro',uri=True)) as probe:
                version=probe.execute('PRAGMA user_version').fetchone()[0]
                tables={r[0] for r in probe.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if (version!=0 or tables) and (version!=1 or not {'streams','events','bay_current','receipts','connections'}<=tables):
                    raise ValueError('Refusing an unrecognized database; choose a new reference-harness DB path')
        with self.db() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if version == 0 and not tables:
                db.executescript((HERE / 'schema.sql').read_text(encoding='utf-8'))
            elif version != 1 or not {'streams','events','bay_current','receipts','connections'} <= tables:
                raise ValueError('Refusing an unrecognized database; choose a new reference-harness DB path')
            db.execute('INSERT OR IGNORE INTO streams(stream_id,topic) VALUES (?,?)', (stream_id,topic))
            if db.execute('SELECT topic FROM streams WHERE stream_id=?',(stream_id,)).fetchone()[0] != topic:
                raise ValueError('Existing stream has a different topic')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=3)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('PRAGMA synchronous=FULL')
            with db:
                yield db
        finally:
            db.close()

    def connection(self, connected):
        with self.lock:
            self.connected = connected
            if connected:
                self.epoch = uuid.uuid4().hex
            with self.db() as db:
                db.execute('INSERT INTO connections(stream_id,backend_run,connection_epoch,connected,observed_at) VALUES (?,?,?,?,?)',
                           (self.stream_id,self.run,self.epoch,int(connected),utcnow()))

    def fail_storage(self, error):
        with self.lock:
            self.storage_error = str(error)
            self.connected = False
        self.journal('storage_failure_no_subscriber_ack', error=str(error), backend_run=self.run)

    def receive(self, raw, *, topic=TOPIC, qos=1, retained=False, mqtt_dup=False, mqtt_mid=None):
        with self.lock, self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            stream = db.execute('SELECT * FROM streams WHERE stream_id=?',(self.stream_id,)).fetchone()
            messages = []
            candidate = ReceivedState(lambda event, **fields: messages.append(dict(event=event,**fields)))
            candidate.previous = json.loads(stream['last_payload_json']) if stream['last_payload_json'] else None
            if topic != self.topic:
                outcome, reason = 'rejected', 'Unexpected MQTT topic for stream'
            else:
                outcome = candidate.receive(raw, topic=topic, qos=qos, retained=retained)
                reason = messages[-1].get('error') if messages else None
            now = utcnow()
            event_id = stream['last_event_id'] if outcome == 'duplicate' else None
            if outcome == 'accepted':
                event = candidate.previous
                payload = json.dumps(event,sort_keys=True,separators=(',',':'))
                ordinal = stream['accepted'] + 1
                cursor = db.execute('''INSERT INTO events(event_uuid,stream_id,ordinal,spot_id,occupied,status,batt_mv,ctr,heartbeat,
                    payload_json,raw_payload,topic,qos,retained,mqtt_dup,mqtt_mid,source_timestamp,received_at,backend_run,connection_epoch)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,NULL,?,?,?)''',
                    (uuid.uuid4().hex,self.stream_id,ordinal,event['spot_id'],int(event['occupied']),event['status'],
                     event['batt_mv'],event['ctr'],int(event['heartbeat']),payload,raw,topic,qos,int(retained),int(mqtt_dup),
                     mqtt_mid,now,self.run,self.epoch))
                event_id = cursor.lastrowid
                db.execute('INSERT INTO bay_current(stream_id,spot_id,event_id) VALUES (?,?,?) '
                           'ON CONFLICT(stream_id,spot_id) DO UPDATE SET event_id=excluded.event_id',
                           (self.stream_id,event['spot_id'],event_id))
                db.execute('UPDATE streams SET accepted=?,last_payload_json=?,last_event_id=? WHERE stream_id=?',
                           (ordinal,payload,event_id,self.stream_id))
            db.execute('''INSERT INTO receipts(receipt_uuid,stream_id,outcome,event_id,reason,raw_payload,raw_size,
                topic,qos,retained,mqtt_dup,mqtt_mid,received_at,backend_run,connection_epoch) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (uuid.uuid4().hex,self.stream_id,outcome,event_id,reason,raw[:4096],len(raw),topic,qos,int(retained),
                 int(mqtt_dup),mqtt_mid,now,self.run,self.epoch))
            # Context manager commits all history/current/checkpoint/receipt changes atomically.
        self.journal('sqlite_committed',outcome=outcome,event_id=event_id,stream_id=self.stream_id)
        return outcome

    def snapshot(self):
        with self.lock, self.db() as db:
            # One read transaction gives a coherent DB snapshot across all SELECTs.
            db.execute('BEGIN')
            counts = {r['outcome']:r['n'] for r in db.execute(
                'SELECT outcome,COUNT(*) AS n FROM receipts WHERE stream_id=? GROUP BY outcome',(self.stream_id,))}
            rows = {r['spot_id']:r for r in db.execute('SELECT e.* FROM bay_current b JOIN events e ON e.id=b.event_id WHERE b.stream_id=?',(self.stream_id,))}
            spaces=[]
            for spot,bay in MAPPING.items():
                row=rows.get(spot)
                fresh=bool(row and self.connected and row['backend_run']==self.run and row['connection_epoch']==self.epoch)
                space=dict(id=bay,spot_id=spot,status='unknown',has_persisted_data=bool(row),occupied=None,
                           batt_mv=None,status_bits=None,ctr=None,heartbeat=None,event_id=None,received_at=None,
                           source_timestamp=None,fresh_this_connection=fresh,
                           connection='No persisted observation',availability_basis='NO_DATA')
                if row:
                    space.update(occupied=bool(row['occupied']),batt_mv=row['batt_mv'],status_bits=row['status'],
                                 ctr=row['ctr'],heartbeat=bool(row['heartbeat']),event_id=row['id'],received_at=row['received_at'],
                                 status='occupied' if row['occupied'] else 'available',availability_basis='LAST_PERSISTED_OBSERVATION',
                                 connection='Persisted MQTT receipt in this connection' if fresh else 'Persisted last-known; awaiting new receipt')
                spaces.append(space)
            return dict(mode='SQLITE_REFERENCE_BACKEND',database_persistent=True,stream_id=self.stream_id,
                        broker_connected=self.connected,physical_connectivity='NOT_ASSESSED',
                        storage_error=self.storage_error,journal_warning=self.journal_warning,
                        accepted=counts.get('accepted',0),duplicates=counts.get('duplicate',0),
                        rejected=counts.get('rejected',0),received=sum(counts.values()),spaces=spaces)

    def health(self):
        data=self.snapshot()
        return dict(mode=data['mode'],stream_id=self.stream_id,database='sqlite-reference-harness',
                    broker_connected=data['broker_connected'],storage_error=data['storage_error'],journal_warning=data['journal_warning'],physical_connectivity='NOT_ASSESSED',
                    sensors=[{key:s[key] for key in ('id','spot_id','has_persisted_data','fresh_this_connection','received_at','connection')}
                             for s in data['spaces']])

    def history(self, after=0, limit=100, receipts=False):
        if type(after) is not int or after<0 or type(limit) is not int or not 1<=limit<=100:
            raise ValueError('after must be >=0 and limit 1..100')
        table='receipts' if receipts else 'events'
        with self.lock, self.db() as db:
            rows=db.execute(f'SELECT * FROM {table} WHERE stream_id=? AND id>? ORDER BY id LIMIT ?',
                            (self.stream_id,after,limit)).fetchall()
            records=[]
            for row in rows:
                record=dict(row)
                record['raw_payload_hex']=record.pop('raw_payload').hex()
                if not receipts:
                    for key in ('occupied','heartbeat','retained','mqtt_dup'):
                        record[key]=bool(record[key])
                    record['payload']=json.loads(record.pop('payload_json'))
                records.append(record)
            return dict(stream_id=self.stream_id,records=records,next_after=records[-1]['id'] if records else after)


class DurableSubscriber(Subscriber):
    def __init__(self, state, port=18883, topic=TOPIC):
        super().__init__(state,port,topic)
        self.client.manual_ack_set(True)

    def on_subscribe(self, client, userdata, mid, reason_codes, properties):
        try:
            super().on_subscribe(client,userdata,mid,reason_codes,properties)
        except sqlite3.Error as exc:
            self.ready.clear()
            self.state.fail_storage(exc)
            client.disconnect()

    def on_message(self, client, userdata, message):
        try:
            outcome=self.state.receive(message.payload,topic=message.topic,qos=message.qos,retained=message.retain,
                                       mqtt_dup=message.dup,mqtt_mid=message.mid)
            # Accepted events and rejected/duplicate audit receipts are committed before PUBACK.
            code=client.ack(message.mid,message.qos)
            self.state.journal('subscriber_ack_after_commit',mid=message.mid,outcome=outcome,code=int(code))
        except sqlite3.Error as exc:
            self.ready.clear()
            self.state.fail_storage(exc)
            client.disconnect()  # fail closed; explicit restart required after resolving storage failure

    def on_disconnect(self, client, userdata, flags, reason_code, properties):
        try:
            super().on_disconnect(client,userdata,flags,reason_code,properties)
        except sqlite3.Error as exc:
            self.ready.clear()
            self.state.fail_storage(exc)

    def stop(self):
        try:
            super().stop()
        except sqlite3.Error as exc:
            self.state.fail_storage(exc)
