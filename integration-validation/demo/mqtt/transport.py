"""Real local MQTT clients; in-memory integration harness, not a production backend."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import threading
import uuid

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'vendor'))
sys.path.insert(0, str(HERE.parent))
from server import MAPPING, CAPTURE, load_capture, snapshot
from simulation_validator import parse_event_json
from wokwi_serial_adapter import FIELDS, validate_capture
import paho.mqtt.client as mqtt

TOPIC = 'smart-parking/integration-test/wokwi/node-1/events'


def utcnow():
    return datetime.now(timezone.utc).isoformat()


class Journal:
    def __init__(self, path=None):
        self.path = Path(path) if path else None
        self.lock = threading.Lock()

    def __call__(self, event, **fields):
        record = dict(at=utcnow(), event=event, **fields)
        if self.path:
            with self.lock, self.path.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(record) + '\n')
        return record


class ReceivedState:
    def __init__(self, journal=None):
        self.lock = threading.RLock()
        self.journal = journal or Journal()
        self.session = uuid.uuid4().hex
        self.previous = None
        self.accepted = self.duplicates = self.rejected = self.received = 0
        self.connected = False
        self.generation = 0
        self.bays = {}

    def connection(self, connected):
        with self.lock:
            self.connected = connected
            if connected:
                self.generation += 1
            self.journal('subscriber_ready' if connected else 'subscriber_disconnected',
                         generation=self.generation, session=self.session)

    def receive(self, raw, *, topic=TOPIC, qos=1, retained=False):
        with self.lock:
            self.received += 1
            try:
                if retained or qos != 1 or len(raw) > 4096:
                    raise ValueError('Requires non-retained QoS 1 payload <=4096 bytes')
                event = parse_event_json(raw.decode('utf-8'))
                if set(event) != set(FIELDS):
                    raise ValueError('Expected exactly the six Wokwi fields')
                report = validate_capture(json.dumps(event))
                if report['issues'] or len(report['records']) != 1:
                    raise ValueError('Invalid Wokwi field types/ranges/status bits')
                if event['spot_id'] not in MAPPING:
                    raise ValueError('Unmapped spot_id')
                if event == self.previous:
                    self.duplicates += 1
                    self.journal('duplicate', topic=topic, payload=event, session=self.session)
                    return 'duplicate'
                if self.previous is not None:
                    pair = validate_capture(json.dumps(self.previous) + '\n' + json.dumps(event))
                    if pair['issues']:
                        raise ValueError('Counter gap/reset/reorder or heartbeat/transition inconsistency')
                received_at = utcnow()
                self.accepted += 1
                normalized = dict(event_id=f'mqtt-receipt-{self.session}-{self.accepted}',
                                  parking_space_id=str(event['spot_id']),
                                  bay_label=MAPPING[event['spot_id']],
                                  status='OCCUPIED' if event['occupied'] else 'AVAILABLE',
                                  timestamp=received_at, timestamp_basis='subscriber_received_at',
                                  evidence_kind='CAPTURE_REPLAY_OVER_MQTT')
                self.bays[event['spot_id']] = dict(payload=event, received_at=received_at,
                                                 generation=self.generation, normalized=normalized)
                self.previous = event
                self.journal('accepted', topic=topic, qos=qos, retained=retained,
                             receipt=self.accepted, payload=event, task2_conversion=normalized,
                             session=self.session, generation=self.generation)
                return 'accepted'
            except (ValueError, UnicodeError, TypeError) as exc:
                self.rejected += 1
                self.journal('rejected', topic=topic, error=str(exc),
                             raw_hex=raw[:4096].hex(), session=self.session)
                return 'rejected'

    def snapshot(self):
        with self.lock:
            spaces = snapshot(dict(records=[], input_sha256=''), 0)['spaces']
            for space in spaces:
                receipt = self.bays.get(space['spotId'])
                space['connection'] = 'Waiting for MQTT data' if self.connected else 'MQTT subscriber disconnected'
                space['received_at'] = None
                if receipt:
                    event = receipt['payload']
                    space.update({key:event[key] for key in ('occupied','ctr','heartbeat','batt_mv','status')})
                    space['received_at'] = receipt['received_at']
                    space['online'] = self.connected and receipt['generation'] == self.generation
                    space['connection'] = ('Received via local MQTT' if space['online'] else
                                           'Awaiting new MQTT receipt after disconnect')
            return copy.deepcopy(dict(mode='MQTT_CAPTURE_TRANSPORT', evidence_kind='CAPTURE_REPLAY_OVER_MQTT',
                                      broker_connected=self.connected, physical_connectivity='NOT_ASSESSED',
                                      session=self.session, generation=self.generation,
                                      accepted=self.accepted, duplicates=self.duplicates, rejected=self.rejected,
                                      received=self.received, spaces=spaces))


def client_id(prefix):
    return prefix + uuid.uuid4().hex[:12]


class Subscriber:
    def __init__(self, state, port=18883, topic=TOPIC):
        self.state, self.port, self.topic = state, port, topic
        self.ready = threading.Event()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id('iv-sub-'),
                                  clean_session=True, protocol=mqtt.MQTTv311)
        self.client.reconnect_delay_set(1, 2)
        self.client.on_connect = self.on_connect
        self.client.on_subscribe = self.on_subscribe
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message

    def on_connect(self, client, userdata, flags, reason_code, properties):
        self.state.journal('connack', code=str(reason_code), topic=self.topic)
        if not reason_code.is_failure:
            client.subscribe(self.topic, qos=1)

    def on_subscribe(self, client, userdata, mid, reason_codes, properties):
        if reason_codes and not any(code.is_failure for code in reason_codes):
            self.state.connection(True)
            self.ready.set()
            self.state.journal('suback', mid=mid, qos=[str(code) for code in reason_codes], topic=self.topic)

    def on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.ready.clear()
        self.state.connection(False)

    def on_message(self, client, userdata, message):
        self.state.receive(message.payload, topic=message.topic, qos=message.qos, retained=message.retain)

    def start(self, timeout=5):
        self.client.connect_async('127.0.0.1', self.port, keepalive=5)
        self.client.loop_start()
        return self.ready.wait(timeout)

    def stop(self):
        self.client.disconnect()
        self.client.loop_stop()
        self.ready.clear()
        self.state.connection(False)


class Publisher:
    def __init__(self, port=18883, topic=TOPIC, journal=None):
        self.topic = topic
        self.port = port
        self.journal = journal or Journal()
        self.ready = threading.Event()
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id('iv-pub-'),
                                  clean_session=True, protocol=mqtt.MQTTv311)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = lambda *args: self.ready.clear()

    def on_connect(self, client, userdata, flags, reason_code, properties):
        self.journal('publisher_connack', code=str(reason_code))
        if not reason_code.is_failure:
            self.ready.set()

    def start(self, timeout=5):
        self.client.connect('127.0.0.1', self.port, keepalive=5)
        self.client.loop_start()
        if not self.ready.wait(timeout):
            self.stop()
            raise TimeoutError('Publisher CONNACK timeout')

    def publish(self, raw):
        if not self.ready.is_set():
            raise ConnectionError('Publisher not connected')
        info = self.client.publish(self.topic, raw, qos=1, retain=False)
        info.wait_for_publish(timeout=5)
        if not info.is_published():
            raise TimeoutError('MQTT PUBACK timeout')
        self.journal('puback', mid=info.mid, topic=self.topic, payload_hex=raw.hex())

    def stop(self):
        self.client.disconnect()
        self.client.loop_stop()
        self.ready.clear()
