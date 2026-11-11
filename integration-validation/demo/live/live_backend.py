"""Labelled live-browser-Serial reference service; original backend mode remains unchanged."""
import argparse
from pathlib import Path
import sys
import json
import time
from http.server import ThreadingHTTPServer
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'backend'))
from store import PersistentState,DurableSubscriber,Journal
from backend_server import backend_handler
from transport import TOPIC
HEALTH_TOPIC=TOPIC+'/bridge-health'

class LiveState(PersistentState):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.bridge_state='unknown'
        self.bridge_seen=None

    def bridge_health(self,raw):
        with self.lock:
            data=json.loads(raw)
            if set(data)!={'state'} or data['state'] not in ('streaming','sensor_untrusted','source_stalled','offline'):
                raise ValueError('Invalid bridge status')
            self.bridge_state=data['state'];self.bridge_seen=time.monotonic()

    def snapshot(self):
        with self.lock:
            data=super().snapshot()
            state=self.bridge_state
            age=time.monotonic()-self.bridge_seen if self.bridge_seen is not None else None
            if not self.connected:state='broker_disconnected'
            elif age is not None and age>10:state='health_stale'
            bridge=dict(state=state,health_age_seconds=age,physical_connectivity='NOT_ASSESSED')
            if state!='streaming':
                for space in data['spaces']:
                    if space['has_persisted_data']:
                        space['fresh_this_connection']=False
                        space['connection']='Persisted last-known; live Serial bridge '+state
            return dict(data,input_mode='LIVE_WOKWI_SERIAL_BRIDGE',replay=False,bridge=bridge)

    def health(self):
        with self.lock:
            return dict(super().health(),bridge=self.snapshot()['bridge'],input_mode='LIVE_WOKWI_SERIAL_BRIDGE')

class LiveSubscriber(DurableSubscriber):
    def on_connect(self,client,userdata,flags,reason_code,properties):
        if not reason_code.is_failure:client.subscribe([(self.topic,1),(HEALTH_TOPIC,1)])

    def on_message(self,client,userdata,message):
        if message.topic==HEALTH_TOPIC:
            try:self.state.bridge_health(message.payload)
            except (ValueError,UnicodeError):pass
            client.ack(message.mid,message.qos)
        else:super().on_message(client,userdata,message)

def live_handler(state):
    class Handler(backend_handler(state)):
        def do_GET(self):
            if self.path=='/live-health.js':
                script="""setInterval(async()=>{try{const r=await fetch('/api/health');const d=await r.json();document.getElementById('liveHealth').textContent='Live simulated-sensor Serial bridge: '+d.bridge.state+'; physical connectivity not assessed.';}catch(e){document.getElementById('liveHealth').textContent='Live bridge health unavailable';}},500);"""
                return self.respond(200,script.encode(),'text/javascript')
            return super().do_GET()

        def respond(self,code,body,mime):
            if mime.startswith('text/html'):
                body=body.replace('captured MQTT events, not production'.encode(),
                                  'live Wokwi Serial bridge; simulated sensor, not production'.encode())
                if b'backendStatus' in body:
                    body=body.replace(b'<main>',b'<p id="liveHealth" role="status">Live bridge health loading</p><main>')
                    body=body.replace(b'</body>',b'<script src="/live-health.js"></script></body>')
            return super().respond(code,body,mime)
    return Handler

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mqtt-port',type=int,default=18886)
    parser.add_argument('--port',type=int,default=8770)
    parser.add_argument('--db',required=True)
    parser.add_argument('--stream',required=True)
    parser.add_argument('--log')
    args=parser.parse_args()
    state=LiveState(args.db,args.stream,journal=Journal(args.log))
    sub=LiveSubscriber(state,args.mqtt_port)
    http=ThreadingHTTPServer(('127.0.0.1',args.port),live_handler(state))
    try:
        ready=sub.start();print(f'LIVE reference backend: http://127.0.0.1:{http.server_port}/backend/; ready={ready}',flush=True)
        http.serve_forever()
    except KeyboardInterrupt:pass
    finally:sub.stop();http.server_close()

if __name__=='__main__':main()
