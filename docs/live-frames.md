# BLE topology and custom RGB effects · 0.3.0

For controller-managed whole-frame switching instead of progressive live W3
updates, use `play_animation` on a verified temporary-buffer profile. Persistent
replacement is a separate `store_animation(overwrite=True)` operation. Both
accept the same arrays as this live API, within native capacity bounds. See
[current playback/storage API](effect-playback-storage.md); the earlier 0.5
raw buffered transfer remains available as an explicit advanced operation.

## The measured coordinate convention

The tested controller reports **`STYPE26X20`** over encrypted BLE notifications.
The app's `Screen.getLedSize` interprets that model as **20 columns × 26 rows**.
Interactive markers established that, in the user's front view:

- 20 strings run **left to right**; string 0 is the leftmost.
- Each string has 26 addressed positions **top to bottom**.
- A frame is indexed **`frame[y][x]`**: y is row/position on the string, x is string.
- The W3 point frame takes coordinates **`(y, x)`**, then **green, red, blue**.

Origin `(0,0)` was red at top-left; `(0,1)` green at the top of the next string;
`(1,0)` blue at the second LED of the first string; `(25,0)` magenta at its
bottom; `(0,19)` yellow at the top of the farthest string. See
[calibration evidence](topology-live-frames.md). No serpentine compensation is
needed: these are already logical 2D coordinates, not raw serial LED offsets.

BLE did **not** tell us the mounting direction, the physical length/width in
metres, or whether every possible logical pixel is actually populated. The
string interpretation and orientation above are human-confirmed for this setup,
not universally encoded in STYPE. Other controllers/mountings require calibration.

## Discover the logical grid

```python
from magical_led import connect

async def inspect(identifier):
    async with connect(identifier, timeout=25) as strip:
        topology = await strip.read_topology(timeout=5)
        print(topology.reported_type)  # STYPE26X20 on the tested device
        print(topology.width, topology.height, topology.pixel_count)  # 20 26 520
```

`read_topology` subscribes to FFF0 notify/indicate characteristics and waits for
a valid decrypted STYPE packet. It sends **no W1 query**. A report observed on
this connection is cached and reused. The timeout includes subscription setup;
silence raises `TimeoutError`. Unsupported model strings raise `ValueError`;
unknown dimensions are not silently inferred or replaced by 20×26. Shared/nested
`notifications` consumers reuse one native subscription; the last consumer
unsubscribes, including after exceptions. A failing user callback is reported
to the asyncio exception handler without starving other consumers.

The app's other recognized models map to grids 20×38, 20×32, 100×1 and 25×20.
They can be parsed, but physical live mapping on them is unverified. An explicit
`Topology(width, height)` can be supplied for offline work/calibrated hardware;
its `reported_type=None` records that it did not come from a BLE report.

## Play a sequence of 2D arrays

```python
import asyncio
from magical_led import connect

async def main(identifier):
    async with connect(identifier, timeout=25) as strip:
        topology = await strip.read_topology()
        frames = []
        # A red, then green, then blue point moves right across the top row.
        for x, rgb in enumerate(((255, 0, 0), (0, 255, 0), (0, 0, 255))):
            frame = [[(0, 0, 0) for _ in range(topology.width)]
                     for _ in range(topology.height)]
            frame[0][x] = rgb
            frames.append(frame)
        result = await strip.play_frames(frames, topology=topology,
                                         brightness=20, fps=0.5, repeat=2)
        print(result.frames_sent, result.pixel_writes, result.effective_fps)

# asyncio.run(main("DEVICE_ID"))
```

API:

```python
await strip.play_frames(
    frames, *, topology=None, mapping=FrameMapping(), fps=1, repeat=1,
    brightness=None, pixel_delay=0.01, command_delay=0.5,
)
```

- `frames`: **1–256** finite frames; generators of frames are allowed. Each
  frame and row must have a length. Rows contain RGB triples `(r,g,b)` or packed
  integer `0xRRGGBB` values; alpha and floating-point channels are not accepted.
  A NumPy integer RGB array or packed-color array can be passed if already
  available in the caller, but NumPy is neither imported nor required/tested.
- `topology=None`: read dimensions from BLE before changing the display. A
  supplied `Topology` bypasses discovery; the caller owns its accuracy.
- All frames are copied, shape-checked and color-validated **before any lighting
  write**. Ragged/wrong-sized arrays, out-of-range values and empty sequences
  fail instead of resizing/cropping. The caller's buffers are not mutated.
  Normalized storage is bounded to 1,000,000 total pixel values across frames
  in addition to the 256-frame limit.
