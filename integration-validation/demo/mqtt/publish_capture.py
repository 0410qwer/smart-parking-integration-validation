"""Publish saved Wokwi JSON unchanged over real MQTT; no live sensor input."""
import argparse
from pathlib import Path
import time
from transport import CAPTURE, Journal, Publisher, load_capture


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=18883)
    parser.add_argument('--interval', type=float, default=1.0)
    parser.add_argument('--log', type=Path)
    parser.add_argument('--start', type=int, default=0, help='zero-based capture event index')
    parser.add_argument('--limit', type=int)
    args = parser.parse_args()
    if args.interval < 0 or args.start < 0 or (args.limit is not None and args.limit < 1):
        parser.error('Invalid interval/start/limit')
    report = load_capture(CAPTURE.read_text(encoding='utf-8-sig'))
    records = report['records'][args.start:]
    if args.limit is not None:
        records = records[:args.limit]
    if not records:
        parser.error('No capture events selected')
    journal = Journal(args.log)
    publisher = Publisher(port=args.port, journal=journal)
    try:
        publisher.start()
        for index, record in enumerate(records):
            # Send the actual JSON text, not an invented sensor envelope or timestamp.
            raw = record['raw_line'].strip().encode('utf-8')
            publisher.publish(raw)
            journal('capture_published', source_line=record['line_number'], ctr=record['source_payload']['ctr'],
                    capture_sha256=report['input_sha256'])
            print(f"PUBACK ctr={record['source_payload']['ctr']} source_line={record['line_number']}", flush=True)
            if index + 1 < len(records):
                time.sleep(args.interval)
    finally:
        publisher.stop()
    print(f'{len(records)} saved events published; subscriber receipt must be checked separately.', flush=True)


if __name__ == '__main__':
    main()
