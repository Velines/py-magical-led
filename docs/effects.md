# Pre-made library effects

**Current 0.6 API:** see [effects, playback and persistent storage](effect-playback-storage.md).
XMAS 01/02 now have explicit full-row synchronized wipes; XMAS 03/04 have cuts.
Visual definitions are independent of delivery/storage. Use `run-effect` to play
and `store-effect --overwrite` to persist. The following **historical 0.5
reference** is retained for the earlier transport investigation; its
`.transport` field and playback overwrite flags are superseded by 0.6.

Names and generators are local library definitions, not a directory fetched
from the controller. **XMAS 01/02 stream live W3 pixels; XMAS 03/04 upload a
buffered custom animation, requiring explicit overwrite consent.** The buffered
path is recommended for whole-string switching on the tested controller. It
does not imply permanent storage or multiple saved slots. Built-in controller
effects remain under `effect ID`; the app catalogue remains under `presets`.

## The collection

| Name | Repeating initial string colors | Step |
|---|---|---|
| **XMAS 01** | red, red, green, green | Move right by one string every 2 s (target) |
| **XMAS 02** | red, red, white, white | Move right by one string every 2 s (target) |
| **XMAS 03** | red, red, green, green | Buffered whole-frame changes; about 2 s confirmed at native speed 10 |
| **XMAS 04** | red, red, white, white | Same buffered path; white variant not yet physically confirmed |

XMAS 03/04 retain the paired-string patterns; they do **not** alternate the
entire display between two solid colors. See [native transfer, consent and
power-cycle results](buffered-animations.md) before uploading.

Every LED down a given string has the same color. Red is RGB `(255,0,0)`, green
`(0,255,0)` and white `(255,255,255)`. Brightness is separately controlled by
the optional global brightness argument, not baked into the RGB values.

“Forward” means **rightward**, using the agreed front view. The complete finite
picture wraps from the right edge to the left. There is no fade/interpolation:
each phase is a one-string translation. On the 20-string device there are four
unique phases (R = red; B = the second color, green or white):

```text
phase 0: R R B B R R B B R R B B R R B B R R B B
phase 1: B R R B B R R B B R R B B R R B B R R B
phase 2: B B R R B B R R B B R R B B R R B B R R
phase 3: R B B R R B B R R B B R R B B R R B B R
repeat:  phase 0
```

One string changes in each color direction **per four-string repeat**. Across
20 strings, each shift changes ten strings total (five each way), or **260 LED
positions**. This follows from moving the whole repeated R/R/B/B image one
column; it is not just two changed strings across the entire installation.

For widths not divisible by four, the rightmost band may be partial. Rotating
the actual finite image preserves the initial colors/population and may require
a longer cycle. A one-/two-string grid initially contains only red, so rotation
cannot create the missing second color. Generated frames respect the existing
256-frame / 1,000,000-normalized-pixel bounds.

## Python

```python
from magical_led import connect, list_effects, get_effect

for effect in list_effects():
    print(effect.name, effect.colors, effect.step_seconds)

async def christmas(identifier):
    async with connect(identifier, timeout=25) as strip:
        # Dimensions come from BLE; the default mapping matches the calibrated
        # top-left view. Does not implicitly power on a powered-off controller.
        result = await strip.play_effect("XMAS 01", repeat=2, brightness=20)
        print(result.overrun_frames, result.max_frame_write_seconds)

        # Collection effects run continuously by default:
        # await strip.play_effect("XMAS 02", brightness=20)
        # Own/cancel that task to stop; no save or restore is sent on cancellation.
```

`get_effect(name)` tolerates case and extra whitespace; unknown names fail
instead of selecting a controller preset. `list_effects()` returns an immutable
tuple of frozen `StripedEffect` definitions. Constants `XMAS_01` through `XMAS_04`
are exported too. `get_effect("XMAS 01").frames(topology)` renders immutable
2D RGB frames without touching BLE; use them with `play_frames` if desired.
`StripedEffect` is reusable for other immutable color palettes, band widths
and step intervals.

```python
await strip.play_effect(
    "XMAS 02", topology=None, mapping=FrameMapping(), direction="right",
    repeat=None, brightness=None, pixel_delay=0, command_delay=0.5,
    allow_overwrite=False, wire_speed=None,
)
```

