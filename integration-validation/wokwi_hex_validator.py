"""Check captured JSON/HEX pairing against the reviewed packed ESP32 struct.

This validates recorded bytes, not BLE transmission or physical measurements.
Little-endian interpretation follows the ESP32 target, not native host layout.
"""
import re
import struct

from wokwi_serial_adapter import validate_capture


def validate_hex_pairs(text):
    records = {r['line_number']: r for r in validate_capture(text)['records']}
    pending = None
    pairs, issues = [], []
    hex_lines = 0

    def issue(line, message):
        issues.append(dict(line_number=line, message=message))

    for number, raw in enumerate(text.splitlines(), 1):
        if number in records:
            if pending is not None:
                issue(pending['line_number'], 'missing HEX before next JSON record')
            pending = records[number]
            continue
        marker = raw.find('HEX:')
        if marker < 0:
            if raw.strip().startswith('HEX'):
                issue(number, 'malformed HEX marker; expected HEX:')
            continue
        hex_lines += 1
        encoded = raw[marker + 4:].strip()
        if not re.fullmatch(r'[0-9a-fA-F]{22}', encoded):
            issue(number, 'HEX must contain exactly 22 hexadecimal digits (11 bytes)')
            pending = None  # A malformed HEX consumes the pending pair.
            continue
        company, version, spot, status, battery, counter = struct.unpack('<HBIBHB', bytes.fromhex(encoded))
        decoded = dict(company_id=company, ver=version, spot_id=spot,
                       status=status, batt_mv=battery, ctr=counter)
        if pending is None:
            issue(number, 'orphan HEX without preceding JSON record')
            continue
        payload = pending['source_payload']
        mismatches = []
        for key in ('spot_id', 'status', 'batt_mv', 'ctr'):
            if type(payload.get(key)) is not int or payload[key] != decoded[key]:
                mismatches.append(key)
        if company != 0xFFFF:
            mismatches.append('company_id')
        if version != 1:
            mismatches.append('ver')
        pair = dict(json_line=pending['line_number'], hex_line=number, hex_payload=encoded,
                    decoded=decoded, result='FAIL' if mismatches else 'PASS', mismatches=mismatches)
        pairs.append(pair)
        if mismatches:
            issue(number, 'JSON/HEX or source constant mismatch: ' + ', '.join(mismatches))
        pending = None
    if pending is not None:
        issue(pending['line_number'], 'missing HEX at end of capture')
    return dict(result='FAIL' if issues else 'PASS' if pairs else 'NOT ASSESSED',
                json_records=len(records), hex_lines=hex_lines, pairs=pairs, issues=issues,
                layout='little-endian <HBIBHB: company_id, ver, spot_id, status, batt_mv, ctr; 11 bytes',
                limitations='heartbeat is JSON-only; occupancy is checked by the JSON validator. Matching bytes do not establish provenance, BLE delivery or sensor accuracy.')
