import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import AsyncMock

from magical_led import (
    Topology, FrameMapping, StripedEffect, StaticEffect,
    XMAS_01, XMAS_02, XMAS_01_STATIC, XMAS_02_STATIC,
    get_effect, list_effects, Strip, PlaybackResult,
)


class EffectTests(unittest.TestCase):
    # trace: TEST-009 UR-006-AC1 SWR-006-AC1
    def test_collection_names_colors_and_immutability(self):
        self.assertEqual(list_effects(), (XMAS_01, XMAS_02, XMAS_01_STATIC, XMAS_02_STATIC))
        self.assertIs(get_effect('  xmas   01 '), XMAS_01)
        self.assertIs(get_effect('xmas 01 static'), XMAS_01_STATIC)
        self.assertEqual(XMAS_01.colors, ((255, 0, 0), (0, 255, 0)))
        self.assertEqual(XMAS_02.colors, ((255, 0, 0), (255, 255, 255)))
        self.assertEqual((XMAS_01.transition, XMAS_02.transition), ('cut', 'cut'))
        self.assertIsInstance(XMAS_01_STATIC, StaticEffect)
        self.assertIs(XMAS_01_STATIC.base, XMAS_01)
        self.assertIs(XMAS_02_STATIC.base, XMAS_02)
        self.assertFalse(hasattr(XMAS_01, 'transport'))
        self.assertEqual(XMAS_01.step_seconds, 2)
        self.assertEqual(XMAS_02.strips_per_band, 2)
        with self.assertRaises(FrozenInstanceError):
            XMAS_01.name = 'changed'
        for bad in ('NOPE', '', None):
            with self.assertRaises(ValueError):
                get_effect(bad)

    def test_all_rows_bands_and_one_column_right_shift(self):
        topology = Topology(20, 26)
        for effect in (XMAS_01, XMAS_02):
            with self.subTest(name=effect.name):
                frames = effect.phase_frames(topology)
                self.assertEqual(len(frames), 4)
                first, second = effect.colors
                self.assertEqual(frames[0][0], (first, first, second, second) * 5)
                for i, frame in enumerate(frames):
                    self.assertEqual(len(frame), 26)
                    self.assertTrue(all(row == frame[0] for row in frame))
                    following = frames[(i + 1) % len(frames)]
                    self.assertEqual(following[0], frame[0][-1:] + frame[0][:-1])
                    # Ten columns change, five in each color direction, not two total.
                    self.assertEqual(sum(a != b for a, b in zip(frame[0], following[0])), 10)
                    self.assertEqual(sum(a == first and b == second for a, b in zip(frame[0], following[0])), 5)

    def test_reverse_partial_bands_and_small_widths(self):
        for width, expected_period in ((1, 1), (2, 1), (4, 4), (5, 5), (20, 4)):
            frames = XMAS_01.phase_frames(Topology(width, 2), direction='left')
            self.assertEqual(len(frames), expected_period)
            for i, frame in enumerate(frames):
                following = frames[(i + 1) % len(frames)]
                self.assertEqual(following[0], frame[0][1:] + frame[0][:1])

    def test_static_effects_return_first_frame_only(self):
        topology = Topology(20, 26)
        for effect, base in ((XMAS_01_STATIC, XMAS_01), (XMAS_02_STATIC, XMAS_02)):
            frames = effect.frames(topology)
            self.assertEqual(len(frames), 1)
            self.assertEqual(frames[0], base.phase_frames(topology)[0])
            self.assertEqual(effect.resolve_delivery('auto'), 'buffered')

    def test_wipe_advances_all_changed_strings_before_next_row(self):
        # trace: TEST-014 UR-008-AC1 SWR-008-AC1
        topology = Topology(20, 26)
        wipe = StripedEffect('Wipe', ((255, 0, 0), (0, 255, 0)), transition='wipe_down')
        frames = wipe.frames(topology)
        phases = wipe.phase_frames(topology)
        self.assertEqual(len(frames), 104)
        self.assertEqual(frames[0], phases[0])
        self.assertEqual(frames[26], phases[1])
        self.assertAlmostEqual(len(frames) * wipe.frame_interval(topology), 8)
        for i, current in enumerate(frames):
            following = frames[(i + 1) % len(frames)]
            rows = {y for y in range(26) if current[y] != following[y]}
            self.assertEqual(rows, {i % 26})
            y = i % 26
            self.assertEqual(sum(a != b for a, b in zip(current[y], following[y])), 10)
        self.assertEqual(len(XMAS_01.frames(topology)), 4)
        self.assertEqual(XMAS_01.frames(topology), XMAS_01.phase_frames(topology))

    def test_invalid_definition_and_memory_bounds(self):
        for kwargs in ({'name': ''}, {'colors': [(255, 0, 0), (0, 255, 0)]},
                       {'colors': ((256, 0, 0), (0, 0, 0))}, {'strips_per_band': True},
                       {'step_seconds': float('nan')}, {'step_seconds': 0}):
            args = {'name': 'test', 'colors': ((255, 0, 0), (0, 0, 0)), **kwargs}
            with self.assertRaises(ValueError):
                StripedEffect(**args)
        with self.assertRaises(ValueError):
            XMAS_01.frames(Topology(20, 26), direction='up')
        with self.assertRaises(ValueError):
            StaticEffect('', XMAS_01)
        with self.assertRaises(ValueError):
            StaticEffect('bad', 'not-an-effect')
        unique = StripedEffect('large', tuple((i, 0, 0) for i in range(256)), strips_per_band=1)
        with self.assertRaisesRegex(ValueError, 'bounds'):
            unique.frames(Topology(256, 256))


class EffectDelegationTests(unittest.IsolatedAsyncioTestCase):
    async def test_helper_uses_intervals_and_shared_player(self):
        # Delegation only; actual transport/pacing/cancellation tested in test_frames.
        strip = Strip.__new__(Strip)
        strip.read_topology = AsyncMock(return_value=Topology(20, 26, 'STYPE26X20'))
        strip.play_frames = AsyncMock(return_value=PlaybackResult(4, 1, 8))
        result = await strip.play_effect('XMAS 02', brightness=20, delivery='live')
        args, kwargs = strip.play_frames.await_args
        self.assertEqual(args[0], XMAS_02.frames(Topology(20, 26)))
        self.assertEqual(kwargs['fps'], 0.5)
        self.assertEqual(kwargs['pixel_delay'], 0)
        self.assertEqual(result.frames_sent, 4)
        strip.read_topology.reset_mock()
        with self.assertRaises(ValueError):
            await strip.play_effect('unknown')
        strip.read_topology.assert_not_awaited()

    async def test_mapping_uses_input_dimensions(self):
        strip = Strip.__new__(Strip)
        strip.play_frames = AsyncMock(return_value=PlaybackResult(4, 1, 8))
        topology = Topology(20, 26)
        mapping = FrameMapping(transpose=True, flip_x=True)
        await strip.play_effect('XMAS 01', topology=topology, mapping=mapping, direction='left', delivery='live')
        args, kwargs = strip.play_frames.await_args
        self.assertEqual(len(args[0][0]), 20)
        self.assertEqual(len(args[0][0][0]), 26)
        self.assertIs(kwargs['mapping'], mapping)