`direction="left"` reverses the translation. A supplied `FrameMapping` applies
after effect generation, so flips/transpose can change its physical direction.
Input dimensions are adjusted for transpose. Discovery, validation, exclusive
write ownership, cancellation and unsaved partial-state behavior are inherited
from [live frame playback](live-frames.md). `repeat` counts complete cycles;
on this grid one ideal cycle takes 8 s excluding initial edit-mode setup.
`repeat=None` loops without repeatedly clearing/re-entering edit mode. The
default since 0.4.1 is continuous **live** playback for XMAS 01/02. Supply
`repeat=1` (or any positive count) for a bounded live run. Generic `play_frames`
still defaults to one run. Buffered 03/04 require `allow_overwrite=True`, return
after MANCPOK and leave the controller running autonomously; host repeat counts
and per-pixel pacing do not apply. `upload_effect` can also buffer the patterns
of 01/02 explicitly without changing their normal live behavior.

## Live XMAS 01/02 timing limitations

The requested interval is **2 seconds per phase** (`fps=0.5`), not a 2-second
sleep added after sending the frame. Pixel submission time counts toward the
interval. When it exceeds the interval, playback slips without catch-up bursts
and counts the overrun. W3 is a progressive pixel interface, not an atomic
whole-string/frame update, so intermediate redraws can be visible.

The generic `play_frames` default remains a conservative 10 ms extra pixel gap.
That alone needs **2.6 s for a 260-pixel transition**, before transport/encoding
overhead, making strict two-second steps impossible with that setting.
`play_effect` therefore defaults to **zero additional pixel delay**: each
write is still awaited and followed by an event-loop yield. This makes the
target feasible on a fast enough link but does **not** prove the controller
received every pixel or that timing holds on your adapter. Faster pacing than
the earlier calibrated 10 ms setting needs physical confirmation. A bounded
test is recommended first. The initial live attempt could not find the
controller advertising. A subsequent XMAS 01 run submitted 8 frames / 2340
pixel writes in 16.047 s excluding setup, with zero host-side interval overruns
and a maximum frame-write duration of 1.719 s. The user saw the paired pattern
but reported no shifting at the requested two-second interval. This is a
physical failure for the requested animation despite successful host timing;
host submission times are not rendering ACKs. A diagnostic run with 10 ms gaps
submitted four phases in 21.688 s, with all four exceeding the requested
interval; the user confirmed color changes progressing down the strings. This
confirms progressive repainting, not the intended clean whole-picture step.
A further diagnostic using acknowledged GATT writes (same 16-byte W3 commands,
no extra gap) took 60.406 s for four phases / 1300 writes, with four host timing
overruns and a maximum frame-write duration of 24.265 s. It did not solve timing.
XMAS 02 was subsequently submitted with 10 ms gaps for one cycle at brightness
20: four phases / 1300 writes in 21.641 s, four overruns, maximum frame-write
duration 8.641 s. Its visible colors/transition have not yet been confirmed by
the user; host submission alone does not count as visual acceptance.

**Open finding:** the paired-frame generator is correct in software tests, but
the requested physical transition is not satisfied by the tested live-streaming
methods. After explicit owner authorization, buffered XMAS 03 was uploaded
successfully and the user confirmed clean whole-string changes, about every
2 s, after Bluetooth disconnect. The actual power-cycle test resumed another
effect. See [investigation and overwrite risk](buffered-animation-investigation.md)
and [buffered API](buffered-animations.md).

Set `pixel_delay=0.01` for the older conservative gap if necessary, accepting
slower transitions. For finite runs, inspect `PlaybackResult.overrun_frames`
(including initial full draw) and `max_frame_write_seconds`; these are host-side
measurements, not visible-rendering acknowledgements. Continuous playback is
cancelled rather than returning final statistics, so benchmark a finite run
first. White lights more channels than red/green; begin at low global brightness.

## CLI

```powershell
.\led.ps1 effects
.\led.ps1 effects --json
.\led.ps1 --dry-run run-effect "XMAS 01" --width 20 --height 26 --repeat 2
.\led.ps1 --timeout 25 --device DEVICE_ID run-effect "XMAS 01" --repeat 2 --brightness 20
.\led.ps1 --timeout 25 --device DEVICE_ID run-effect "XMAS 02" --brightness 20
.\led.ps1 --dry-run run-effect "XMAS 03" --width 20 --height 26
.\led.ps1 --timeout 25 --device DEVICE_ID run-effect "XMAS 03" --allow-overwrite --brightness 20
```

Standard installations use `magical-led` instead of `led.ps1`. Global options
precede the command. For live 01/02, with neither flag the effect runs continuously.
`--repeat N` requests a bounded number of cycles; `--forever` is retained as an
explicit alias for the default and is mutually exclusive with `--repeat`. Ctrl+C
stops streaming and disconnects; the last/partial unsaved frame may remain.
`--direction left`, `--pixel-delay 0.01`, `--flip-x`, `--flip-y`, `--transpose`
are available. Live geometry is read from BLE; `--width` and `--height` are
required **only for offline preview** and rejected for a live run. No JSON file
or project-specific effect export is necessary to run the collection.
