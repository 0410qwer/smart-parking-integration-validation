"""HTTP view of actual MQTT subscriber state; separate from saved-file replay."""
import argparse
import json
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit
from transport import HERE, Journal, ReceivedState, Subscriber, CAPTURE, load_capture
from server import FRONTEND, handler_for


def mqtt_handler(state):
    replay = load_capture(CAPTURE.read_text(encoding='utf-8-sig'))
    class Handler(handler_for(replay)):
        def do_GET(self):
            path = urlsplit(self.path).path
            if path == '/api/mqtt':
                body, mime = json.dumps(state.snapshot()).encode(), 'application/json'
            elif path == '/mqtt.js':
                body, mime = (HERE / 'mqtt.js').read_bytes(), 'text/javascript; charset=utf-8'
            elif path in ('/mqtt/', '/mqtt/index.html'):
                html = (FRONTEND / 'index.html').read_text(encoding='utf-8')
                html = html.replace('href="style.css"', 'href="/style.css"')
                html = html.replace('Simulation Mode', 'Local MQTT transport harness — saved Wokwi events, not live sensors')
                html = html.replace('Demo interface using simulated parking data',
                                    'Real local MQTT broker transport; in-memory harness, no production database')
                controls = '''<section style="padding:16px" aria-label="MQTT transport">
<p>1001 → A01; 1002 → A02; 1003 → A03. Updated only by subscriber-received MQTT messages.</p>
<p>Publisher input is the saved Wokwi capture. No physical sensor or ESP32 connection.</p>
<p id="mqttStatus" role="status" aria-live="polite">Connecting to local subscriber service…</p>
<a href="/">Saved-file replay fallback</a> | <a href="/simulation/">Original simulation fallback</a>
</section>'''
                html = html.replace('<main>', controls + '<main>')
                html = html.replace('<th>Last Update</th>', '<th>MQTT subscriber receipt (UTC, not source time)</th>')
                html = html.replace('<script src="app.js"></script>',
                                    '<script src="/base.js"></script><script src="/mqtt.js"></script>')
                body, mime = html.encode(), 'text/html; charset=utf-8'
            else:
                return super().do_GET()
            self.send_response(200)
            self.send_header('Content-Type', mime)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--mqtt-port', type=int, default=18883)
    parser.add_argument('--log', type=Path)
    args = parser.parse_args()
    if args.log is None:
        from datetime import datetime, timezone
        folder = HERE.parent / 'evidence' / ('mqtt-session-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
        folder.mkdir(parents=True, exist_ok=False)
        args.log = folder / 'subscriber.jsonl'
    state = ReceivedState(Journal(args.log))
    subscriber = Subscriber(state, port=args.mqtt_port)
    ready = subscriber.start()
    http = ThreadingHTTPServer(('127.0.0.1', args.port), mqtt_handler(state))
    print(f'MQTT harness: http://127.0.0.1:{args.port}/mqtt/; subscribed={ready}; journal={args.log}', flush=True)
    try:
        http.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        http.server_close()
        subscriber.stop()


if __name__ == '__main__':
    main()
