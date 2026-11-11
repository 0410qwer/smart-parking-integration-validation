"""Saved ultrasonic-capture replay → real local MQTT. NOT direct ESP32 transport."""
import argparse
import time
import sys
from capture_adapter import HERE,validate_sensor_capture
sys.path.insert(0,str(HERE.parent/'mqtt'))
from transport import Publisher,Journal

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture')
    parser.add_argument('--port',type=int,default=18885)
    parser.add_argument('--interval',type=float,default=1)
    parser.add_argument('--log')
    args=parser.parse_args()
    if args.interval<0:parser.error('interval must be >=0')
    from pathlib import Path
    report=validate_sensor_capture(Path(args.capture).read_text(encoding='utf-8-sig'))
    publisher=Publisher(args.port,journal=Journal(args.log))
    try:
        publisher.start()
        for i,record in enumerate(report['records']):
            publisher.publish(record['raw_line'].strip().encode())
            print(f"Saved ultrasonic event PUBACK ctr={record['source_payload']['ctr']}; not direct ESP32",flush=True)
            if i+1<len(report['records']):time.sleep(args.interval)
    finally:publisher.stop()

if __name__=='__main__':main()
