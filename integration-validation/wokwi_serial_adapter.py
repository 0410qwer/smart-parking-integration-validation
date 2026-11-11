"""Offline Serial adapter for the source-reviewed ESP32 Parking Node Simulator."""
import hashlib
import json
from simulation_validator import parse_event_json

FIELDS = ('spot_id', 'occupied', 'batt_mv', 'status', 'ctr', 'heartbeat')
SOURCE_HASHES = {
    'sketch.ino': 'b57e51aeb6a996b5cdb198f839addd116136a3f0ffd8c30b13846f6e7f68b918',
    'diagram.json': 'd0ba612ce3d49a565ff82fcbb0e4550d6e7062f85c5ee856a4df616b9e38e7a6',
}


def validate_capture(text, *, evidence_kind='UNVERIFIED_CAPTURE', counter_modulus=256):
    """One ordered node stream; global counter survives ID changes, not boots."""
    if evidence_kind not in {'SAMPLE_FIXTURE', 'UNVERIFIED_CAPTURE'}:
        raise ValueError('unsupported evidence kind')
    if type(counter_modulus) is not int or counter_modulus != 256:
        raise ValueError('reviewed firmware requires counter_modulus=256')
    records, issues, ignored = [], [], []
    previous_ctr = previous_payload = previous_occupied = None
    comparisons = rollovers = resets = valid_records = state_comparisons = 0

    def issue(line, category, message):
        issues.append(dict(line_number=line, category=category, message=message))

    def uint(value, maximum):
        return type(value) is int and 0 <= value <= maximum

    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip().lstrip('\ufeff')
        if line.endswith('[BOOT] Parking Node Simulator starting...'):
            previous_ctr = previous_payload = None
            previous_occupied = False
            resets += 1
            ignored.append(dict(line_number=number, text=raw))
            continue
        start = line.find('{')
        if line.upper().startswith('HEX') or start < 0:
            if line.startswith('[') and not line.startswith(('[BOOT]', '[CFG]')):
                try:
                    json.loads(line)
                except ValueError:
                    ignored.append(dict(line_number=number, text=raw))
                else:
                    issue(number, 'json', 'JSON arrays are not event objects')
            else:
                ignored.append(dict(line_number=number, text=raw))
            continue
        try:
            payload = parse_event_json(line[start:])
        except ValueError as exc:
            issue(number, 'json', str(exc))
            continue
        if not set(FIELDS).intersection(payload):
            ignored.append(dict(line_number=number, text=raw))
            continue
        normalized = {}
        records.append(dict(local_record_id=f'line-{number}', line_number=number,
                            raw_line=raw, source_payload=payload, normalized=normalized,
                            source_identifiers={k: payload[k] for k in ('spot_id', 'event_id') if k in payload}))
        validity = {
            'spot_id': uint(payload.get('spot_id'), 0xFFFFFFFF),
            'occupied': type(payload.get('occupied')) is bool,
            'batt_mv': uint(payload.get('batt_mv'), 0xFFFF),
            'status': uint(payload.get('status'), 7),
            'ctr': uint(payload.get('ctr'), 255),
            'heartbeat': type(payload.get('heartbeat')) is bool,
        }
        for field, valid in validity.items():
            if field not in payload:
                issue(number, 'fields', 'missing field: ' + field)
            elif not valid:
                issue(number, 'fields', 'invalid type or value: ' + field)
        if validity['spot_id']:
            normalized['parking_space_id'] = str(payload['spot_id'])
        if validity['occupied']:
            normalized['status'] = 'OCCUPIED' if payload['occupied'] else 'AVAILABLE'
        if validity['ctr']:
            normalized['sequence_counter'] = payload['ctr']
        if not all(validity.values()):
            continue
        valid_records += 1
        expected_status = int(payload['occupied'])
        # Transition calls explicitly pass lowBatt=false even below 3200mV.
        if payload['heartbeat'] and payload['batt_mv'] < 3200:
            expected_status |= 4
        if payload['status'] != expected_status:
            issue(number, 'status_bits', f"expected status {expected_status}, received {payload['status']}")
        fingerprint = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        if fingerprint == previous_payload:
            issue(number, 'duplicates', 'adjacent identical payload; possible repeated capture, not a unique event ID')
            continue
        ctr = payload['ctr']
        if previous_ctr is not None:
            comparisons += 1
            expected = (previous_ctr + 1) % 256
            if ctr != expected:
                issue(number, 'sequence', f'expected {expected}, received {ctr}; gap, reset or reorder possible')
            elif previous_ctr == 255:
                rollovers += 1
        if previous_occupied is not None:
            state_comparisons += 1
            changed = payload['occupied'] != previous_occupied
            if changed == payload['heartbeat']:
                issue(number, 'output_state', 'heartbeat changed occupancy or transition repeated occupancy; missing records possible')
        previous_ctr, previous_payload = ctr, fingerprint
        previous_occupied = payload['occupied']

    checks = []

    def check(name, status, reason):
        checks.append(dict(check=name, result=status, reason=reason))

    check('event_presence', 'PASS' if records else 'FAIL', f'{len(records)} candidate objects')
    reasons = {
        'json': 'Strict JSON; HEX and Serial diagnostics ignored.',
        'fields': 'Six source fields, unsigned numeric ranges, strict JSON booleans.',
        'duplicates': 'Adjacent identical payloads flagged; repetition after rollover/reset can be legitimate.',
        'sequence': 'One global uint8 counter per node, +1 modulo 256 across ID changes; BOOT resets history.',
        'status_bits': 'Occupied bit0; fault bit1 clear; low-battery bit2 only on heartbeats below 3200mV.',
        'output_state': 'Heartbeats preserve output occupancy; non-heartbeats change it. Gaps may cause failures.',
    }
    for category, reason in reasons.items():
        failed = any(i['category'] == category for i in issues)
        assessed = {'sequence': comparisons, 'output_state': state_comparisons,
                    'status_bits': valid_records}.get(category, len(records)) > 0
        check(category, 'FAIL' if failed else 'PASS' if assessed else 'NOT ASSESSED', reason)
    check('counter_rollover', 'PASS' if rollovers else 'NOT ASSESSED',
          f'Source supports 255->0; {rollovers} valid pairs in this input; input provenance still applies.')
    for name, reason in {
        'status_transition_timing': 'Mocked signals, 1500/2500ms confirmation; no samples, intermediate states or event timestamps in Serial.',
        'source_event_identity': 'No source event ID; counter wraps/resets. Local record ID identifies a file line only.',
        'timestamp_ordering': 'Source emits no event timestamps. Prefixes and extra fields are not interpreted as event times.',
        'sensor_accuracy': 'HC-SR04 wired but never read; mocked inputs cannot establish physical accuracy.',
        'mqtt_wifi_backend_database_web': 'Serial only: no Wi-Fi, MQTT, BLE transmission or backend integration implemented.',
        'sensor_to_web_latency': 'No source timestamps, real sensor inputs or correlated backend/web observations.',
        'recovery': 'BOOT segments sequence history; no network implementation or controlled recovery observations.',
    }.items():
        check(name, 'NOT ASSESSED', reason)
    return dict(report_type='OFFLINE_SERIAL_VALIDATION', evidence_kind=evidence_kind,
                real_system_validated=False, source_review_status='SOURCE_REVIEWED',
                reviewed_source_sha256=SOURCE_HASHES,
                input_sha256=hashlib.sha256(text.encode('utf-8')).hexdigest(),
                contract=dict(spot_id='uint32 JSON integer normalized to decimal string',
                              counter_scope='global per node/session', counter_modulus=256,
                              required_fields=list(FIELDS)), boot_markers=resets,
                overall_result='FAIL' if any(c['result'] == 'FAIL' for c in checks) else 'NOT ASSESSED',
                records=records, issues=issues, ignored_lines=ignored, checks=checks)


def render_summary(report):
    lines = ['# Wokwi Serial validation', '', 'Evidence: ' + report['evidence_kind'],
             'Overall: ' + report['overall_result'], '',
             'Source-reviewed offline checks only; real system not validated.', '',
             '| Check | Result | Reason |', '|---|---|---|']
    lines.extend(f"| {c['check']} | {c['result']} | {c['reason']} |" for c in report['checks'])
    lines += ['', f"Records: {len(report['records'])}; issues: {len(report['issues'])}; ignored lines: {len(report['ignored_lines'])}."]
    lines.extend(f"- Line {i['line_number']}: {i['category']}: {i['message']}" for i in report['issues'])
    return '\n'.join(lines) + '\n'