- Initialization sends optional LIGHT, then EFFE 0, COLO black, SMVEW 1 (enter
  unsaved edit mode), waiting `command_delay` after each. It does not send LEDON;
  use `set_power(True)` explicitly when needed.
- The first frame writes **every pixel**, including black, so no old marker or
  last-run cache is assumed. Later frames send only changed pixels, including
  pixels that must become black. Loop boundaries are also compared correctly.
- W3 writes use the controller's discovered write properties and one encrypted
  16-byte block per pixel. `pixel_delay` defaults to **10 ms**, a conservative
  pacing baseline informed by the app's live-edit send delay, not a measured
  hardware limit. Lower delays need separate physical verification.
- `fps` is a requested **ceiling**: each frame's write time counts toward its
  display interval. Overruns slip; playback does not burst to catch up. The last
  frame is held for its interval too. With 520 updates and a 10 ms gap, a full
  refresh needs at least **5.2 seconds plus BLE/encoding/scheduling overhead**.
  Sparse effects are much cheaper. There is no atomic framebuffer latch in the
  observed live protocol: large updates visibly redraw progressively.
- `repeat` is a positive integer, or **`None` for continuous playback** (added
  in 0.4.0). Own and cancel the continuous task explicitly. The per-Strip write lock covers setup and
  playback, preventing other writes through that instance from interleaving.
  Do not await a different write on the same Strip until the playback finishes
  or is cancelled. Other processes/Strip instances are outside that lock.
- Return value `PlaybackResult` contains `frames_sent`, `pixel_writes`,
  `elapsed_seconds` and computed `effective_fps`, plus `overrun_frames` and
  `max_frame_write_seconds` in 0.4.0. Overruns include the initial full draw;
  maximum write duration includes per-pixel pacing but not the final interval
  hold. Counts mean completed host-side
  submissions, **not visible-rendering acknowledgements**. Elapsed time excludes
  discovery/validation/edit setup and includes frame writes and interval holds.
  Continuous playback returns no result until it completes (normally it is
  cancelled instead). Check timing with a bounded run before streaming forever.

### Orientation transforms

```python
from magical_led import FrameMapping

mapping = FrameMapping(flip_x=True)  # view from opposite horizontal direction
# Or FrameMapping(transpose=True, flip_x=True), etc.
await strip.play_frames(frames, mapping=mapping)
```

Transpose input first, then flip native x/y. With transpose enabled the required
input size is 26 columns × 20 rows for this native 20×26 grid. Without transpose
it is 20 columns × 26 rows. The default matches the calibrated top-left view.
`prepare_frames(frames, topology, mapping)` performs the same normalization
offline and returns immutable native row-major RGB buffers.

### Completion, errors and cancellation

This is **live streaming**, not controller-side effect storage. No upload, save
(`SMVEW 2`) or firmware command is sent. The connection must stay open while
streaming. Normal completion leaves the last frame in unsaved edit mode;
cancellation/write failure propagates and releases the write lock, leaving the
last complete or partial image. No hidden retry, restore or clear follows a
failure. After cancellation you can explicitly select a built-in effect, power
off, or call `exit_live()` (SMVEW 0; its visible exit behavior is not yet tested).
A later `play_frames` call rewrites its entire first frame. Do not mix unrelated
scene changes or partial raw pixel writes into a running playback.

## CLI and example data

```powershell
.\led.ps1 --timeout 25 --device DEVICE_ID topology
.\.analysis\cpython\python.exe examples/moving_dot.py --output moving-dot.json
.\led.ps1 --dry-run play moving-dot.json --repeat 2
.\led.ps1 --timeout 25 --device DEVICE_ID play moving-dot.json --fps 0.5 --repeat 2 --brightness 20
```

Standard installations use `magical-led` in place of `led.ps1`. The generator
uses only stdlib, defaults to 20×26/four frames, and refuses to overwrite an
existing file. The CLI accepts UTF-8 JSON of the form `{"frames": [...]}` up
to 4 MiB; the same 256-frame bound applies. `--flip-x`, `--flip-y`, `--transpose`
select transforms. A dry run uses the input's dimensions, not a fabricated
controller report, and prints planned pixel-write counts rather than dumping
hundreds of packets. Live playback requires an exact match to the BLE-derived
grid. A JSON input like the synthetic 2×2 fixture in tests is useful for offline
previews but will correctly fail on a 20×26 device.
