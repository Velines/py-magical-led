import unittest
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from magical_led import Strip, encrypt, plaintext, power
from magical_led.client import matches
from magical_led.protocol import BULK, COMMAND, LIVE, SERVICE, VERSION_READ, indexed_chunks, pixel, decrypt


class ClientTests(unittest.IsolatedAsyncioTestCase):
    # trace: TEST-003 UR-003-AC1 SWR-003-AC1
    def setUp(self):
        self.char = SimpleNamespace(properties=['write-without-response', 'write'], max_write_without_response_size=20)
        self.bulk = SimpleNamespace(properties=['write-without-response'], max_write_without_response_size=20)
        self.live = SimpleNamespace(properties=['write'], max_write_without_response_size=20)
        self.service = Mock()
        self.rx = SimpleNamespace(properties=['indicate'])
        self.version = SimpleNamespace(properties=['read'])
        self.service.characteristics = [self.char, self.rx, self.version]
        self.service.get_characteristic.side_effect = {COMMAND: self.char, VERSION_READ: self.version,
                                                      BULK: self.bulk, LIVE: self.live}.get
        self.client = Mock()
        self.client.services.get_service.side_effect = {SERVICE: self.service}.get
        self.client.write_gatt_char = AsyncMock()
        self.strip = Strip(self.client)

    async def test_writes_on_control_characteristic(self):
        wire = bytes.fromhex('ebd372ed98857317f2f54cd2130fdc9c')
        await self.strip.send(power(True))
        self.client.write_gatt_char.assert_awaited_once_with(self.char, wire, response=False)
        self.char.properties = ['write']
        await self.strip.send(power(True))
        self.client.write_gatt_char.assert_awaited_with(self.char, wire, response=True)

    async def test_no_write_to_wrong_profile(self):
        self.char.properties = ['notify']
        with self.assertRaisesRegex(ValueError, 'not writable'):
            await self.strip.send(power(True))
        self.client.write_gatt_char.assert_not_awaited()
        self.service.get_characteristic.side_effect = lambda _: None
        with self.assertRaisesRegex(ValueError, 'characteristic'):
            Strip(self.client)
        self.client.services.get_service.side_effect = lambda _: None
        with self.assertRaisesRegex(ValueError, 'service'):
            Strip(self.client)

    async def test_notification_context_cleanup(self):
        self.client.start_notify = AsyncMock()
        self.client.stop_notify = AsyncMock()
        observe = Mock()
        with self.assertRaises(TimeoutError):
            async with self.strip.notifications(observe):
                char, handler = self.client.start_notify.await_args.args
                self.assertIs(char, self.rx)
                wire = bytes.fromhex('cbb1fdbfc560d5e453c2cbd928b53fab')
                handler(char, bytearray(wire))
                observe.assert_called_with(wire, power(False))
                handler(char, b'x')
                observe.assert_called_with(b'x', None)
                raise TimeoutError
        self.client.stop_notify.assert_awaited_once_with(self.rx)

    async def test_plain_version_read(self):
        self.client.read_gatt_char = AsyncMock(return_value=bytearray(b'TR-example'))
        self.assertEqual(await self.strip.read_version(), b'TR-example')
        self.client.read_gatt_char.assert_awaited_once_with(self.version)

    async def test_read_power_observes_reports_during_subscription(self):
        for frame, expected in ((power(True), True), (b'\x05LEDOF' + bytes(10), False)):
            async def subscribe(char, callback):
                callback(char, b'short')
                callback(char, encrypt(plaintext('STSC')))
                callback(char, encrypt(frame))

            self.client.start_notify = AsyncMock(side_effect=subscribe)
            self.client.stop_notify = AsyncMock()
            self.assertIs(await self.strip.read_power(), expected)
            self.client.stop_notify.assert_awaited_once_with(self.rx)
        self.client.write_gatt_char.assert_not_awaited()

    async def test_read_power_does_not_reuse_reports_or_commands(self):
        self.client.start_notify = AsyncMock()
        self.client.stop_notify = AsyncMock()
        await self.strip.set_power(False)
        self.client.write_gatt_char.reset_mock()
        observe = Mock()
        async with self.strip.notifications(observe):
            char, callback = self.client.start_notify.await_args.args
            callback(char, encrypt(power(True)))
            self.assertIsNone(await self.strip.read_power(timeout=0.01))
            self.client.start_notify.assert_awaited_once()
            self.client.stop_notify.assert_not_awaited()
        self.client.stop_notify.assert_awaited_once_with(self.rx)
        self.client.write_gatt_char.assert_not_awaited()

    async def test_read_power_timeout_cleans_up_and_transport_errors_propagate(self):
        self.client.start_notify = AsyncMock()
        self.client.stop_notify = AsyncMock()
        with self.assertRaises(ValueError):
            await self.strip.read_power(timeout=0)
        self.client.start_notify.assert_not_awaited()
        self.assertIsNone(await self.strip.read_power(timeout=0.01))
        self.client.stop_notify.assert_awaited_once_with(self.rx)
        self.assertFalse(self.strip._listeners)
        self.client.start_notify.side_effect = TimeoutError('BLE setup failed')
        with self.assertRaisesRegex(TimeoutError, 'BLE setup failed'):
            await self.strip.read_power()

    async def test_secondary_channels(self):
        wire = next(indexed_chunks(b'abc'))
        await self.strip.send_chunk(wire)
        self.client.write_gatt_char.assert_awaited_with(self.bulk, b'\x04\x00abc' + bytes(15), response=False)
        with self.assertRaisesRegex(ValueError, 'write limit'):
            await self.strip.send_chunk(next(indexed_chunks(b'def', 98)))
        await self.strip.send_live(pixel(2, 3, 0x12, 0x34, 0x56))
        char, wire = self.client.write_gatt_char.await_args.args
        self.assertIs(char, self.live)
        self.assertEqual(decrypt(wire), bytes.fromhex('050203341256') + bytes(10))

    def test_scan_signature(self):
        self.assertTrue(matches({0x5254: b'\x00\x56\x01'}))
        self.assertFalse(matches({0x5452: b'\x00\x56'}))
        self.assertFalse(matches({0x5254: b'\x00\x57'}))

    def written_frames(self):
        return [decrypt(call.args[1]) for call in self.client.write_gatt_char.await_args_list]

    async def test_high_level_static_sequence(self):
        from magical_led import plaintext, color
        await self.strip.set_color(0, 255, 0, brightness=20, delay=0)
        self.assertEqual(self.written_frames(),
                         [plaintext('LIGHT', 20), plaintext('EFFE', 0), color(0, 255, 0)])
        self.client.write_gatt_char.reset_mock()
        await self.strip.set_brightness(80, color=(0, 255, 0), delay=0)
        self.assertEqual(self.written_frames(),
                         [plaintext('LIGHT', 80), plaintext('EFFE', 0), color(0, 255, 0)])

    async def test_high_level_selectors(self):
        from magical_led import plaintext
        await self.strip.select_animation(2)
        await self.strip.select_image(25)
        await self.strip.set_speed(80)
        await self.strip.set_effect(4, brightness=20, speed=80, delay=0)
        await self.strip.set_power(False)
        self.assertEqual(self.written_frames(), [plaintext('ANIM', 2), plaintext('IMAG', 25),
                         plaintext('SPEED', 80), plaintext('LIGHT', 20),
                         plaintext('SPEED', 80), plaintext('EFFE', 4), power(False)])

    async def test_sequence_prevalidation_and_failure(self):
        for frames, delay in [([power(True), b'short'], 0), ([power(True)], -1),
                              ([power(True)], float('nan')), ([power(True)], True)]:
            with self.assertRaises(ValueError):
                await self.strip.send_sequence(frames, delay=delay)
        with self.assertRaises(ValueError):
            await self.strip.set_color(0, 0, 256, brightness=20)
        self.client.write_gatt_char.assert_not_awaited()
        self.client.write_gatt_char.side_effect = [None, RuntimeError('write failed')]
        with self.assertRaisesRegex(RuntimeError, 'write failed'):
            await self.strip.set_color(0, 255, 0, brightness=20, delay=0)
        self.assertEqual(self.client.write_gatt_char.await_count, 2)

    async def test_sequence_cannot_interleave(self):
        from magical_led import plaintext, color
        entered = asyncio.Event()
        proceed = asyncio.Event()

        async def write(*args, **kwargs):
            if not entered.is_set():
                entered.set()
                await proceed.wait()

        self.client.write_gatt_char.side_effect = write
        scene = asyncio.create_task(self.strip.set_color(0, 255, 0, delay=0))
        await entered.wait()
        competing = asyncio.create_task(self.strip.set_power(False))
        await asyncio.sleep(0)
        proceed.set()
        await asyncio.gather(scene, competing)
        self.assertEqual(self.written_frames(), [plaintext('EFFE', 0), color(0, 255, 0), power(False)])

    async def test_clock_schedule_and_version_queries(self):
        from datetime import datetime
        from magical_led import Schedule, ScheduleRule, VersionInfo, clock, weekday_mask
        now = datetime(2026, 11, 28, 18, 30, 45)
        await self.strip.sync_clock(now)
        self.assertEqual(self.written_frames(), [clock(now)])
        self.client.write_gatt_char.reset_mock()

        sched = Schedule(
            on=ScheduleRule(True, weekday_mask('weekdays'), 18, 0),
            off=ScheduleRule(True, weekday_mask('daily'), 23, 30),
        )
        await self.strip.set_schedule(sched, sync_clock=True, local=now, delay=0)
        self.assertEqual(self.written_frames(), [clock(now), sched.to_frame()])
        self.client.write_gatt_char.reset_mock()

        callback_holder = []

        async def subscribe(_char, cb):
            callback_holder.append(cb)

        async def respond(_char, wire, **_kwargs):
            plain = decrypt(wire)
            cb = callback_holder[-1]
            if plain[1:4] == b'VER':
                cb(self.rx, encrypt(bytes.fromhex('05564552050100000000000000000000')))
            elif plain[1:5] == b'STSC':
                cb(self.rx, encrypt(sched.to_frame()))

        self.client.start_notify = AsyncMock(side_effect=subscribe)
        self.client.stop_notify = AsyncMock()
        self.client.write_gatt_char = AsyncMock(side_effect=respond)

        self.assertEqual(await self.strip.read_version_info(), VersionInfo(spi=5, ota=1))
        self.assertEqual(await self.strip.read_schedule(), sched)
        self.assertEqual(self.client.stop_notify.await_count, 2)

    async def test_read_state_single_connection_and_partial_timeouts(self):
        from magical_led import Schedule, Topology, VersionInfo
        self.client.read_gatt_char = AsyncMock(return_value=bytearray(b'TR2103R001-8\0'))
        callback_holder = []

        async def subscribe(_char, cb):
            callback_holder.append(cb)
            cb(self.rx, encrypt(b'\x0aSTYPE26X20' + bytes(5)))

        async def respond(_char, wire, **_kwargs):
            plain = decrypt(wire)
            cb = callback_holder[-1]
            if plain[1:4] == b'VER':
                cb(self.rx, encrypt(bytes.fromhex('05564552050100000000000000000000')))
            elif plain[1:5] == b'STSC':
                cb(self.rx, encrypt(bytes.fromhex('0c535453430000000000000000000000')))

        self.client.start_notify = AsyncMock(side_effect=subscribe)
        self.client.stop_notify = AsyncMock()
        self.client.write_gatt_char = AsyncMock(side_effect=respond)

        state = await self.strip.read_state(timeout=1)
        self.assertEqual(state.firmware, 'TR2103R001-8')
        self.assertEqual(state.version_info, VersionInfo(5, 1))
        self.assertEqual(state.topology, Topology(20, 26, 'STYPE26X20'))
        self.assertEqual(state.schedule, Schedule())
        self.assertIsNone(state.power)
        self.assertEqual(state.errors, ())
        self.client.start_notify.assert_awaited_once()
        self.client.stop_notify.assert_awaited_once_with(self.rx)

        # Partial failure: version read fails and STSC times out, while power notification arrives.
        self.strip._topology = None
        self.client.read_gatt_char = AsyncMock(side_effect=RuntimeError('gatt read failed'))

        async def subscribe_power(_char, cb):
            callback_holder.append(cb)
            cb(self.rx, encrypt(power(True)))

        self.client.start_notify = AsyncMock(side_effect=subscribe_power)
        self.client.write_gatt_char = AsyncMock()
        partial = await self.strip.read_state(timeout=0.01)
        self.assertIsNone(partial.firmware)
        self.assertIsNone(partial.version_info)
        self.assertIsNone(partial.schedule)
        self.assertIsNone(partial.topology)
        self.assertIs(partial.power, True)
        self.assertEqual(len(partial.errors), 4)
