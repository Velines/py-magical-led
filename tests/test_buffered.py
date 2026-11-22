import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from magical_led import (Strip, Topology, encode_animation, AnimationTransferError,
                         AnimationUploadResult, encrypt, decrypt, power,
                         StorageCapabilities, PersistentStoreResult, StorageUnsupportedError)
from magical_led.protocol import COMMAND, BULK, SERVICE


def reply(token):
    token = token.encode('ascii')
    return encrypt((bytes([len(token)]) + token).ljust(16, b'\0'))


class EncodingTests(unittest.TestCase):
    # trace: TEST-011 UR-007-AC1 SWR-007-AC1
    def test_column_major_grb_and_header(self):
        frames = [[[(1, 2, 3), (4, 5, 6)], [(7, 8, 9), (10, 11, 12)]]]
        transfer = encode_animation(frames, Topology(2, 2), wire_speed=10, chunk_capacity=18)
        self.assertEqual(transfer.payload, bytes([2, 1, 3, 8, 7, 9, 5, 4, 6, 11, 10, 12]))
        self.assertEqual(transfer.header, bytes.fromhex('084d414e59010a000c') + bytes(7))
        self.assertEqual(transfer.chunks, (bytes([13, 0]) + transfer.payload + bytes(6),))

    def test_indexed_chunks_and_native_limits(self):
        frames = [[[0] * 20 for _ in range(26)]] * 4
        transfer = encode_animation(frames, Topology(20, 26))
        self.assertEqual(len(transfer.payload), 6240)
        self.assertEqual(len(transfer.chunks), 65)
        self.assertEqual(transfer.chunks[-1][:2], bytes([97, 64]))
        for kwargs in ({'wire_speed': 0}, {'wire_speed': True}, {'chunk_capacity': 98}, {'chunk_capacity': 18}):
            with self.assertRaises(ValueError):
                encode_animation(frames, Topology(20, 26), **kwargs)
        with self.assertRaises(ValueError):
            encode_animation([[[0]]] * 256, Topology(1, 1))
        with self.assertRaises(ValueError):
            encode_animation(frames * 11, Topology(20, 26))


