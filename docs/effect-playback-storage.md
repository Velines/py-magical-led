# Effects, playback and persistent storage · 0.6.0

## Visual definitions do not select storage

| Name | Colors | Transition |
|---|---|---|
| XMAS 01 | red/red/green/green repeating across strings | Synchronized top-to-bottom wipe, every LED row |
| XMAS 02 | red/red/white/white repeating across strings | Same synchronized row wipe |
| XMAS 03 | red/red/green/green | Whole-picture cut to the next shifted phase |
| XMAS 04 | red/red/white/white | Same whole-picture cut |

Each complete phase moves one string right with cyclic wrapping. `direction="left"`
reverses that direction. There is no storage/overwrite or transport field on an
effect definition: it contains colors, band width, target step duration and
`transition` only. `phase_frames(topology)` gives the four complete pictures;
`frames(topology)` renders the actual visual transition, identically for play,
buffering or storage. No backend silently substitutes the phase pictures for
the requested wipe.

For 20 strings × 26 LEDs, XMAS 01/02 render **104 snapshots per cycle**. Between
successive snapshots only one LED row changes, across all ten affected strings
(five in each color direction), before the next row advances. Opposite color
changes therefore share the same vertical frontier; one string is not finished
before starting the other. The last intermediate joins the initial complete
picture at the loop boundary. A bounded run may stop at that final intermediate;
continuous playback completes the last row on the next loop's first snapshot.

The requested interval per row snapshot is 2/26 seconds, giving four 2-second
full-string transitions per cycle on a sufficiently fast link. Live W3 packets
are still sequential, not electrically simultaneous; tests enforce row-level
ordering and the user confirmed visually synchronized XMAS 01. Timing can slip.
The initial complete picture uses 10 ms gaps by default for a row-wipe effect
and took about 9 s in the physical test; that is initialization, not the desired
wipe speed. Subsequent row batches use no extra per-pixel gap and are paced as
snapshots. `initial_pixel_delay` can override initialization explicitly.

## Playback is not persistent storage

```powershell
.\led.ps1 effects
.\led.ps1 --device DEVICE_ID run-effect "XMAS 01" --brightness 20
.\led.ps1 --device DEVICE_ID run-effect "XMAS 03" --brightness 20
.\led.ps1 --device DEVICE_ID run-effect "XMAS 03" --delivery live --repeat 1
```

`run-effect` never sends the persistent-save command. `--delivery auto` prefers
live streaming for a row wipe and a temporary buffered program for a whole-frame
cut. You can explicitly choose `live` or `buffered`; that changes delivery,
not the rendered effect. `buffered` is permitted automatically only on a profile
whose temporary/persistent isolation was physically verified. No effect name
is a reason to overwrite saved content.

Live playback repeats until Ctrl+C by default; `--repeat N` requests bounded
cycles. Buffered playback returns after upload and the controller loops until
another display operation or power change; no finite native repeat count is
known, so repeat/forever/pixel-delay options are rejected there. Explicit live
delivery of a cut cannot provide a hardware frame latch and may show redraw.
Explicit buffered delivery of the full row wipe fails the capacity check below.

On TR2103R001-8 / STYPE26X20, temporary native XMAS 04 played cleanly, then a
real power cycle restored **saved XMAS 03**. That is the evidence allowing
buffered playback without a persistent-overwrite flag on this verified profile.
Unknown profiles fail closed for this automatic temporary buffering. The
advanced `upload-effect --replace-buffer` / `upload_effect(allow_overwrite=True)`
remain explicit experimental transfer operations; they never add a save.

## Persistent store/overwrite is a separate operation

```powershell
.\led.ps1 --device DEVICE_ID storage-capabilities
.\led.ps1 --dry-run store-effect "XMAS 03" --width 20 --height 26
.\led.ps1 --device DEVICE_ID store-effect "XMAS 03" --overwrite --brightness 20
```

```python
from magical_led import connect

async def use_effects(identifier):
    async with connect(identifier, timeout=25) as strip:
        caps = await strip.read_storage_capabilities()
        print(caps.persistent_save_verified, caps.startup_speed_retained)

        # Temporary play only; no persistent save, no overwrite permission needed.
        await strip.play_effect("XMAS 03")

        # Separate, deliberate replacement of the controller's custom program.
        stored = await strip.store_effect("XMAS 03", overwrite=True, brightness=20)
        print(stored.save_command_hex, stored.startup_speed_retained)
```

`store_effect(name, overwrite=False, ...)` and
`store_animation(frames, overwrite=False, ...)` require **overwrite=True**:
the discovered protocol has no saved-slot inventory, free-slot test or backup,
so creation without permission to replace cannot be safely distinguished from
overwriting an existing custom program. Only the single unaddressed custom
location is supported; names are local, not four installed device slots.

On the verified profile a store operation:

1. Validates the **same complete rendered sequence**, byte/index bounds and
   controller write limits before changing content.
