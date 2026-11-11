"""Reuse source-field checks, with explicit provenance for the ultrasonic variant."""
import hashlib
import json
from pathlib import Path
import re
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent.parent))
from wokwi_serial_adapter import validate_capture


def validate_sensor_capture(text):
    if '[BOOT] HC-SR04-only measured Wokwi variant' not in text:
        raise ValueError('Not labelled as the isolated HC-SR04 variant')
    samples=[]
    pattern=r'^\[SENSOR\] t_ms=(\d+) echo_us=(\d+) distance_mm=(\d+) valid=(\d) known=(\d) trusted=(\d) occupied=(\d) fault=(\d)$'
    for line in text.splitlines():
        if line.startswith('[SENSOR]'):
            match=re.fullmatch(pattern,line)
            if not match:raise ValueError('Malformed sensor diagnostic')
            sample=dict(zip(('t_ms','echo_us','distance_mm','valid','known','trusted','occupied','fault'),map(int,match.groups())))
            expected=0 if sample['echo_us']==0 or sample['echo_us']>=25000 else (sample['echo_us']*10+29)//58
            valid=sample['echo_us']>0 and sample['echo_us']<25000 and 20<=expected<=4100
            if sample['distance_mm']!=expected or sample['valid']!=int(valid):
                raise ValueError('Echo pulse/distance/validity inconsistent')
            samples.append(sample)
    if not samples:raise ValueError('No actual measurement diagnostics supplied')
    legacy=validate_capture(text)
    if legacy['issues'] or not legacy['records']:raise ValueError('Invalid/missing six-field events: '+json.dumps(legacy['issues']))
    applicable={'event_presence','json','fields','duplicates','sequence','status_bits','output_state','counter_rollover'}
    return dict(report_type='HC_SR04_VARIANT_CAPTURE_VALIDATION',evidence_kind='WOKWI_BROWSER_SERIAL_CAPTURE',
                physical_sensor_verified=False,direct_esp32_mqtt_verified=False,
                contract_checker='existing wokwi_serial_adapter; six-field and sequence checks reused only',
                checks=[c for c in legacy['checks'] if c['check'] in applicable],records=legacy['records'],
                samples=samples,input_sha256=hashlib.sha256(text.encode()).hexdigest(),
                source_sha256={name:hashlib.sha256((HERE/'firmware'/name).read_bytes()).hexdigest() for name in ('sketch.ino','diagram.json')})
