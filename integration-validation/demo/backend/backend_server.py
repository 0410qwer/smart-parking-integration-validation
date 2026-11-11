"""SQLite reference integration backend, not Saaket's production backend."""
import argparse
import json
from http.server import ThreadingHTTPServer
import sqlite3
from urllib.parse import parse_qs, urlsplit
from store import HERE, DurableSubscriber, PersistentState, Journal
from transport import CAPTURE, TOPIC, load_capture
from server import FRONTEND, handler_for


def backend_handler(state):
    report=load_capture(CAPTURE.read_text(encoding='utf-8-sig'))
    class Handler(handler_for(report)):
        def do_GET(self):
            path=urlsplit(self.path)
            code=200
            try:
                if path.path=='/api/availability':
                    data=state.snapshot()
                    code=503 if state.storage_error else 200
                elif path.path=='/api/health':
                    data=state.health()
                    code=503 if state.storage_error else 200
                elif path.path in ('/api/events','/api/receipts'):
                    query=parse_qs(path.query)
                    data=state.history(after=int(query.get('after',['0'])[0]),limit=int(query.get('limit',['100'])[0]),
                                       receipts=path.path=='/api/receipts')
                elif path.path=='/backend.js':
                    return self.respond(200,(HERE/'backend.js').read_bytes(),'text/javascript; charset=utf-8')
                elif path.path in ('/backend/','/backend/index.html'):
                    html=(FRONTEND/'index.html').read_text(encoding='utf-8')
                    html=html.replace('href="style.css"','href="/style.css"')
                    html=html.replace('Simulation Mode','SQLite reference backend — captured MQTT events, not production')
                    html=html.replace('Demo interface using simulated parking data','Persisted last-known observations; physical sensor connectivity not assessed')
                    html=html.replace('<main>','''<section style="padding:16px" aria-label="Persistent backend">
<p>Reference integration harness, not Saaket's production backend. 1001 → A01; 1002 → A02; 1003 → A03.</p>
<p>Availability shows the last committed database observation, including after restart. Health shows receipt freshness separately.</p>
<p id="backendStatus" role="status" aria-live="polite">Loading persisted state…</p>
<a href="/api/health">Sensor health API</a> | <a href="/api/events">Event history API</a> |
<a href="/">File replay</a> | <a href="http://127.0.0.1:8766/mqtt/">Memory MQTT mode</a> | <a href="/simulation/">Simulation</a>
</section><main>''')
                    html=html.replace('<th>Last Update</th>','<th>Persisted metadata; receive time (not source time)</th>')
                    html=html.replace('<script src="app.js"></script>','<script src="/base.js"></script><script src="/backend.js"></script>')
                    return self.respond(200,html.encode(),'text/html; charset=utf-8')
                else:
                    return super().do_GET()
            except ValueError as exc:
                data,code=dict(error=str(exc)),400
            except sqlite3.Error:
                data,code=dict(error='Reference database unavailable'),503
            self.respond(code,json.dumps(data).encode(),'application/json')

        def respond(self,code,body,mime):
            self.send_response(code)
            self.send_header('Content-Type',mime)
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    return Handler


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8767)
    parser.add_argument('--mqtt-port',type=int,default=18884)
    parser.add_argument('--db',default=str(HERE/'data'/'parking-reference.sqlite3'))
    parser.add_argument('--stream',default='capture-1',help='durable source-session namespace; reuse on restart')
    parser.add_argument('--log')
    args=parser.parse_args()
    state=PersistentState(args.db,args.stream,journal=Journal(args.log))
    subscriber=DurableSubscriber(state,args.mqtt_port)
    http=ThreadingHTTPServer(('127.0.0.1',args.port),backend_handler(state))
    try:
        ready=subscriber.start()
        print(f'Reference SQLite backend: http://127.0.0.1:{http.server_port}/backend/; subscribed={ready}; db={state.path}; stream={args.stream}',flush=True)
        http.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        subscriber.stop()
        http.server_close()


if __name__=='__main__':
    main()
