import unittest
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from magical_led import Strip, power
from magical_led.client import matches
from magical_led.protocol import BULK, COMMAND, LIVE, SERVICE, VERSION_READ, indexed_chunks, pixel, decrypt


class ClientTests(unittest.IsolatedAsyncioTestCase):
    # trace: TEST-003 UR-003-AC1 SWR-003-AC1
    def setUp(self):
        self.char = SimpleNamespace(properties=['write-without-response', 'write'], max_write_without_response_size=20)
        self.bulk = SimpleNamespace(properties=['write-without-response'], max_write_without_response_size=20)
        self.live = SimpleNamespace(properties=['write'])
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
                              ([power(True)], float('nan'))]:
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
