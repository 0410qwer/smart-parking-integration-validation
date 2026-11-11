"""Own isolated broker/clients/HTTP for browser tests. JSON stdin is test control only."""
import json
import sys
import threading
from http.server import ThreadingHTTPServer
from transport import CAPTURE, HERE, Journal, Publisher, ReceivedState, Subscriber, load_capture
from dashboard_server import mqtt_handler
from test_transport import Broker, EVIDENCE, wait_for

broker=Broker('browser-owned-broker').start()
state=ReceivedState(Journal(EVIDENCE/'subscriber.jsonl'))
subscriber=Subscriber(state,broker.port)
publisher=Publisher(broker.port,journal=Journal(EVIDENCE/'publisher.jsonl'))
http=None
try:
    if not subscriber.start():
        raise RuntimeError('No subscriber SUBACK')
    publisher.start()
    http=ThreadingHTTPServer(('127.0.0.1',0),mqtt_handler(state))
    threading.Thread(target=http.serve_forever,daemon=True).start()
    records=load_capture(CAPTURE.read_text(encoding='utf-8-sig'))['records']
    print(json.dumps(dict(event='ready',url=f'http://127.0.0.1:{http.server_port}',mqtt_port=broker.port)),flush=True)
    for line in sys.stdin:
        command=json.loads(line)
        try:
            action=command['action']
            if action in ('publish','raw'):
                before=state.received
                payload=(records[command['index']]['raw_line'].strip().encode() if action=='publish'
                         else command['raw'].encode())
                publisher.publish(payload)
                wait_for(lambda:state.received==before+1)
            elif action=='disconnect':
                publisher.stop(); broker.stop()
                wait_for(lambda:not state.connected)
            elif action=='reconnect':
                broker.start()
                wait_for(lambda:subscriber.ready.is_set(),timeout=10)
                publisher=Publisher(broker.port,journal=Journal(EVIDENCE/'publisher.jsonl'))
                publisher.start()
            elif action=='stop':
                break
            else:
                raise ValueError('Unknown controller action')
            print(json.dumps(dict(ok=True,state=state.snapshot())),flush=True)
        except Exception as exc:
            print(json.dumps(dict(ok=False,error=str(exc))),flush=True)
finally:
    publisher.stop(); subscriber.stop(); broker.stop()
    if http:
        http.shutdown(); http.server_close()
