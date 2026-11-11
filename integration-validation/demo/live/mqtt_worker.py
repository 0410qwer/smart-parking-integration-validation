"""Line-oriented live bridge worker. Input is stdin from a running browser, never a capture file."""
import argparse
import json
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'mqtt'))
from transport import Publisher,Journal
from wokwi_serial_adapter import validate_capture
from simulation_validator import parse_event_json
from transport import TOPIC
HEALTH_TOPIC=TOPIC+'/bridge-health'

def validate_line(raw):
    payload=parse_event_json(raw)
    if set(payload)!={'spot_id','occupied','batt_mv','status','ctr','heartbeat'}:
        raise ValueError('Expected the six Wokwi event fields')
    report=validate_capture(raw)
    if report['issues'] or not report['records']:raise ValueError('Invalid live sensor event')
    if payload['spot_id']!=1001:raise ValueError('Live demo maps sensor 1001 only')
    return payload

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mqtt-port',type=int,required=True)
    parser.add_argument('--journal',required=True)
    args=parser.parse_args()
    journal=Journal(args.journal)
    publisher=Publisher(args.mqtt_port,journal=journal)
    publisher.client.will_set(HEALTH_TOPIC,json.dumps(dict(state='offline')),qos=1,retain=False)
    def health(state):
        deadline=time.monotonic()+30
        while True:
            try:
                if not publisher.ready.is_set():raise ConnectionError('MQTT disconnected')
                info=publisher.client.publish(HEALTH_TOPIC,json.dumps(dict(state=state)),qos=1,retain=False)
                info.wait_for_publish(timeout=5)
                if not info.is_published():raise TimeoutError('Bridge health PUBACK timeout')
                return
            except (ConnectionError,RuntimeError,TimeoutError):
                if time.monotonic()>=deadline:raise TimeoutError('Bridge health unavailable for 30s')
                time.sleep(.25)
    try:
        publisher.start()
        print(json.dumps(dict(ready=True,input_mode='LIVE_BROWSER_SERIAL',replay=False)),flush=True)
        for line in sys.stdin:
            request=json.loads(line)
            try:
                if request.get('kind')=='health':
                    state=request['state']
                    if state not in ('streaming','sensor_untrusted','source_stalled','offline'):raise ValueError('Invalid bridge health')
                    health(state)
                    print(json.dumps(dict(ok=True,kind='health')),flush=True)
                    continue
                raw=request['raw']
                payload=validate_line(raw)
                deadline=time.monotonic()+30
                while True:
                    try:
                        publisher.publish(raw.encode())
                        break
                    except (ConnectionError,RuntimeError,TimeoutError):
                        if time.monotonic()>=deadline:raise TimeoutError('MQTT unavailable for 30s; event not discarded')
                        time.sleep(.25)
                journal('live_serial_forwarded',raw=raw,browser_observed_at=request['observed_at'],
                        bridge_published_at=time.time(),serial_index=request['serial_index'],
                        input_mode='LIVE_BROWSER_SERIAL',replay=False)
                print(json.dumps(dict(ok=True,serial_index=request['serial_index'],ctr=payload['ctr'])),flush=True)
            except (ValueError,KeyError,TypeError,TimeoutError) as exc:
                journal('live_bridge_rejected_or_stalled',error=str(exc))
                print(json.dumps(dict(ok=False,error=str(exc))),flush=True)
    finally:
        if publisher.ready.is_set():
            try:health('offline')
            except (RuntimeError,TimeoutError):pass
        publisher.stop()

if __name__=='__main__':main()
