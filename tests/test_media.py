import unittest
from types import SimpleNamespace
from unittest.mock import patch

from magical_led import Topology, load_image_frames, prepare_frames


class _FakeFrame:
    def __init__(self, pixels):
        self._pixels = pixels

    def convert(self, mode):
        assert mode == 'RGB'
        return self

    def resize(self, size, resample=None):
        assert size == (2, 2)
        return self

    def getdata(self):
        return self._pixels


class _FakeImage:
    def __init__(self, frames):
        self._frames = frames

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class MediaTests(unittest.TestCase):
    def test_validation_before_pillow_import(self):
        with self.assertRaises(ValueError):
            load_image_frames('x.png', 'not-a-topology')
        with self.assertRaises(ValueError):
            load_image_frames('x.png', Topology(2, 2), max_frames=0)
        with self.assertRaises(ValueError):
            load_image_frames('x.png', Topology(2, 2), resample='cubic')

    def test_missing_pillow_raises_clear_error(self):
        with patch('magical_led.media._pillow', side_effect=RuntimeError("install image support: python -m pip install '.[images]'")):
            with self.assertRaisesRegex(RuntimeError, r'\[images\]'):
                load_image_frames('x.png', Topology(2, 2))

    def test_loads_multiframe_image_into_immutable_frames(self):
        f1 = _FakeFrame([(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)])
        f2 = _FakeFrame([(0, 0, 0), (1, 2, 3), (4, 5, 6), (7, 8, 9)])
        fake_image_mod = SimpleNamespace(
            Resampling=SimpleNamespace(NEAREST=0, BILINEAR=1, LANCZOS=2),
            open=lambda _src: _FakeImage([f1, f2]),
        )
        fake_seq_mod = SimpleNamespace(Iterator=lambda img: iter(img._frames))
        with patch('magical_led.media._pillow', return_value=(fake_image_mod, fake_seq_mod)):
            frames = load_image_frames('anim.gif', Topology(2, 2), max_frames=10)
        self.assertEqual(len(frames), 2)
        self.assertEqual(frames[0], (((255, 0, 0), (0, 255, 0)), ((0, 0, 255), (255, 255, 255))))
        self.assertEqual(frames[1], (((0, 0, 0), (1, 2, 3)), ((4, 5, 6), (7, 8, 9))))
        prepare_frames(frames, Topology(2, 2))
