import unittest

from magical_led import (DeviceState, Schedule, ScheduleRule, Topology, VersionInfo,
                         mask_to_weekdays, parse_schedule, parse_version_notification,
                         plaintext, schedule, weekday_mask)


class StateTests(unittest.TestCase):
    def test_weekday_masks_and_names(self):
        self.assertEqual(weekday_mask('mon'), 0x01)
        self.assertEqual(weekday_mask('sun'), 0x40)
        self.assertEqual(weekday_mask('weekdays'), 0x1F)
        self.assertEqual(weekday_mask('weekends'), 0x60)
        self.assertEqual(weekday_mask('daily'), 0x7F)
        self.assertEqual(weekday_mask('none'), 0x00)
        self.assertEqual(weekday_mask('Mon, Wednesday, fri'), 0b0010101)
        self.assertEqual(weekday_mask([1, 7]), 0x41)
        self.assertEqual(weekday_mask(0x7F), 0x7F)
        self.assertEqual(mask_to_weekdays(0x1F), ('mon', 'tue', 'wed', 'thu', 'fri'))
        self.assertEqual(mask_to_weekdays(0x60), ('sat', 'sun'))
        for bad in (True, -1, 128, '', 'funday', [0], [8], [True]):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    weekday_mask(bad)
        for bad in (True, -1, 128):
            with self.assertRaises(ValueError):
                mask_to_weekdays(bad)

    def test_schedule_encode_and_parse(self):
        # Captured hardware STSC response (2026-11-22): all disabled / zeros.
        captured_stsc = bytes.fromhex('0c535453430000000000000000000000')
        parsed = parse_schedule(captured_stsc)
        self.assertEqual(parsed, Schedule(ScheduleRule(False, 0, 0, 0), ScheduleRule(False, 0, 0, 0)))

        sched = Schedule(
            on=ScheduleRule(True, weekday_mask('weekdays'), 18, 30),
            off=ScheduleRule(True, weekday_mask('daily'), 23, 0),
        )
        frame = sched.to_frame()
        self.assertEqual(frame, schedule(sched.on, sched.off))
        self.assertEqual(frame, bytes([12]) + b'SCHD' + bytes([1, 0x1F, 18, 30, 1, 0x7F, 23, 0, 0, 0, 0]))
        self.assertEqual(parse_schedule(frame), sched)

        # SCHDOK ack and unrelated packets must be ignored.
        self.assertIsNone(parse_schedule(b'\x06SCHDOK' + bytes(9)))
        self.assertIsNone(parse_schedule(plaintext('VER')))
        self.assertIsNone(parse_schedule(b'short'))

        # High bit in day mask or invalid clock values raise ValueError.
        with self.assertRaises(ValueError):
            parse_schedule(bytes([12]) + b'STSC' + bytes([1, 0x80, 12, 0, 0, 0, 0, 0, 0, 0, 0]))
        with self.assertRaises(ValueError):
            ScheduleRule(True, 0x7F, 24, 0)
        with self.assertRaises(ValueError):
            ScheduleRule(True, 0x7F, 12, 60)

    def test_version_notification_and_device_state_dict(self):
        # Captured hardware VER response (2026-11-22): SPI=5, OTA=1.
        captured_ver = bytes.fromhex('05564552050100000000000000000000')
        self.assertEqual(parse_version_notification(captured_ver), VersionInfo(spi=5, ota=1))
        self.assertIsNone(parse_version_notification(b'\x03VER\x05\x01\x00\x00'))
        self.assertIsNone(parse_version_notification(plaintext('STSC')))

        state = DeviceState(
            firmware_raw_hex='545232313033523030312d3800',
            firmware='TR2103R001-8',
            version_info=VersionInfo(5, 1),
            topology=Topology(20, 26, 'STYPE26X20'),
            schedule=Schedule(),
            power=None,
            read_at='2026-11-28T17:00:00+01:00',
            errors=(),
        )
        as_dict = state.to_dict()
        self.assertEqual(as_dict['firmware'], 'TR2103R001-8')
        self.assertEqual(as_dict['version_info'], {'spi': 5, 'ota': 1})
        self.assertEqual(as_dict['topology']['pixel_count'], 520)
        self.assertIsNone(as_dict['power'])
        self.assertEqual(as_dict['schedule']['on']['time'], '00:00')