2. Transfers MANY / indexed W2 chunks with application ACK barriers / MANCP.
3. Only after MANCPOK, waits 1 s, sends **SMVEW 2** (`06534d56455702000000000000000000`)
   and waits 6 s for settling. ATT response is preferred for the save if supported.
4. Holds one write lock throughout upload and save, so another operation through
   this Strip cannot replace the temporary buffer between them.

No save follows a failed upload. Timeout/cancellation can occur after content
has changed, including during save settling; there is no automatic retry or
rollback. `PersistentStoreResult` contains the acknowledged upload, save command
hex, total elapsed time and the profile's startup-speed limitation. It explicitly
reports `power_cycle_checked_by_operation=False`: no readback or fresh power cycle
is fabricated by a successful host write.

The actual save experiment restored **XMAS 03 animation after a real power cycle**.
The user reported the wrong speed afterward, also seen with the original app.
Thus animation/startup selection survives, but **saved speed is not retained**
on the tested firmware. The library does not claim that two-second timing survives
power loss or send guessed firmware/configuration commands to fix it.

Verified support is matched to both BLE model STYPE26X20 and directly read
firmware `TR2103R001-8`, not to an arbitrary device name. Capability flags mean
library support tested on that profile, not automatic discovery of all hardware
features. Recognized but unverified profiles return false capability flags and
persistent store / safe buffered play raise `StorageUnsupportedError` before
content writes. An unrecognized grid report still raises the topology parser's
unsupported-grid error; it never becomes a guessed capability/dimension.

## Full row wipes cannot fit the verified device format

The user chose every LED row rather than a coarse three-step approximation.
At this size, a stored XMAS 01/02 cycle requires **104 × 20 × 26 × 3 = 162,240 bytes**.
The verified header supports at most 65,535 bytes, and the 96-byte chunk/index
format further limits a transfer to 24,576 bytes (15 full frames at 20×26).
Therefore storing the selected full-resolution wipe or buffering it is rejected
**before MANY, pixels, brightness or save writes**. It is not replaced by a cut
or coarser wipe. XMAS 03/04 each need only four frames / 6,240 bytes and fit.

This capacity error is independent of the effect's name and applies to any
oversized custom sequence. A different explicit visual definition could fit,
but it would be a different effect, not a hidden storage-dependent rendering.

### Migration from 0.5

- Effect `.transport` is replaced by visual `.transition`.
- Playback selects `delivery='auto'|'live'|'buffered'`, not storage flags.
- Remove `allow_overwrite` / `--allow-overwrite` from normal `play_effect` /
  `run-effect` calls. Use `store_effect(overwrite=True)` / `store-effect --overwrite`
  to make a persistent write.
- The advanced temporary upload command accepts `--replace-buffer`; its old
  `--allow-overwrite` spelling is retained only as an alias, never a save request.
- The generic raw `play_frames` defaults remain bounded and unchanged, except
  for its optional separate `initial_pixel_delay` control.

## Arbitrary animation arrays (not just named effects)

The layout is exactly `frames[animation_step][y][x]`, where each pixel is an
RGB triple `(r,g,b)` with channels 0..255, or packed `0xRRGGBB`. For this device
each step has 26 rows × 20 columns. Read those dimensions instead of hard-coding:

```python
import asyncio
from magical_led import connect

async def main(identifier):
    async with connect(identifier, timeout=25) as strip:
        topology = await strip.read_topology()
        frames = [
            [[(0, 0, 0) for _ in range(topology.width)]
             for _ in range(topology.height)]
            for _ in range(2)
        ]
        frames[0][0][0] = (255, 0, 0)
        frames[1][0][1] = (0, 255, 0)
        # Host-streamed playback, two seconds per input animation step.
        await strip.play_frames(frames, topology=topology, fps=0.5,
                                 repeat=None, brightness=20)

# asyncio.run(main("DEVICE_ID"))
```

Choose the operation separately; the same arrays are accepted by all three:

| Operation | Python method | Lifetime / constraints |
|---|---|---|
| Host live streaming | `await strip.play_frames(frames, fps=0.5, repeat=None)` | Requires connection; generic 256-frame / pixel-memory bounds; FPS is a ceiling |
| Temporary controller playback | `await strip.play_animation(frames, wire_speed=10)` | Returns after upload; verified profile; native byte/chunk/frame bounds; no persistent save |
| Persistent replacement | `await strip.store_animation(frames, overwrite=True)` | Explicit overwrite; verified save profile; same native capacity bounds; saved speed not retained |

`play_animation` does not need an overwrite flag because it uses only the
verified temporary-buffer path. `store_animation` always does. Host `fps` and
`repeat` are not native timing/loop-count arguments; raw native speed 10 was
observed at about two seconds only on this profile. Standard Python lists and
tuples work; compatible integer arrays can be supplied by callers, with no
NumPy dependency added. All arrays are shape/color-validated and copied before
content writes; no backend silently changes the visual frames to make them fit.
