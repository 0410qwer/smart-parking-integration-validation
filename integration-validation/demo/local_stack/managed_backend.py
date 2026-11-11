"""Owned, gracefully stoppable wrapper around the existing local service implementations."""
import argparse
import json
from pathlib import Path
import sys
import threading
from http.server import ThreadingHTTPServer
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'live'))
sys.path.insert(0,str(HERE.parent/'mqtt'))
sys.path.insert(0,str(HERE.parent/'backend'))
sys.path.insert(0,str(HERE.parent/'multi'))
from live_backend import LiveState,LiveSubscriber,live_handler
from store import PersistentState,DurableSubscriber,Journal
from backend_server import backend_handler
from transport import ReceivedState,Subscriber,CAPTURE,load_capture
from dashboard_server import mqtt_handler
from server import handler_for

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--mode',choices=['Multi','Live','Reference','Memory','Replay','Simulation'],required=True)
parser.add_argument('--port',type=int,required=True)
parser.add_argument('--mqtt-port',type=int,default=0)
parser.add_argument('--db',required=True)
parser.add_argument('--stream',required=True)
parser.add_argument('--log',required=True)
args=parser.parse_args()
subscriber=None
if args.mode=='Multi':
    from model import MultiState,MultiSubscriber
    from server import handler_for as multi_handler
    # "server" is already the legacy replay module in sys.modules; load isolated UI explicitly.
    import importlib.util
    spec=importlib.util.spec_from_file_location('multi_http',HERE.parent/'multi/server.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    state=MultiState(args.db,args.stream,Journal(args.log));subscriber=MultiSubscriber(state,args.mqtt_port);handler=module.handler_for(state)
elif args.mode=='Live':
    state=LiveState(args.db,args.stream,journal=Journal(args.log));subscriber=LiveSubscriber(state,args.mqtt_port);handler=live_handler(state)
elif args.mode=='Reference':
    state=PersistentState(args.db,args.stream,journal=Journal(args.log));subscriber=DurableSubscriber(state,args.mqtt_port);handler=backend_handler(state)
elif args.mode=='Memory':
    state=ReceivedState(Journal(args.log));subscriber=Subscriber(state,args.mqtt_port);handler=mqtt_handler(state)
else:handler=handler_for(load_capture(CAPTURE.read_text(encoding='utf-8-sig')))
http=ThreadingHTTPServer(('127.0.0.1',args.port),handler)
try:
    if subscriber and not subscriber.start():raise RuntimeError('MQTT subscriber did not receive SUBACK')
    threading.Thread(target=http.serve_forever,daemon=True).start()
    print(json.dumps(dict(event='ready',port=http.server_port,mode=args.mode)),flush=True)
    for line in sys.stdin:
        if line.strip()=='stop':break
finally:
    http.shutdown();http.server_close()
    if subscriber:subscriber.stop()