class TransferTests(unittest.IsolatedAsyncioTestCase):
    # trace: TEST-012 UR-007-AC2 SWR-007-AC2
    def setUp(self):
        self.command = SimpleNamespace(properties=['write-without-response'], max_write_without_response_size=20)
        self.bulk = SimpleNamespace(properties=['write-without-response'], max_write_without_response_size=98)
        self.rx = SimpleNamespace(properties=['notify'])
        service = Mock()
        service.characteristics = [self.command, self.bulk, self.rx]
        service.get_characteristic.side_effect = {COMMAND: self.command, BULK: self.bulk}.get
        self.client = Mock()
        self.client.services.get_service.side_effect = {SERVICE: service}.get
        self.client.stop_notify = AsyncMock()
        self.callback = None
        self.mode = 'ok'
        self.entered = asyncio.Event()

        async def subscribe(char, callback):
            self.callback = callback

        async def write(char, value, **kwargs):
            if char is self.command:
                body = decrypt(value)[1:6]
                if body[:4] == b'MANY':
                    if self.mode != 'header-timeout':
                        self.callback(self.rx, reply('MANYOK'))
                elif body == b'MANCP' and self.mode != 'finish-timeout':
                    self.callback(self.rx, reply('MANCPOK'))
            elif char is self.bulk:
                if self.mode == 'cancel':
                    self.entered.set()
                    await asyncio.Future()
                token = {'chunk-error': 'ERROR', 'unexpected': 'MANYOK'}.get(self.mode, 'REOK')
                self.callback(self.rx, reply(token))

        self.client.start_notify = AsyncMock(side_effect=subscribe)
        self.client.write_gatt_char = AsyncMock(side_effect=write)
        self.strip = Strip(self.client)
        self.strip.read_storage_capabilities = AsyncMock(return_value=StorageCapabilities(
            None, 'fixture', 2, 2, True, True, False))
        self.frames = [[[0, 0xff0000], [0x00ff00, 0x0000ff]]] * 2

    async def upload(self, **kwargs):
        return await self.strip.upload_animation(self.frames, topology=Topology(2, 2),
                                                 allow_overwrite=True, **kwargs)

    async def test_explicit_consent_before_any_io(self):
        self.strip.read_topology = AsyncMock()
        for operation in (self.strip.upload_animation(self.frames),
                          self.strip.upload_effect('XMAS 03'), self.strip.store_effect('XMAS 03')):
            with self.assertRaises(PermissionError):
                await operation
        self.strip.read_topology.assert_not_awaited()
        self.client.start_notify.assert_not_awaited()
        self.client.write_gatt_char.assert_not_awaited()

    async def test_handshake_and_payload_are_not_double_encrypted(self):
        result = await self.upload(chunk_capacity=18)
        self.assertIsInstance(result, AnimationUploadResult)
        self.assertEqual((result.frame_count, result.bytes_sent, result.chunks_sent), (2, 24, 2))
        calls = self.client.write_gatt_char.await_args_list
        self.assertEqual([c.args[0] for c in calls], [self.command, self.bulk, self.bulk, self.command])
        self.assertEqual(decrypt(calls[0].args[1])[1:5], b'MANY')
        transfer = encode_animation(self.frames, Topology(2, 2), chunk_capacity=18)
        self.assertEqual([c.args[1] for c in calls[1:3]], list(transfer.chunks))
        self.assertEqual(decrypt(calls[-1].args[1])[1:6], b'MANCP')
        self.assertEqual(result.power_cycle_persistence, 'unverified')
        self.client.stop_notify.assert_awaited_once_with(self.rx)

    async def test_buffered_name_uses_transfer_not_pixel_stream(self):
        self.strip.read_storage_capabilities.return_value = StorageCapabilities(None, 'fixture', 4, 2, True, True, False)
        result = await self.strip.play_effect('XMAS 03', topology=Topology(4, 2))
        self.assertIsInstance(result, AnimationUploadResult)
        self.assertEqual(result.frame_count, 4)
        self.assertTrue(all(c.args[0] is self.command or c.args[0] is self.bulk
                            for c in self.client.write_gatt_char.await_args_list))
        with self.assertRaisesRegex(ValueError, 'loop counts'):
            await self.strip.play_effect('XMAS 04', topology=Topology(4, 2), repeat=2)
        with self.assertRaisesRegex(ValueError, 'pacing'):
            await self.strip.play_effect('XMAS 04', topology=Topology(4, 2), pixel_delay=0.01)

    async def test_errors_timeouts_stop_without_retry_or_finish(self):
        for mode, expected in [('header-timeout', 'MANYOK'), ('chunk-error', 'ERROR'), ('unexpected', 'unexpected')]:
            with self.subTest(mode=mode):
                self.mode = mode
                self.client.write_gatt_char.reset_mock()
                with self.assertRaisesRegex(AnimationTransferError, expected):
                    await self.upload(ack_timeout=0.01)
                commands = [decrypt(c.args[1])[1:6] for c in self.client.write_gatt_char.await_args_list
                            if c.args[0] is self.command]
                self.assertEqual(commands, [b'MANY\x02'])
                self.assertFalse(self.strip._lock.locked())
        self.mode = 'finish-timeout'
        with self.assertRaisesRegex(AnimationTransferError, 'MANCP'):
            await self.upload(ack_timeout=0.01)

    async def test_preflight_before_header(self):
        self.bulk.max_write_without_response_size = 20
        with self.assertRaisesRegex(ValueError, 'write limit'):
            await self.upload(chunk_capacity=96)
        self.client.write_gatt_char.assert_not_awaited()

    async def test_cancellation_releases_subscription_and_lock(self):
        self.mode = 'cancel'
        task = asyncio.create_task(self.upload())
        await self.entered.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertFalse(self.strip._lock.locked())
        self.client.stop_notify.assert_awaited_once_with(self.rx)
        self.client.write_gatt_char.side_effect = None
        await asyncio.wait_for(self.strip.send(power(False)), timeout=1)

    async def test_total_deadline_cleans_up_without_commit(self):
        self.mode = 'cancel'
        with self.assertRaisesRegex(AnimationTransferError, 'total deadline'):
            await self.upload(total_timeout=0.01, ack_timeout=1)
        self.assertFalse(self.strip._lock.locked())
        self.client.stop_notify.assert_awaited_once_with(self.rx)
        commands = [decrypt(c.args[1])[1:6] for c in self.client.write_gatt_char.await_args_list
                    if c.args[0] is self.command]
        self.assertEqual(commands, [b'MANY\x02'])

    async def test_persistent_store_saves_only_after_completed_upload(self):
        # trace: TEST-013 UR-008-AC3 SWR-008-AC3
        self.command.properties.append('write')
        with patch('magical_led.client.asyncio.sleep', new_callable=AsyncMock) as sleep:
            result = await self.strip.store_animation(self.frames, overwrite=True, topology=Topology(2, 2))
        self.assertIsInstance(result, PersistentStoreResult)
        self.assertFalse(result.startup_speed_retained)
        self.assertFalse(result.power_cycle_checked_by_operation)
        commands = [decrypt(c.args[1]) for c in self.client.write_gatt_char.await_args_list
                    if c.args[0] is self.command]
        self.assertEqual([frame[1:6] for frame in commands], [b'MANY\x02', b'MANCP', b'SMVEW'])
        self.assertEqual(commands[-1], bytes.fromhex('06534d56455702000000000000000000'))
        self.assertTrue(self.client.write_gatt_char.await_args.kwargs['response'])
        self.assertEqual([call.args[0] for call in sleep.await_args_list], [1, 6])
        self.mode = 'chunk-error'
        self.client.write_gatt_char.reset_mock()
        with self.assertRaises(AnimationTransferError):
            await self.strip.store_animation(self.frames, overwrite=True, topology=Topology(2, 2))
        self.assertFalse(any(c.args[0] is self.command and decrypt(c.args[1])[1:6] == b'SMVEW'
                             for c in self.client.write_gatt_char.await_args_list))

    async def test_array_animation_play_does_not_save(self):
        result = await self.strip.play_animation(self.frames)
        self.assertEqual((result.frame_count, result.bytes_sent), (2, 24))
        commands = [decrypt(c.args[1])[1:6] for c in self.client.write_gatt_char.await_args_list
                    if c.args[0] is self.command]
        self.assertEqual(commands, [b'MANY\x02', b'MANCP'])

    async def test_unknown_profile_and_full_row_wipe_capacity_fail_before_writes(self):
        self.strip.read_storage_capabilities.return_value = StorageCapabilities(None, 'unknown', 2, 2, False, False, None)
        for operation in (self.strip.play_effect('XMAS 03'), self.strip.play_animation(self.frames),
                          self.strip.store_effect('XMAS 03', overwrite=True)):
            with self.assertRaises(StorageUnsupportedError):
                await operation
        self.strip.read_storage_capabilities.return_value = StorageCapabilities('STYPE26X20', 'TR2103R001-8', 20, 26, True, True, False)
        with self.assertRaisesRegex(ValueError, '65535'):
            await self.strip.store_effect('XMAS 01', overwrite=True)
        self.client.write_gatt_char.assert_not_awaited()

    async def test_capabilities_require_both_firmware_and_model(self):
        self.strip.read_storage_capabilities = Strip.read_storage_capabilities.__get__(self.strip, Strip)
        self.strip.read_topology = AsyncMock(return_value=Topology(20, 26, 'STYPE26X20'))
        self.strip.read_version = AsyncMock(return_value=b'TR2103R001-8\0')
        caps = await self.strip.read_storage_capabilities()
        self.assertTrue(caps.temporary_buffer_verified)
        self.assertTrue(caps.persistent_save_verified)
        self.assertFalse(caps.startup_speed_retained)
        self.strip._storage_caps = None
        self.strip.read_version.return_value = b'OTHER-FIRMWARE'
        caps = await self.strip.read_storage_capabilities()
        self.assertFalse(caps.temporary_buffer_verified)
        self.assertFalse(caps.persistent_save_verified)
        self.assertIsNone(caps.startup_speed_retained)
        self.strip._storage_caps = None
        self.strip.read_topology.return_value = Topology(20, 32, 'STYPE32X20')
        self.strip.read_version.return_value = b'TR2103R001-8\0'
        self.assertFalse((await self.strip.read_storage_capabilities()).persistent_save_verified)

    async def test_no_other_write_can_interleave_before_persistent_commit(self):
        ready, release = asyncio.Event(), asyncio.Event()
        original_sleep = asyncio.sleep

        async def settle(seconds):
            if seconds == 1:
                ready.set()
                await release.wait()
            else:
                await original_sleep(0)

        with patch('magical_led.client.asyncio.sleep', side_effect=settle):
            storing = asyncio.create_task(self.strip.store_animation(self.frames, overwrite=True, topology=Topology(2, 2)))
            await ready.wait()
            competing = asyncio.create_task(self.strip.send(power(False)))
            await original_sleep(0)
            self.assertFalse(competing.done())
            release.set()
            await storing
            await competing
        commands = [decrypt(c.args[1]) for c in self.client.write_gatt_char.await_args_list
                    if c.args[0] is self.command]
        self.assertEqual(commands[-2][1:6], b'SMVEW')
        self.assertEqual(commands[-1], power(False))
