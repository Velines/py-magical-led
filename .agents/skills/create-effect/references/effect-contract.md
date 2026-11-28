# py-magical-led Effect Contract

## Coordinate System & Frame Format

- `frames(topology, *, direction='right')` returns an immutable tuple of frames:
  `tuple[tuple[tuple[RGB, ...], ...], ...]`
  indexed as `frames[step][y][x]`.
- `RGB` is `tuple[int, int, int]` with each channel `0 <= c <= 255` and `type(c) is int`.
- `y` runs `0 .. topology.height - 1` (top to bottom).
- `x` runs `0 .. topology.width - 1` (left to right).
- Never hard-code `20×26`; always use `topology.width` and `topology.height` and handle edge cases like `Topology(1, 1)` or `Topology(5, 3)`.

## Bounds & Hardware Constraints

- **Library live bounds** (`magical_led/frames.py`):
  - `1 <= len(frames) <= MAX_FRAMES` (`256`)
  - `len(frames) * topology.pixel_count <= MAX_TOTAL_PIXELS` (`1_000_000`)
- **Controller buffered / persistent bounds** (`magical_led/buffered.py`):
  - Header limit: `<= 255` frames and `<= 65,535` payload bytes (`frames * width * height * 3`).
  - 96-byte indexed chunk limit (1-byte chunk index): `<= 24,576` payload bytes.
  - On the verified `STYPE26X20` (`20×26`, 520 pixels, 1,560 bytes/frame) grid, that is **at most 15 frames**.
- **Separation of concerns**:
  - Effect definitions are pure visual definitions. Never put BLE, transport, overwrite, or storage logic/fields on an effect.
  - `frames()` must produce the exact same visual sequence regardless of delivery (`live`, `buffered`) or storage (`store_effect`).

## Required Interface

Every entry in `magical_led.effects._EFFECTS` must be a `@dataclass(frozen=True)` with JSON-serializable fields (compatible with `dataclasses.asdict`) implementing:

- `name: str` — nonempty, unique after `' '.join(name.split()).casefold()`.
- `frames(self, topology: Topology, *, direction: str = 'right') -> tuple[tuple[tuple[RGB, ...], ...], ...]`
  - Must validate `isinstance(topology, Topology)` and `direction in ('right', 'left')`.
  - Must raise `ValueError` on invalid input or exceeded `MAX_FRAMES` / `MAX_TOTAL_PIXELS`.
- `frame_interval(self, topology: Topology) -> float`
  - Returns a finite positive float (seconds per rendered frame) with a finite reciprocal `1 / interval`.
- `resolve_delivery(self, delivery: str = 'auto') -> str`
  - Must validate `delivery in ('auto', 'live', 'buffered')` and raise `ValueError` otherwise.
  - For `'auto'`, return `'buffered'` if the effect is intended for controller-buffered playback (`<= 15` frames on `20×26`), or `'live'` otherwise.
  - For explicit `'live'` or `'buffered'`, return `delivery` unchanged.

Optional attributes used by the CLI (`magical-led effects` and `run-effect --dry-run`):
- `description: str` — short human-readable summary.
- `colors: tuple[RGB, ...]` — palette shown in `magical-led effects`.
- `step_seconds: float` — target step duration shown in dry-run output.
- `transition: str` — transition label shown in dry-run output.

## Minimal Custom Effect Template

```python
@dataclass(frozen=True)
class CustomEffect:
    """Short description of the visual pattern."""

    name: str
    colors: tuple[RGB, ...]
    step_seconds: float = 0.25
    frame_count: int = 12
    description: str = ''

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError('effect name must be nonempty')
        if (not isinstance(self.colors, tuple) or not self.colors
                or any(not isinstance(rgb, tuple) or len(rgb) != 3
                       or any(type(c) is not int or not 0 <= c <= 255 for c in rgb)
                       for rgb in self.colors)):
            raise ValueError('colors must be a nonempty immutable tuple of integer RGB triples')
        if type(self.frame_count) is not int or not 1 <= self.frame_count <= MAX_FRAMES:
            raise ValueError(f'frame_count must be an integer 1..{MAX_FRAMES}')
        if (isinstance(self.step_seconds, bool) or not isinstance(self.step_seconds, (int, float))
                or not math.isfinite(self.step_seconds) or self.step_seconds <= 0
                or not math.isfinite(1 / self.step_seconds)):
            raise ValueError('step_seconds must have a finite positive value and reciprocal')

    def frames(self, topology: Topology, *, direction: str = 'right'):
        if not isinstance(topology, Topology):
            raise ValueError('expected a Topology')
        if direction not in ('right', 'left'):
            raise ValueError('direction must be right or left')
        if self.frame_count > MAX_FRAMES or self.frame_count * topology.pixel_count > MAX_TOTAL_PIXELS:
            raise ValueError('rendered effect exceeds playback frame/pixel bounds')
        # Build immutable tuple[frame][y][x] here.
        ...

    def frame_interval(self, topology: Topology) -> float:
        return self.step_seconds

    def resolve_delivery(self, delivery: str = 'auto') -> str:
        if delivery not in ('auto', 'live', 'buffered'):
            raise ValueError('delivery must be auto, live or buffered')
        return ('buffered' if self.frame_count <= 15 else 'live') if delivery == 'auto' else delivery
```
