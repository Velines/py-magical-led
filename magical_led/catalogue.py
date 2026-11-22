"""App 1.2.0 catalogues, not a directory fetched from a peripheral.

Hardware observations refer only to TR2103R001-8 / STYPE26X20 in the documented
2026-11-21 session. Effect 1..5 names are app labels; other names are descriptive
placeholders, not verified descriptions of patterns.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Preset:
    kind: str
    id: int
    name: str
    observed_on: str | None = None


_MODEL = 'TR2103R001-8 / STYPE26X20'
EFFECTS = tuple(Preset('effect', i, name, _MODEL if i in (0, 3, 4) else None)
                for i, name in enumerate(('Static / effect disabled', 'Flashing',
                                          'Hot Wheels', 'Meteor', 'Chase', 'Explosion')))
ANIMATIONS = tuple(Preset('animation', i, f'Animation {i}', _MODEL if i in (1, 2) else None)
                   for i in range(1, 26))
IMAGES = tuple(Preset('image', i, f'Image {i}') for i in range(1, 26))


def catalogue(kind: str = 'all') -> tuple[Preset, ...]:
    """List app-supported IDs offline; observed_on is not universal compatibility."""
    groups = {'effects': EFFECTS, 'animations': ANIMATIONS, 'images': IMAGES,
              'all': EFFECTS + ANIMATIONS + IMAGES}
    if kind not in groups:
        raise ValueError('expected effects, animations, images or all')
    return groups[kind]


def preset_id(value: int, maximum: int, *, minimum: int = 1) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'preset ID must be an integer {minimum}..{maximum}')
    return value
