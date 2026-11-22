import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from magical_led import (Strip, Topology, FrameMapping, parse_topology,
                         prepare_frames, encrypt, decrypt, power)
from magical_led.protocol import COMMAND, LIVE, SERVICE

REPORT = b'\x0aSTYPE26X20' + bytes(5)


class FrameTests(unittest.TestCase):
    # trace: TEST-006 UR-005-AC1 SWR-005-AC1
    def test_report_and_unknown_profiles(self):
        topology = parse_topology(REPORT)
        self.assertEqual((topology.width, topology.height, topology.pixel_count), (20, 26, 520))
        self.assertEqual(topology.reported_type, 'STYPE26X20')
        self.assertIsNone(parse_topology(b'short'))
        self.assertIsNone(parse_topology(b'\x03VER' + bytes(12)))
        self.assertIsNone(parse_topology(b'\x09STYPE26X20' + bytes(5)))
        with self.assertRaisesRegex(ValueError, 'unsupported'):
            parse_topology(b'\x0aSTYPE99X99' + bytes(5))
        with self.assertRaises(ValueError):
            Topology(26, 20, 'STYPE26X20')

    def test_normalization_copy_and_transforms(self):
        # trace: TEST-007 UR-005-AC2 SWR-005-AC2
        source = [[[0x12, 0x34, 0x56], 0xff0000]]
        result = prepare_frames([source], Topology(2, 1))
        source[0][0][0] = 0
        self.assertEqual(result, (((18, 52, 86), (255, 0, 0)),))
        frame = [[1, 2], [3, 4], [5, 6]]
        topology = Topology(3, 2)
        for mapping, expected in (
            (FrameMapping(transpose=True), [1, 3, 5, 2, 4, 6]),
            (FrameMapping(transpose=True, flip_x=True), [5, 3, 1, 6, 4, 2]),
            (FrameMapping(transpose=True, flip_y=True), [2, 4, 6, 1, 3, 5]),
            (FrameMapping(transpose=True, flip_x=True, flip_y=True), [6, 4, 2, 5, 3, 1]),
        ):
            self.assertEqual([rgb[2] for rgb in prepare_frames([frame], topology, mapping)[0]], expected)

    def test_bad_pixels_shapes_and_limits(self):
        for frames in ([], [[[True]]], [[[-1]]], [[[0x1000000]]], [[[(1, 2, 256)]]],
                       [[[(1.5, 2, 3)]]], [[[1, 2]]], [[[1], [2]]], [[[1]]] * 257):
            with self.subTest(frames=str(frames)[:60]), self.assertRaises(ValueError):
                prepare_frames(frames, Topology(1, 1))
        with patch('magical_led.frames.MAX_TOTAL_PIXELS', 1), self.assertRaisesRegex(ValueError, 'memory bound'):
            prepare_frames([[[0]], [[0]]], Topology(1, 1))


class PlaybackTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.command = SimpleNamespace(properties=['write-without-response'], max_write_without_response_size=20)
        self.live = SimpleNamespace(properties=['write-without-response'], max_write_without_response_size=20)
        self.rx = SimpleNamespace(properties=['notify'])
        service = Mock()
        service.characteristics = [self.command, self.live, self.rx]
        service.get_characteristic.side_effect = {COMMAND: self.command, LIVE: self.live}.get
        self.service = service
        self.client = Mock()
        self.client.services.get_service.side_effect = {SERVICE: service}.get
        self.client.write_gatt_char = AsyncMock()
        self.client.stop_notify = AsyncMock()

        async def subscribe(char, callback):
            callback(char, encrypt(REPORT))

        self.client.start_notify = AsyncMock(side_effect=subscribe)
        self.strip = Strip(self.client)

    async def test_ble_topology_and_shared_subscriptions(self):
        observe = Mock()
        async with self.strip.notifications(observe):
            topology = await self.strip.read_topology()
            self.assertEqual(topology, Topology(20, 26, 'STYPE26X20'))
            self.client.stop_notify.assert_not_awaited()
            async with self.strip.notifications(lambda raw, frame: None):
                self.client.start_notify.assert_awaited_once()
        self.client.stop_notify.assert_awaited_once_with(self.rx)
        self.assertIs(await self.strip.read_topology(), topology)
        self.client.write_gatt_char.assert_not_awaited()

    async def test_timeout_unknown_and_partial_setup_cleanup(self):
        self.client.start_notify.side_effect = None
        with self.assertRaises(TimeoutError):
            await self.strip.read_topology(timeout=0.01)
        self.client.stop_notify.assert_awaited_once_with(self.rx)
        self.assertFalse(self.strip._listeners)

        async def unknown(char, callback):
            callback(char, encrypt(b'\x0aSTYPE99X99' + bytes(5)))

        self.client.start_notify.side_effect = unknown
        with self.assertRaisesRegex(ValueError, 'unsupported controller grid'):
            await self.strip.read_topology()
        rx2 = SimpleNamespace(properties=['indicate'])
        self.service.characteristics.append(rx2)
        self.client.stop_notify.reset_mock()
        self.client.start_notify.side_effect = [None, RuntimeError('subscribe failed')]
        with self.assertRaisesRegex(RuntimeError, 'subscribe failed'):
            async with self.strip.notifications(lambda raw, frame: None):
                self.fail('setup should have failed')
        self.client.stop_notify.assert_awaited_once_with(self.rx)
        self.assertFalse(self.strip._listeners)

    async def test_callback_failure_does_not_starve_other_consumers(self):
        observe = Mock()
        loop = asyncio.get_running_loop()
        with patch.object(loop, 'call_exception_handler') as report_error:
            async with self.strip.notifications(Mock(side_effect=RuntimeError('observer failed'))):
                async with self.strip.notifications(observe):
                    self.strip._received(self.rx, encrypt(REPORT))
                    observe.assert_called_once_with(encrypt(REPORT), REPORT)
            self.assertGreaterEqual(report_error.call_count, 1)
        self.client.stop_notify.assert_awaited_once_with(self.rx)

    async def test_full_first_frame_deltas_and_loop_boundary(self):
        # trace: TEST-008 UR-005-AC2 SWR-005-AC2 SWR-005-AC3
        frames = [[[0, 0], [0, 0]], [[0, 0], [0, (0x12, 0x34, 0x56)]]]
        result = await self.strip.play_frames(frames, topology=Topology(2, 2), fps=100000,
                                             repeat=2, brightness=20, pixel_delay=0, command_delay=0)
        writes = self.client.write_gatt_char.await_args_list
        commands = [decrypt(c.args[1]) for c in writes if c.args[0] is self.command]
        self.assertEqual([c[1:6].rstrip(b'\0') for c in commands], [b'LIGHT', b'EFFE', b'COLO', b'SMVEW'])
        pixels = [decrypt(c.args[1]) for c in writes if c.args[0] is self.live]
        self.assertEqual([(p[1], p[2]) for p in pixels[:4]], [(0, 0), (0, 1), (1, 0), (1, 1)])
        self.assertEqual(pixels[4][:6], bytes.fromhex('050101341256'))
        self.assertEqual(pixels[5][:6], bytes.fromhex('050101000000'))
        self.assertEqual(result.frames_sent, 4)
        self.assertEqual(result.pixel_writes, 7)
        self.assertGreater(result.elapsed_seconds, 0)
        self.assertNotIn(b'\x06SMVEW\x02' + bytes(9), commands)

    async def test_validation_before_lighting_changes(self):
        for options in ({'fps': 0}, {'fps': float('nan')}, {'repeat': True},
                        {'pixel_delay': -1}, {'command_delay': float('inf')}):
            with self.assertRaises(ValueError):
                await self.strip.play_frames([[[0]]], topology=Topology(1, 1), **options)
        with self.assertRaises(ValueError):
            await self.strip.play_frames([[[0]], [[(256, 0, 0)]]], topology=Topology(1, 1))
        self.live.properties = ['notify']
        with self.assertRaisesRegex(ValueError, 'not writable'):
            await self.strip.play_frames([[[0]]], topology=Topology(1, 1))
        self.client.write_gatt_char.assert_not_awaited()

    async def test_cancellation_releases_lock_without_save(self):
        entered = asyncio.Event()

        async def write(char, value, **kwargs):
            if char is self.live:
                entered.set()
                await asyncio.Future()

        self.client.write_gatt_char.side_effect = write
        task = asyncio.create_task(self.strip.play_frames([[[0]]], topology=Topology(1, 1), command_delay=0))
        await entered.wait()
        competing = asyncio.create_task(self.strip.set_power(False))
        await asyncio.sleep(0)
        self.assertFalse(competing.done())
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(competing, timeout=1)
        values = [decrypt(c.args[1]) for c in self.client.write_gatt_char.await_args_list]
        self.assertEqual(values[-1], power(False))
        self.assertFalse(any(v[1:6] == b'SMVEW' and v[6] == 2 for v in values))

    async def test_pixel_write_failure_stops_and_releases_lock(self):
        async def write(char, value, **kwargs):
            if char is self.live:
                raise RuntimeError('pixel write failed')

        self.client.write_gatt_char.side_effect = write
        with self.assertRaisesRegex(RuntimeError, 'pixel write failed'):
            await self.strip.play_frames([[[0, 0]]], topology=Topology(2, 1), command_delay=0)
        self.assertEqual(sum(call.args[0] is self.live for call in self.client.write_gatt_char.await_args_list), 1)
        await asyncio.wait_for(self.strip.set_power(False), timeout=1)
        self.assertEqual(decrypt(self.client.write_gatt_char.await_args.args[1]), power(False))

    async def test_pacing_does_not_catch_up_after_slow_frame(self):
        clock = [0.0]

        async def sleep(seconds):
            self.assertGreaterEqual(seconds, 0)
            clock[0] += seconds

        async def write(char, value, **kwargs):
            if char is self.live:
                clock[0] += 0.03

        self.client.write_gatt_char.side_effect = write
        with patch('magical_led.client.monotonic', side_effect=lambda: clock[0]), \
             patch('magical_led.client.asyncio.sleep', side_effect=sleep):
            result = await self.strip.play_frames([[[0, 0], [0, 0]]] * 2,
                topology=Topology(2, 2), fps=10, pixel_delay=0.01, command_delay=0)
        self.assertEqual(result.pixel_writes, 4)
        self.assertAlmostEqual(result.elapsed_seconds, 0.26)
        self.assertEqual(result.overrun_frames, 1)
        self.assertAlmostEqual(result.max_frame_write_seconds, 0.16)

    async def test_named_effect_two_second_schedule(self):
        # trace: TEST-010 UR-006-AC2 SWR-006-AC2
        clock = [0.0]

        async def sleep(seconds):
            clock[0] += seconds

        async def write(char, value, **kwargs):
            if char is self.live:
                clock[0] += 0.001

        self.client.write_gatt_char.side_effect = write
        with patch('magical_led.client.monotonic', side_effect=lambda: clock[0]), \
             patch('magical_led.client.asyncio.sleep', side_effect=sleep):
            result = await self.strip.play_effect('XMAS 01', topology=Topology(4, 2),
                                                  repeat=2, brightness=20)
        self.assertEqual(result.frames_sent, 16)
        self.assertEqual(result.pixel_writes, 38)
        self.assertAlmostEqual(result.elapsed_seconds, 16)
        self.assertAlmostEqual(clock[0], 18)  # Four setup commands, then two 8 s cycles.
        self.assertEqual(result.overrun_frames, 0)

    async def test_continuous_repeat_does_not_reinitialize_each_cycle(self):
        holds = 0

        async def sleep(seconds):
            nonlocal holds
            if seconds > 0:
                holds += 1
                if holds == 5:
                    raise asyncio.CancelledError

        with patch('magical_led.client.asyncio.sleep', side_effect=sleep):
            with self.assertRaises(asyncio.CancelledError):
                await self.strip.play_frames([[[0]], [[0xff0000]]], topology=Topology(1, 1),
                                             repeat=None, pixel_delay=0, command_delay=0)
        calls = self.client.write_gatt_char.await_args_list
        self.assertEqual(sum(c.args[0] is self.command for c in calls), 3)
        self.assertEqual(sum(c.args[0] is self.live for c in calls), 5)
        self.assertFalse(self.strip._lock.locked())

    async def test_named_effect_continues_past_first_cycle_by_default(self):
        holds = 0

        async def sleep(seconds):
            nonlocal holds
            if seconds > 0:
                holds += 1
                if holds == 5:
                    raise asyncio.CancelledError

        with patch('magical_led.client.asyncio.sleep', side_effect=sleep):
            with self.assertRaises(asyncio.CancelledError):
                # No repeat argument: pass the four-phase cycle and enter phase 0 again.
                await self.strip.play_effect('XMAS 01', topology=Topology(4, 1), command_delay=0, initial_pixel_delay=0)
        calls = self.client.write_gatt_char.await_args_list
        self.assertEqual(sum(call.args[0] is self.command for call in calls), 3)
        self.assertEqual(sum(call.args[0] is self.live for call in calls), 12)
        self.assertFalse(self.strip._lock.locked())
