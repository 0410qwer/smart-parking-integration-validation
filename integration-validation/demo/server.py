"""Loopback-only capture replay demo. No sensor, MQTT or database connection."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from wokwi_serial_adapter import validate_capture

MAPPING = {1001: 'A01', 1002: 'A02', 1003: 'A03'}
FRONTEND = ROOT.parent / 'smart-parking-web'
CAPTURE = ROOT / 'captures/wokwi_serial_actual.txt'


def load_capture(text):
    report = validate_capture(text)
    if report['issues'] or not report['records']:
        raise ValueError('Capture rejected: ' + json.dumps(report['issues']))
    unknown = {r['source_payload']['spot_id'] for r in report['records']} - MAPPING.keys()
    if unknown:
        raise ValueError('Unmapped spot IDs: ' + str(sorted(unknown)))
    return report


def snapshot(report, count):
    if type(count) is not int or not 0 <= count <= len(report['records']):
        raise ValueError('count outside capture range')
    spaces = {spot: dict(id=bay, spotId=spot, occupied=False, online=False,
                        connection='No captured data', lastUpdate=None,
                        ctr=None, heartbeat=None, batt_mv=None, status=None, line=None)
              for spot, bay in MAPPING.items()}
    for record in report['records'][:count]:
        event = record['source_payload']
        spaces[event['spot_id']].update(
            occupied=event['occupied'], online=True, connection='Captured record',
            ctr=event['ctr'], heartbeat=event['heartbeat'], batt_mv=event['batt_mv'],
            status=event['status'], line=record['line_number'])
    return dict(mode='CAPTURE_REPLAY', connectivity='NOT_ASSESSED', count=count,
                total=len(report['records']), spaces=list(spaces.values()),
                capture_sha256=report['input_sha256'])


def handler_for(report):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlsplit(self.path)
            try:
                if path.path == '/api/replay':
                    count = int(parse_qs(path.query).get('count', ['0'])[0])
                    body = json.dumps(snapshot(report, count)).encode()
                    mime = 'application/json'
                elif path.path in ('/', '/index.html'):
                    html = (FRONTEND / 'index.html').read_text(encoding='utf-8')
                    html = html.replace('Simulation Mode', 'Captured Wokwi replay — not live sensors')
                    html = html.replace('Demo interface using simulated parking data',
                                        'Saved Serial evidence replay; MQTT/backend/database not connected')
                    controls = '''<section style="padding:16px" aria-label="Replay controls">
<p>Mapping: 1001 → A01; 1002 → A02; 1003 → A03. Only 1001 occurs in this capture.</p>
<p>One event/second is demo pacing, not source timing. End holds the last captured state.</p>
<button id="play">Play / Pause</button> <button id="step">Next event</button>
<button id="reset">Reset</button> <a href="/simulation/">Simulation fallback (synthetic)</a>
<p id="replayStatus" role="status" aria-live="polite">Loading capture…</p></section>'''
                    html = html.replace('<main>', controls + '<main>')
                    html = html.replace('<th>Last Update</th>', '<th>Capture evidence (no source timestamp)</th>')
                    html = html.replace('<script src="app.js"></script>',
                                        '<script src="base.js"></script><script src="integration.js"></script>')
                    body, mime = html.encode(), 'text/html; charset=utf-8'
                elif path.path == '/base.js':
                    body = (FRONTEND / 'app.js').read_text(encoding='utf-8').split('// 7. Initialise application')[0].encode()
                    mime = 'text/javascript'
                elif path.path == '/integration.js':
                    body = Path(__file__).with_name('integration.js').read_bytes()
                    mime = 'text/javascript'
                elif path.path in ('/style.css', '/simulation/', '/simulation/app.js', '/simulation/style.css'):
                    name = 'index.html' if path.path == '/simulation/' else path.path.rsplit('/', 1)[-1]
                    body = (FRONTEND / name).read_bytes()
                    mime = 'text/html' if name.endswith('html') else 'text/css' if name.endswith('css') else 'text/javascript'
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header('Content-Type', mime)
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (ValueError, KeyError):
                self.send_error(400, 'Invalid replay request')
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    report = load_capture(CAPTURE.read_text(encoding='utf-8-sig'))
    print(f'Capture replay: http://127.0.0.1:{args.port}/ (22 saved events; not live)', flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(report)).serve_forever()


if __name__ == '__main__':
    main()
