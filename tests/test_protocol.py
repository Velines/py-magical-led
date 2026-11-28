import unittest
from datetime import datetime

from magical_led import brightness, clock, color, decrypt, encrypt, plaintext, power, parse_power_notification
from magical_led.protocol import image_chunks, indexed_chunks


class ProtocolTests(unittest.TestCase):
    def test_power_notification_matches_app_prefixes(self):
        # Synthetic plaintext, not hardware captures.
        self.assertIs(parse_power_notification(b'\x00LEDON' + bytes(10)), True)
        self.assertIs(parse_power_notification(b'\xffLEDOFX' + bytes(9)), False)
        for frame in (b'\x05LEDON\0\0', b'LEDON' + bytes(11), plaintext('LIGHTOFF'), plaintext('VER')):
            self.assertIsNone(parse_power_notification(frame))
    def test_external_vectors(self):
        # trace: TEST-001 UR-001-AC1 SWR-001-AC1. .NET AES, not captured traffic.
        for frame, prefix, wire in (
            (power(True), '054c45444f4e', 'ebd372ed98857317f2f54cd2130fdc9c'),
            (power(False), '064c45444f4646', 'cbb1fdbfc560d5e453c2cbd928b53fab'),
            (color(0x12, 0x34, 0x56), '07434f4c4f341256', '1153d5d091266d514a11b97aa7887092'),
            (brightness(50), '064c4947485432', '12be7e044087149279944078890f457a'),
        ):
            with self.subTest(prefix=prefix):
                self.assertEqual(frame, bytes.fromhex(prefix).ljust(16, b'\0'))
                self.assertEqual(encrypt(frame).hex(), wire)
                self.assertEqual(decrypt(bytes.fromhex(wire)), frame)

    def test_app_specific_edges(self):
        self.assertEqual(brightness(0), b'\x06LIGHT\x01'.ljust(16, b'\0'))
        self.assertEqual(plaintext('STIN'), b'\x06STIN'.ljust(16, b'\0'))
        self.assertEqual(clock(datetime(2026, 11, 22, 23, 58, 59))[:9], b'\x08TIME\x07\x17\x3a\x3b')
        for bad in (-1, 256, True, 1.5):
            with self.assertRaises(ValueError):
                brightness(bad)
        for token, args in [('NOPE', ()), ('COLO', (1, 2)), ('VER', (0,))]:
            with self.assertRaises(ValueError):
                plaintext(token, *args)
        for bad in (b'', bytes(15), bytes(17)):
            with self.assertRaises(ValueError):
                decrypt(bad)

    def test_bulk_dialects_are_distinct(self):
        payload = bytes(range(20))
        self.assertEqual(list(indexed_chunks(payload)),
                         [b'\x13\0' + payload[:18], b'\x03\x01\x12\x13' + bytes(16)])
        self.assertEqual([decrypt(x) for x in image_chunks(payload)],
                         [b'\x0f' + payload[:15], b'\x05' + payload[15:] + bytes(10)])
        self.assertEqual(len(list(indexed_chunks(bytes(98), 98))), 1)
        self.assertFalse(list(indexed_chunks(b'')))
        with self.assertRaises(ValueError):
            list(indexed_chunks(bytes(18 * 256 + 1)))

    def test_catalogue_and_preset_validation(self):
        from magical_led import animation, image, effect, catalogue, static_color
        self.assertEqual(animation(1), plaintext('ANIM', 1))
        self.assertEqual(image(25), plaintext('IMAG', 25))
        self.assertEqual(effect(0), plaintext('EFFE', 0))
        self.assertEqual(static_color(1, 2, 3), (effect(0), color(1, 2, 3)))
        self.assertEqual(len(catalogue()), 56)
        self.assertFalse(any(p.observed_on for p in catalogue('images')))
        for builder, bad in [(animation, 0), (animation, 26), (image, True), (effect, 6)]:
            with self.assertRaises(ValueError):
                builder(bad)
