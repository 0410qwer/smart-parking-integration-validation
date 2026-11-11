"""Read-only API and isolated multi-bay UI for the reference integration demo."""
import json
from pathlib import Path
import sqlite3
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit,parse_qs
HERE=Path(__file__).resolve().parent

def handler_for(state):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path=urlsplit(self.path);status=200
            try:
                if path.path in ('/','/backend/','/admin/'):
                    body=(HERE/'web/index.html').read_bytes();mime='text/html; charset=utf-8'
                elif path.path in ('/dashboard.css','/dashboard.js'):
                    body=(HERE/'web'/path.path[1:]).read_bytes();mime='text/css' if path.path.endswith('css') else 'text/javascript'
                elif path.path in ('/api/availability','/api/health'):
                    data=state.snapshot();body=json.dumps(data).encode();mime='application/json'
                elif path.path in ('/api/events','/api/receipts'):
                    q=parse_qs(path.query,keep_blank_values=True)
                    spot=int(q['spot_id'][0]) if 'spot_id' in q else None
                    data=state.history(spot,int(q.get('after',['0'])[0]),int(q.get('limit',['50'])[0]),path.path.endswith('receipts'))
                    body=json.dumps(data).encode();mime='application/json'
                elif path.path=='/healthz':body=b'{"service":"multi-reference","ready":true}';mime='application/json'
                else:self.send_error(404);return
            except ValueError as exc:status=400;body=json.dumps(dict(error=str(exc))).encode();mime='application/json'
            except sqlite3.Error:status=503;body=b'{"error":"Reference database unavailable"}';mime='application/json'
            self.send_response(status)
            for key,value in {'Content-Type':mime,'Content-Length':str(len(body)),'Cache-Control':'no-store',
                'X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"}.items():self.send_header(key,value)
            self.end_headers();self.wfile.write(body)
    return Handler
