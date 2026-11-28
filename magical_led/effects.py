"""Library-defined live effects, separate from the controller's preset catalogue.

Each effect renders immutable frame[y][x] RGB arrays. Visual transition style
is independent of delivery or persistent storage. Names stay local.
"""
from dataclasses import dataclass
import math

from .frames import RGB, Topology, MAX_FRAMES, MAX_TOTAL_PIXELS


@dataclass(frozen=True)
class StripedEffect:
    """Uniform vertical bands, cyclically translated one column per time step.

    Forward means right in input-array space; explicit mapping flips can reverse
    the physical direction. Edge wrapping rotates the actual finite-width image,
    including partial bands on widths not divisible by the pattern length.
    """
    name: str
    colors: tuple[RGB, ...]
    strips_per_band: int = 2
    step_seconds: float = 2.0
    transition: str = 'cut'

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError('effect name must be nonempty')
        if self.transition not in ('cut', 'wipe_down'):
            raise ValueError('transition must be cut or wipe_down')
        if (not isinstance(self.colors, tuple) or len(self.colors) < 2
                or any(not isinstance(rgb, tuple) or len(rgb) != 3
                       or any(type(c) is not int or not 0 <= c <= 255 for c in rgb)
                       for rgb in self.colors)):
            raise ValueError('colors must be an immutable tuple of integer RGB triples')
        if type(self.strips_per_band) is not int or not 1 <= self.strips_per_band <= 256:
            raise ValueError('strips_per_band must be an integer 1..256')
        if (isinstance(self.step_seconds, bool) or not isinstance(self.step_seconds, (int, float))
                or not math.isfinite(self.step_seconds) or self.step_seconds <= 0
                or not math.isfinite(1 / self.step_seconds)):
            raise ValueError('step_seconds must have a finite positive value and reciprocal')

    def phase_frames(self, topology: Topology, *, direction: str = 'right'):
        """Full paired-color pictures, before applying the visual transition.

        On the calibrated 20-string device these effects each have four phases.
        A width of one band or less may have no visible movement; do not invent
        colors that were not present in the initial finite-width picture.
        """
        # trace: SWR-006-AC1
        if not isinstance(topology, Topology):
            raise ValueError('expected a Topology')
        if direction not in ('right', 'left'):
            raise ValueError('direction must be right or left')
        base = tuple(self.colors[(x // self.strips_per_band) % len(self.colors)]
                     for x in range(topology.width))
        period = next(n for n in range(1, topology.width + 1)
                      if all(base[x] == base[(x - n) % topology.width] for x in range(topology.width)))
        if period > MAX_FRAMES or topology.pixel_count * period > MAX_TOTAL_PIXELS:
            raise ValueError('generated effect exceeds playback frame/pixel bounds')
        sign = 1 if direction == 'right' else -1
        return tuple(tuple(tuple(base[(x - sign * phase) % topology.width]
                                 for x in range(topology.width))
                           for _ in range(topology.height))
                     for phase in range(period))

    def frames(self, topology: Topology, *, direction: str = 'right'):
        """Render one cyclic visual sequence, identically for play and storage.

        wipe_down changes ALL affected columns at row y before advancing to
        row y+1. Frame 0 is the initial complete picture. The last intermediate
        frame joins frame 0 to complete the last row at the cycle boundary.
        There is no delivery-dependent simplification or persistent side effect.
        """
        # trace: SWR-008-AC1
        phases = self.phase_frames(topology, direction=direction)
        if self.transition == 'cut' or len(phases) == 1:
            return phases
        count = len(phases) * topology.height
        if count > MAX_FRAMES or count * topology.pixel_count > MAX_TOTAL_PIXELS:
            raise ValueError('rendered transition exceeds playback frame/pixel bounds')
        frames = [phases[0]]
        for i, current in enumerate(phases):
            following = phases[(i + 1) % len(phases)]
            for rows in range(1, topology.height + 1):
                if i == len(phases) - 1 and rows == topology.height:
                    continue  # Next loop's frame 0 completes the cycle.
                frames.append(following[:rows] + current[rows:])
        return tuple(frames)

    def frame_interval(self, topology: Topology) -> float:
        """Requested interval per rendered frame, not extra time after writing."""
        return self.step_seconds / topology.height if self.transition == 'wipe_down' else self.step_seconds

    def resolve_delivery(self, delivery: str = 'auto') -> str:
        """Auto is a playback capability preference, never a storage decision."""
        if delivery not in ('auto', 'live', 'buffered'):
            raise ValueError('delivery must be auto, live or buffered')
        return ('live' if self.transition == 'wipe_down' else 'buffered') if delivery == 'auto' else delivery


@dataclass(frozen=True)
class StaticEffect:
    """A single static frame derived from a striped effect."""

    name: str
    base: StripedEffect

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError('effect name must be nonempty')
        if not isinstance(self.base, StripedEffect):
            raise ValueError('base must be a StripedEffect')

    def frames(self, topology: Topology, *, direction: str = 'right'):
        return (self.base.phase_frames(topology, direction=direction)[0],)

    def frame_interval(self, topology: Topology) -> float:
        return self.base.step_seconds

    def resolve_delivery(self, delivery: str = 'auto') -> str:
        if delivery not in ('auto', 'live', 'buffered'):
            raise ValueError('delivery must be auto, live or buffered')
        return 'buffered' if delivery == 'auto' else delivery


XMAS_01 = StripedEffect('XMAS 01', ((255, 0, 0), (0, 255, 0)))
XMAS_02 = StripedEffect('XMAS 02', ((255, 0, 0), (255, 255, 255)))
XMAS_01_STATIC = StaticEffect('XMAS 01 static', XMAS_01)
XMAS_02_STATIC = StaticEffect('XMAS 02 static', XMAS_02)
_EFFECTS = (XMAS_01, XMAS_02, XMAS_01_STATIC, XMAS_02_STATIC)


def list_effects() -> tuple[StripedEffect | StaticEffect, ...]:
    """Return the immutable library collection, not a BLE device inventory."""
    return _EFFECTS


def get_effect(name: str) -> StripedEffect | StaticEffect:
    """Resolve a collection name, ignoring case and redundant whitespace."""
    if isinstance(name, str):
        normalized = ' '.join(name.split()).casefold()
        for effect in _EFFECTS:
            if effect.name.casefold() == normalized:
                return effect
    raise ValueError(f'unknown library effect: {name!r}; use list_effects()')
