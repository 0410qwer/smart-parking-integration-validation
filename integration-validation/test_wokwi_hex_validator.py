"""Handcrafted binary fixtures, never labelled observed simulator evidence."""
import json
import unittest

from wokwi_hex_validator import validate_hex_pairs

PAYLOAD = dict(spot_id=1001, occupied=False, batt_mv=3599, status=0, ctr=0, heartbeat=True)
HEX = 'HEX:FFFF01E9030000000F0E00'


class WokwiHexTests(unittest.TestCase):
    def test_known_little_endian_pair(self):
        report = validate_hex_pairs('[BOOT] Parking Node Simulator starting...\n' + json.dumps(PAYLOAD) + '\n' + HEX)
        self.assertEqual(report['result'], 'PASS')
        self.assertEqual(report['pairs'][0]['decoded'], dict(company_id=65535, ver=1, spot_id=1001, status=0, batt_mv=3599, ctr=0))

    def test_binary_field_mismatches(self):
        for key, value in dict(spot_id=1002, batt_mv=3598, status=1, ctr=1).items():
            with self.subTest(field=key):
                report = validate_hex_pairs(json.dumps(dict(PAYLOAD, **{key: value})) + '\n' + HEX)
                self.assertEqual(report['result'], 'FAIL')
                self.assertIn(key, report['pairs'][0]['mismatches'])

    def test_company_and_version_must_match_source(self):
        for encoded, field in (('000001E9030000000F0E00', 'company_id'), ('FFFF02E9030000000F0E00', 'ver')):
            report = validate_hex_pairs(json.dumps(PAYLOAD) + '\nHEX:' + encoded)
            self.assertIn(field, report['pairs'][0]['mismatches'])

    def test_malformed_length_and_characters(self):
        for encoded in ('FF', 'F' * 21, 'G' * 22):
            self.assertEqual(validate_hex_pairs(json.dumps(PAYLOAD) + '\nHEX:' + encoded)['result'], 'FAIL')

    def test_missing_orphan_and_duplicate_hex(self):
        for text in (json.dumps(PAYLOAD), HEX, json.dumps(PAYLOAD) + '\n' + HEX + '\n' + HEX,
                     json.dumps(PAYLOAD) + '\n' + json.dumps(PAYLOAD) + '\n' + HEX):
            self.assertEqual(validate_hex_pairs(text)['result'], 'FAIL')

    def test_prefixes_case_and_missing_json_field(self):
        text = '12:00 -> ' + json.dumps(PAYLOAD) + '\n12:00 -> ' + HEX.lower().replace('hex:', 'HEX:')
        self.assertEqual(validate_hex_pairs(text)['result'], 'PASS')
        payload = dict(PAYLOAD)
        del payload['ctr']
        self.assertEqual(validate_hex_pairs(json.dumps(payload) + '\n' + HEX)['result'], 'FAIL')
