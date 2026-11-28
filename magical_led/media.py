"""Optional image and animated GIF loader for py-magical-led.

Requires Pillow (`python -m pip install '.[images]'`). No Pillow import occurs
at package import time so the core library stays standard-library only.
"""
from os import PathLike

from .frames import MAX_FRAMES, MAX_TOTAL_PIXELS, RGB, Topology


def _pillow():
    try:
        from PIL import Image, ImageSequence
    except ImportError as exc:
        raise RuntimeError(
            "install image support: python -m pip install '.[images]'"
        ) from exc
    return Image, ImageSequence


def load_image_frames(
    source: str | PathLike[str],
    topology: Topology,
    *,
    max_frames: int = MAX_FRAMES,
    resample: str = 'nearest',
) -> tuple[tuple[tuple[RGB, ...], ...], ...]:
    """Load a PNG/JPEG/GIF (or other Pillow image) into immutable frames[step][y][x].

    Each frame is converted to RGB and resized to (topology.width, topology.height).
    Animated images (e.g. GIF/WebP) yield one frame per animation frame up to max_frames.
    """
    if not isinstance(topology, Topology):
        raise ValueError('expected a Topology')
    if type(max_frames) is not int or not 1 <= max_frames <= MAX_FRAMES:
        raise ValueError(f'max_frames must be an integer 1..{MAX_FRAMES}')
    if resample not in ('nearest', 'bilinear', 'lanczos'):
        raise ValueError('resample must be nearest, bilinear, or lanczos')

    Image, ImageSequence = _pillow()
    resampling = getattr(Image, 'Resampling', Image)
    filter_map = {
        'nearest': resampling.NEAREST,
        'bilinear': resampling.BILINEAR,
        'lanczos': resampling.LANCZOS,
    }
    resampler = filter_map[resample]

    frames: list[tuple[tuple[RGB, ...], ...]] = []
    with Image.open(source) as img:
        for index, raw_frame in enumerate(ImageSequence.Iterator(img)):
            if index >= max_frames:
                break
            if (index + 1) * topology.pixel_count > MAX_TOTAL_PIXELS:
                raise ValueError(f'loaded frames exceed the {MAX_TOTAL_PIXELS} pixel memory bound')
            rgb_img = raw_frame.convert('RGB').resize(
                (topology.width, topology.height), resample=resampler
            )
            pixels = list(rgb_img.getdata())
            rows = tuple(
                tuple(
                    (int(r), int(g), int(b))
                    for r, g, b in pixels[y * topology.width:(y + 1) * topology.width]
                )
                for y in range(topology.height)
            )
            frames.append(rows)
    if not frames:
        raise ValueError('image contained no frames')
    return tuple(frames)
