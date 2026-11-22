"""Reported logical grids and bounded RGB arrays for unsaved W3 playback.

Native frame convention is rows top-to-bottom, columns left-to-right for the
mounting documented in docs/topology-live-frames.md. BLE reports dimensions,
not mounting orientation or physical lengths. No device pixel state lives here.
"""
from dataclasses import dataclass
from operator import index
from itertools import islice
import re

RGB = tuple[int, int, int]
Frame = tuple[RGB, ...]  # Native row-major buffer, independent of input objects.
MAX_FRAMES = 256
MAX_TOTAL_PIXELS = 1_000_000

# Screen.getLedSize, not an arbitrary reversal of the numbers in STYPE.
_APP_GRIDS = {'STYPE38X20': (20, 38), 'STYPE32X20': (20, 32),
              'STYPE26X20': (20, 26), 'STYPE100X1': (100, 1),
              'STYPE20X25': (25, 20)}


@dataclass(frozen=True)
class Topology:
    """Logical columns/rows; reported_type=None denotes caller-supplied geometry.

    Interpretation: app grid + W3 row/column coordinates. Physical mapping was
    tested only on TR2103R001-8 / STYPE26X20. Other grids require calibration.
    """
    width: int
    height: int
    reported_type: str | None = None

    def __post_init__(self):
        if any(type(n) is not int or not 1 <= n <= 256 for n in (self.width, self.height)):
            raise ValueError('grid dimensions must be integer values 1..256')
        if self.reported_type is not None and _APP_GRIDS.get(self.reported_type) != (self.width, self.height):
            raise ValueError('unsupported report or dimensions inconsistent with the app profile')

    @property
    def pixel_count(self) -> int:
        return self.width * self.height


def parse_topology(frame: bytes) -> Topology | None:
    """Parse one decrypted notification. Ignore unrelated/malformed packets.

    A syntactically valid but unknown STYPE raises ValueError rather than
    guessing how its reported numbers map to the native coordinate grid.
    """
    # trace: SWR-005-AC1
    if not isinstance(frame, bytes) or len(frame) != 16:
        return None
    n = frame[0]
    if not 1 <= n <= 15 or any(frame[n + 1:]):
        return None
    payload = frame[1:n + 1]
    if re.fullmatch(rb'STYPE[0-9]+X[0-9]+', payload) is None:
        return None
    report = payload.decode('ascii')
    if report not in _APP_GRIDS:
        raise ValueError(f'unsupported controller grid: {report}; no mapping guessed')
    return Topology(*_APP_GRIDS[report], reported_type=report)


@dataclass(frozen=True)
class FrameMapping:
    """Transpose input first, then flip native columns/rows as requested."""
    transpose: bool = False
    flip_x: bool = False
    flip_y: bool = False

    def __post_init__(self):
        if any(type(v) is not bool for v in (self.transpose, self.flip_x, self.flip_y)):
            raise ValueError('transpose and flips must be booleans')

    def input_size(self, topology: Topology) -> tuple[int, int]:
        return ((topology.height, topology.width) if self.transpose
                else (topology.width, topology.height))

    def native_xy(self, x: int, y: int, topology: Topology) -> tuple[int, int]:
        x, y = (y, x) if self.transpose else (x, y)
        return (topology.width - 1 - x if self.flip_x else x,
                topology.height - 1 - y if self.flip_y else y)


def _rgb(value) -> RGB:
    if isinstance(value, bool):
        raise ValueError('boolean is not a color')
    try:
        packed = index(value)
    except TypeError:
        try:
            components = tuple(islice(iter(value), 4))
            if len(components) != 3 or any(isinstance(c, bool) for c in components):
                raise ValueError('expected three integer RGB channels')
            channels = tuple(index(c) for c in components)
        except (TypeError, ValueError) as exc:
            raise ValueError('expected RGB triple or integer 0xRRGGBB') from exc
        if any(not 0 <= c <= 255 for c in channels):
            raise ValueError('RGB channels must be 0..255')
        return channels
    if not 0 <= packed <= 0xffffff:
        raise ValueError('packed RGB must be 0x000000..0xFFFFFF')
    return (packed >> 16, (packed >> 8) & 255, packed & 255)


def prepare_frames(frames, topology: Topology,
                   mapping: FrameMapping = FrameMapping()) -> tuple[Frame, ...]:
    """Validate/copy 1..256 frames before lighting writes, with no resizing.

    Accept rows of RGB triples or packed integer colors, including integer
    array scalars with __index__. NumPy is not imported or required. Generators
    of frames are allowed but must terminate within MAX_FRAMES; rows/frames
    must have lengths. No caller buffer is retained or mutated.
    """
    # trace: SWR-005-AC2
    if not isinstance(topology, Topology) or not isinstance(mapping, FrameMapping):
        raise ValueError('expected Topology and FrameMapping instances')
    width, height = mapping.input_size(topology)
    prepared = []
    try:
        iterator = iter(frames)
    except TypeError as exc:
        raise ValueError('frames must be an iterable of 2D arrays') from exc
    for frame_index, frame in enumerate(iterator):
        if frame_index >= MAX_FRAMES:
            raise ValueError(f'at most {MAX_FRAMES} frames are accepted per playback')
        if (frame_index + 1) * topology.pixel_count > MAX_TOTAL_PIXELS:
            raise ValueError(f'normalized frames exceed the {MAX_TOTAL_PIXELS} pixel memory bound')
        try:
            rows = tuple(islice(iter(frame), height + 1))
            if len(frame) != height or len(rows) != height:
                raise ValueError(f'expected {height} rows of {width} pixels')
            native = [None] * topology.pixel_count
            for y, row in enumerate(rows):
                values = tuple(islice(iter(row), width + 1))
                if len(row) != width or len(values) != width:
                    raise ValueError(f'expected {height} rows of {width} pixels')
                for x, value in enumerate(values):
                    nx, ny = mapping.native_xy(x, y, topology)
                    native[ny * topology.width + nx] = _rgb(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f'frame {frame_index}: {exc}') from exc
        prepared.append(tuple(native))
    if not prepared:
        raise ValueError('at least one frame is required')
    return tuple(prepared)


@dataclass(frozen=True)
class PlaybackResult:
    """Counts of completed submissions, not visible-rendering acknowledgements.

    elapsed_seconds covers frame writes and requested display holds, excluding
    input validation, topology discovery and initial edit-mode setup.
    overrun_frames counts write/pacing durations beyond the requested interval,
    including the initial full draw. max_frame_write_seconds includes pixel
    pacing but excludes the extra hold used to reach the interval.
    """
    frames_sent: int
    pixel_writes: int
    elapsed_seconds: float
    overrun_frames: int = 0
    max_frame_write_seconds: float = 0.0

    @property
    def effective_fps(self) -> float:
        return self.frames_sent / self.elapsed_seconds if self.elapsed_seconds else 0.0
