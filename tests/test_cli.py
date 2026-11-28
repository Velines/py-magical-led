import subprocess
import sys
import unittest


class CliTests(unittest.TestCase):
    # trace: TEST-002 UR-002-AC1 SWR-002-AC1
    def invoke(self, *args):
        return subprocess.run([sys.executable, '-S', '-m', 'magical_led', *args],
                              capture_output=True, text=True, timeout=10)

    def test_preview_without_site_packages(self):
        result = self.invoke('--dry-run', 'color', '#123456')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ['plain 05454646450000000000000000000000',
                                                     'wire  10ca7ecf7236ff2de7db560a831ab6b8',
                                                     'wait  0.5 seconds',
                                                     'plain 07434f4c4f3412560000000000000000',
                                                     'wire  1153d5d091266d514a11b97aa7887092'])

    def test_usage_errors_before_ble(self):
        for args in [('on',), ('--dry-run', 'color', 'xyz'), ('--dry-run', 'effect', '256')]:
            with self.subTest(args=args):
                self.assertEqual(self.invoke(*args).returncode, 2)

    def test_animation_and_static_brightness(self):
        # trace: TEST-004 UR-004-AC1 SWR-004-AC1
        result = self.invoke('--dry-run', 'animation', '2')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('wire  c013d1b5ce18c35d396433690ceff2c1', result.stdout)
        result = self.invoke('--dry-run', 'brightness', '20', '--color', '00ff00')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([x for x in result.stdout.splitlines() if x.startswith('plain')],
                         ['plain 064c4947485414000000000000000000',
                          'plain 05454646450000000000000000000000',
                          'plain 07434f4c4fff00000000000000000000'])

    def test_offline_catalogue_is_not_inventory(self):
        # trace: TEST-005 UR-004-AC2 SWR-004-AC2
        import json
        result = self.invoke('presets', 'animations', '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertFalse(data['device_inventory'])
        self.assertEqual(len(data['presets']), 25)
        self.assertEqual([p['id'] for p in data['presets'] if p['observed_on']], [1, 2])
        for args in [('--device', 'unused', 'presets'), ('--dry-run', 'image', '0'),
                     ('--dry-run', 'animation', '26')]:
            self.assertEqual(self.invoke(*args).returncode, 2)

    def test_version_read_preview(self):
        result = self.invoke('--dry-run', 'version')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('129602', result.stdout)
        self.assertNotIn('wire ', result.stdout)

    def test_frame_preview_without_device(self):
        import json
        result = self.invoke('--dry-run', 'play', 'tests/fixtures/tiny-frames.json', '--repeat', '2')
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual((summary['width'], summary['height'], summary['frames'], summary['pixel_writes']),
                         (2, 2, 4, 10))
        self.assertIn('NOT read from device', summary['source'])
        self.assertFalse(summary['saved_to_controller'])
        for options in [('--fps', 'nan'), ('--fps', '0'), ('--repeat', '0')]:
            self.assertEqual(self.invoke('--dry-run', 'play', 'tests/fixtures/tiny-frames.json', *options).returncode, 2)

    def test_topology_preview_is_subscription_not_query(self):
        result = self.invoke('--dry-run', 'topology')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('no lighting/query writes', result.stdout)
        self.assertNotIn('wire ', result.stdout)

    def test_power_state_preview_is_subscription_not_query(self):
        result = self.invoke('--dry-run', 'power-state', '--wait', '2.5')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('2.5 seconds; no lighting/query writes', result.stdout)
        self.assertNotIn('wire ', result.stdout)
        self.assertEqual(self.invoke('--dry-run', 'power-state', '--wait', '0').returncode, 2)

    def test_library_effect_listing_and_preview(self):
        import json
        result = self.invoke('effects')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('XMAS 01 static', result.stdout)
        result = self.invoke('effects', '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual([effect['name'] for effect in data['effects']],
                         ['XMAS 01', 'XMAS 02', 'XMAS 01 static', 'XMAS 02 static'])
        self.assertIn('local library', data['source'])
        result = self.invoke('--dry-run', 'run-effect', 'XMAS 01', '--delivery', 'live',
                             '--width', '20', '--height', '26', '--repeat', '2')
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual((data['cycle_frames'], data['frames'], data['step_seconds'], data['pixel_writes']),
                         (4, 8, 2, 2340))
        result = self.invoke('--dry-run', 'run-effect', 'XMAS 02', '--delivery', 'live',
                             '--width', '20', '--height', '26')
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data['continuous'])
        self.assertIsNone(data['frames'])
        self.assertIsNone(data['pixel_writes'])
        result = self.invoke('--dry-run', 'run-effect', 'XMAS 01', '--delivery', 'live',
                             '--width', '20', '--height', '26', '--repeat', '1')
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertFalse(data['continuous'])
        self.assertEqual((data['frames'], data['pixel_writes']), (4, 1300))
        result = self.invoke('--dry-run', 'run-effect', 'XMAS 01', '--delivery', 'live',
                             '--width', '20', '--height', '26', '--forever')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['continuous'])
        for args in [('--device', 'unused', 'effects'), ('--dry-run', 'run-effect', 'XMAS 01'),
                     ('--dry-run', 'run-effect', 'XMAS 01', '--width', '20', '--height', '26', '--pixel-delay', '-1')]:
            self.assertEqual(self.invoke(*args).returncode, 2)

    def test_buffered_preview_and_consent_gate(self):
        import json
        result = self.invoke('--dry-run', 'run-effect', 'XMAS 01', '--width', '20', '--height', '26')
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual((data['frame_count'], data['bytes'], data['chunks']), (4, 6240, 65))
        self.assertEqual(data['header_plain'], '084d414e59040a186000000000000000')
        self.assertEqual(data['payload_sha256'], '6e1e31f5541846595de4a74d8e92fda3ffec2f42809aa77ab6c672f17d416caa')
        self.assertFalse(data['persistent_save_requested'])
        self.assertIsNone(data['save_command_hex'])
        result = self.invoke('--dry-run', 'upload-effect', 'XMAS 02', '--width', '20', '--height', '26')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['name'], 'XMAS 02')
        for command, flag in (('store-effect', '--overwrite'), ('upload-effect', '--replace-buffer')):
            result = self.invoke('--device', 'unused', command, 'XMAS 01')
            self.assertEqual(result.returncode, 1)
            self.assertIn(flag, result.stderr)
            self.assertNotIn('install live BLE support', result.stderr)
        result = self.invoke('--dry-run', 'run-effect', 'XMAS 01', '--width', '20', '--height', '26', '--repeat', '2')
        self.assertEqual(result.returncode, 1)
        self.assertIn('autonomous', result.stderr)

    def test_persistent_store_preview_is_separate_and_keeps_visual_resolution(self):
        import json
        result = self.invoke('--dry-run', 'store-effect', 'XMAS 01', '--width', '20', '--height', '26')
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        self.assertTrue(plan['persistent_save_requested'])
        self.assertTrue(plan['persistent_overwrite_consent_required'])
        self.assertEqual(plan['save_command_hex'], '06534d56455702000000000000000000')
        result = self.invoke('--dry-run', 'store-effect', 'XMAS 01 static', '--width', '20', '--height', '26')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['frame_count'], 1)
        result = self.invoke('--dry-run', 'run-effect', 'XMAS 01', '--persist', '--width', '20', '--height', '26')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['persistent_save_requested'])

    def test_live_dispatch_without_radio(self):
        from contextlib import asynccontextmanager, redirect_stdout, redirect_stderr
        from unittest.mock import AsyncMock, patch
        import io
        from magical_led.cli import main
        from magical_led import static_color
        strip = AsyncMock()

        @asynccontextmanager
        async def fake_connect(identifier, *, timeout):
            self.assertEqual(identifier, 'test-device')
            self.assertEqual(timeout, 20)
            yield strip

        with patch('magical_led.cli.connect', fake_connect):
            self.assertEqual(main(['--device', 'test-device', 'color', '00ff00', '--brightness', '20']), 0)
            strip.send_sequence.assert_awaited_once_with(static_color(0, 255, 0, level=20))
            strip.read_version.return_value = b'TR-test\0'
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(['--device', 'test-device', 'version']), 0)
            self.assertIn('text  TR-test', output.getvalue())
            strip.read_version.assert_awaited_once_with()
            from magical_led import Topology, PlaybackResult
            strip.read_topology.return_value = Topology(20, 26, 'STYPE26X20')
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(['--device', 'test-device', 'topology']), 0)
            self.assertIn('"pixel_count": 520', output.getvalue())
            for state, expected in ((True, 'on'), (False, 'off'), (None, 'unknown')):
                strip.read_power.return_value = state
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(main(['--device', 'test-device', 'power-state', '--wait', '2.5']), 0)
                self.assertEqual(output.getvalue().strip(), expected)
                self.assertEqual(strip.read_power.await_args.kwargs, {'timeout': 2.5})
            strip.play_frames.return_value = PlaybackResult(2, 6, 2.0)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(['--device', 'test-device', 'play', 'tests/fixtures/tiny-frames.json']), 0)
            strip.play_frames.assert_awaited_once()
            strip.play_effect.return_value = PlaybackResult(4, 1300, 8, 1, 3.0)
            errors = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(errors):
                self.assertEqual(main(['--device', 'test-device', 'run-effect', 'xmas 01', '--delivery', 'live']), 0)
            self.assertEqual(strip.play_effect.await_args.args, ('XMAS 01',))
            self.assertIsNone(strip.play_effect.await_args.kwargs['repeat'])
            self.assertIn('exceeded the requested interval', errors.getvalue())
            from magical_led import AnimationUploadResult
            native = AnimationUploadResult(4, 6240, 65, 10, 1.0, 'STYPE26X20', '074d414e43504f4b0000000000000000')
            strip.play_effect.return_value = native
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(main(['--device', 'test-device', 'run-effect', 'XMAS 01']), 0)
            self.assertIn('"host_streaming": false', output.getvalue())
            self.assertEqual(strip.play_effect.await_args.kwargs['delivery'], 'buffered')
            self.assertNotIn('allow_overwrite', strip.play_effect.await_args.kwargs)
            strip.upload_effect.return_value = native
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(['--device', 'test-device', 'upload-effect', 'XMAS 02', '--allow-overwrite']), 0)
            self.assertEqual(strip.upload_effect.await_args.args, ('XMAS 02',))
            from magical_led import PersistentStoreResult
            strip.store_effect.return_value = PersistentStoreResult(native, '06534d56455702000000000000000000', 8, False)
            errors = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(errors):
                self.assertEqual(main(['--device', 'test-device', 'store-effect', 'XMAS 01', '--overwrite']), 0)
            self.assertTrue(strip.store_effect.await_args.kwargs['overwrite'])
            self.assertIn('not its selected speed', errors.getvalue())

    def test_status_schedule_clock_batch_and_ergonomics(self):
        import io
        import json
        import os
        from contextlib import asynccontextmanager, redirect_stdout
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch
        from magical_led import (DeviceState, Schedule, ScheduleRule, Topology,
                                 VersionInfo, clock, color, effect, power, weekday_mask)
        from magical_led.cli import main

        # Dry-run previews for new commands (no BLE).
        res = self.invoke('--dry-run', 'status', '--wait', '2')
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn('129602', res.stdout)
        self.assertIn('03564552', res.stdout)
        self.assertIn('0453545343', res.stdout)

        res = self.invoke('--dry-run', 'sync-clock', '--time', '2026-11-28T18:30:45')
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn('0854494d4506121e2d', res.stdout)

        res = self.invoke('--dry-run', 'schedule', '--wait', '3')
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn('0453545343', res.stdout)

        res = self.invoke('--dry-run', 'set-schedule', '--on', '18:30', '--on-days', 'weekdays',
                          '--off', '23:00', '--off-days', 'daily', '--sync-clock')
        self.assertEqual(res.returncode, 0, res.stderr)
        plains = [line for line in res.stdout.splitlines() if line.startswith('plain ')]
        self.assertEqual(len(plains), 2)
        self.assertIn('0c53434844011f121e017f1700', plains[1])

        res = self.invoke('--dry-run', 'batch', 'on', 'color 00ff00', 'sleep 2', 'off', '--delay', '0.25')
        self.assertEqual(res.returncode, 0, res.stderr)
        lines = res.stdout.splitlines()
        self.assertIn('wait  0.25 seconds', lines)
        self.assertIn('wait  2 seconds', lines)
        self.assertEqual(len([line for line in lines if line.startswith('plain ')]), 4)

        # Invalid batch step fails before BLE.
        res = self.invoke('--dry-run', 'batch', 'not-a-command')
        self.assertEqual(res.returncode, 1)

        # MAGICAL_LED_DEVICE fallback + --json outputs + live batch over one connection.
        strip = AsyncMock()
        connect_calls = []

        @asynccontextmanager
        async def fake_connect(identifier, *, timeout):
            connect_calls.append(identifier)
            yield strip

        with patch.dict(os.environ, {'MAGICAL_LED_DEVICE': 'env-device'}):
            with patch('magical_led.cli.connect', fake_connect), \
                 patch('magical_led.cli.scan', AsyncMock(return_value=[SimpleNamespace(address='AA:BB', name='MT-1')])):
                # scan --json works even with MAGICAL_LED_DEVICE set.
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(main(['scan', '--json']), 0)
                self.assertEqual(json.loads(output.getvalue()), [{'address': 'AA:BB', 'name': 'MT-1'}])

                # --dry-run still wins over MAGICAL_LED_DEVICE.
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(main(['--dry-run', 'on']), 0)
                self.assertFalse(connect_calls)

                # version --json using MAGICAL_LED_DEVICE.
                strip.read_version.return_value = b'TR2103R001-8\0'
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(main(['version', '--json']), 0)
                self.assertEqual(json.loads(output.getvalue())['text'], 'TR2103R001-8')
                self.assertEqual(connect_calls[-1], 'env-device')

                # power-state --json
                strip.read_power.return_value = None
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(main(['power-state', '--json']), 0)
                self.assertEqual(json.loads(output.getvalue()), {'power': None, 'status': 'unknown', 'wait_seconds': 5})

                # status --json and human output
                sample_state = DeviceState(
                    firmware_raw_hex='545232313033523030312d3800',
                    firmware='TR2103R001-8',
                    version_info=VersionInfo(5, 1),
                    topology=Topology(20, 26, 'STYPE26X20'),
                    schedule=Schedule(ScheduleRule(True, weekday_mask('weekdays'), 18, 30), ScheduleRule()),
                    power=None,
                    read_at='2026-11-28T17:00:00+01:00',
                )
                strip.read_state.return_value = sample_state
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(main(['status', '--json']), 0)
                parsed_status = json.loads(output.getvalue())
                self.assertEqual(parsed_status['firmware'], 'TR2103R001-8')
                self.assertEqual(parsed_status['version_info'], {'spi': 5, 'ota': 1})
                self.assertIsNone(parsed_status['power'])

                # schedule --json
                strip.read_schedule.return_value = sample_state.schedule
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(main(['schedule', '--json']), 0)
                self.assertEqual(json.loads(output.getvalue())['on']['time'], '18:30')

                # set-schedule
                self.assertEqual(main(['set-schedule', '--on', '07:15', '--on-days', 'mon,fri', '--sync-clock']), 0)
                saved_sched = strip.set_schedule.await_args.args[0]
                self.assertEqual(saved_sched.on, ScheduleRule(True, weekday_mask('mon,fri'), 7, 15))
                self.assertEqual(saved_sched.off, ScheduleRule())
                self.assertTrue(strip.set_schedule.await_args.kwargs['sync_clock'])

                # batch executes multiple commands on a single connection
                connect_before = len(connect_calls)
                strip.send.reset_mock()
                self.assertEqual(main(['batch', 'on', 'color 00ff00', 'sleep 0', 'off', '--delay', '0']), 0)
                self.assertEqual(len(connect_calls), connect_before + 1)
                self.assertEqual(
                    [call.args[0] for call in strip.send.await_args_list],
                    [power(True), effect(0), color(0, 255, 0), power(False)],
                )
