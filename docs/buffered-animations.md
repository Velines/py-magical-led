# Buffered effects and device storage · 0.5.0

**0.6 update:** explicit persistent saves are now power-cycle-tested on the known
firmware profile using SMVEW 2; temporary playback preserves the saved program.
Saved speed is not retained. See [current playback/storage API and capacity
limits](effect-playback-storage.md). This earlier transfer-only API reference is
historical; normal playback no longer uses an overwrite flag or fixed effect
transport, and persistent writes use `store-effect --overwrite`.

## What is confirmed?

**XMAS 03** is the paired red/red/green/green pattern played by the controller
from an uploaded four-frame animation. On TR2103R001-8 / STYPE26X20 the user
confirmed whole strings change cleanly, about every two seconds at raw speed
10, and continue after Bluetooth disconnects. There is no live downward repaint.

**XMAS 04** uses the same path for red/red/white/white. Its frame generation and
transfer are unit-tested; its visible white pattern is not yet hardware-confirmed.

There is an important limit to the word **stored**:

| Property | Evidence on tested device |
|---|---|
| Controller accepts a complete custom animation | MANYOK, 65 REOK barriers and MANCPOK confirmed |
| Controller loops it without the Python process/Bluetooth connection | User confirmed for XMAS 03 |
| XMAS 03 automatically resumes after actual power loss | **No**: user power-cycled and saw another effect |
| Uploaded bytes survive power loss and can be reselected | Unknown; no readback/reselect path established |
| Multiple named custom programs coexist in separate slots | Unknown; MANY header has no destination slot |

Therefore this is an **active custom-animation buffer**, not a promised
permanent effect library in the controller. No guessed save, firmware update or
reset is used to work around that distinction. Uploading another program may
replace the current custom animation; we cannot back it up via the discovered
protocol. Names stay in Python, not on the device.

## CLI

```powershell
.\led.ps1 effects
.\led.ps1 --dry-run run-effect "XMAS 03" --width 20 --height 26
.\led.ps1 --timeout 25 --device DEVICE_ID run-effect "XMAS 03" --allow-overwrite --brightness 20
.\led.ps1 --timeout 25 --device DEVICE_ID run-effect "XMAS 04" --allow-overwrite --brightness 20
```

The two live commands above are alternatives: each upload may replace the
previous custom program. `--allow-overwrite` is required **on every actual
upload**. It acknowledges possible replacement; it is not a request for a
permanent flash save. An offline preview never writes anything and requires
explicit geometry. Live geometry is obtained from BLE.

The command returns after MANCPOK and disconnects; the controller owns the
continuous loop. Do **not** use `--repeat`, `--forever` or `--pixel-delay` for
XMAS 03/04. No finite controller-loop-count operation has been identified.
Ctrl+C after the command has returned cannot stop an autonomous animation;
explicitly select another effect or use the existing `off` command instead.
The native path does not hold a host connection open or keep repainting pixels.

Use `upload-effect` to send **any** named library effect through this same
native path, including the patterns of legacy XMAS 01/02:

```powershell
.\led.ps1 --dry-run upload-effect "XMAS 01" --width 20 --height 26
.\led.ps1 --device DEVICE_ID upload-effect "XMAS 01" --allow-overwrite --brightness 20
```

`run-effect XMAS 01/02` retains live streaming for compatibility; it does not
silently start overwriting controller content. The new 03/04 names explicitly
select buffered delivery. `--wire-speed 1..10` overrides the app's raw native
speed. Only speed 10 has a human-confirmed approximate two-second step on this
controller; no general milliseconds/seconds formula is claimed.

## Python

```python
from magical_led import connect

async def native_christmas(identifier):
    async with connect(identifier, timeout=25) as strip:
        result = await strip.play_effect(
            "XMAS 03", allow_overwrite=True, brightness=20,
        )
        # Returns after upload acceptance, not after the controller loop finishes.
        print(result.frame_count, result.bytes_sent, result.chunks_sent)
    # Bluetooth is disconnected; observed XMAS 03 continues until mode/power changes.
```

- `play_effect("XMAS 03/04", allow_overwrite=True, ...)` returns an
  `AnimationUploadResult`, whereas live XMAS 01/02 return a `PlaybackResult`
  only when their bounded run finishes (or keep running until cancellation).
- `upload_effect(name, allow_overwrite=True, topology=None, mapping=FrameMapping(),
  direction="right", wire_speed=10, brightness=None)` buffers any collection
  program. It always requires consent, regardless of the name's normal transport.
- `upload_animation(frames, allow_overwrite=True, topology=None,
  mapping=FrameMapping(), wire_speed=10, brightness=None, chunk_capacity=None,
  ack_timeout=5, total_timeout=60)` uploads arbitrary finite 2D RGB frames using
  the same normalization as `play_frames`. A provided topology bypasses discovery;
  the caller owns its accuracy. Brightness, if supplied, is applied first with a
  500 ms settle before the header.
- `encode_animation(frames, topology, mapping=..., wire_speed=10,
  chunk_capacity=96)` builds an immutable `AnimationTransfer` offline. It returns
  validated payload/header/chunks but sends nothing and needs no consent flag.

`AnimationUploadResult` reports frame/byte/chunk counts, raw speed, total
transfer/subscription/optional-brightness time, raw type and decrypted completion
reply hex. `power_cycle_persistence="unverified"` means the upload operation
cannot verify nonvolatile retention; it is not a claim that the separate human
power-cycle test passed. The CLI reports `uploaded_to_controller=true` and
`host_streaming=false`, not `saved_permanently=true`.

## Format and handshake

Source trace is in [the investigation](buffered-animation-investigation.md).
Unlike live W3 frames, the native payload is **column-major**:

```text
for each animation frame:
    for x in columns left-to-right:
        for y in LED positions top-to-bottom:
            append green, red, blue
```

1. Subscribe before changing anything. Validate complete arrays, frame count,
   byte length, chunk count and actual GATT write limits before MANY.
2. W1 plaintext `[8] MANY frameCount wireSpeed byteLengthHi byteLengthLo zeros`,
   encrypted as one block. Wait for decrypted MANYOK.
3. W2 indexed chunk: `[payloadLength+1][zeroBasedIndex][payload][zero padding]`.
   These are **not AES command blocks**. Wait for REOK after every chunk.
4. W1 encrypted `[5] MANCP zeros`. Wait for MANCPOK. This acknowledged
   completion triggered autonomous playback in the XMAS 03 test.

Auto capacity is 96 payload bytes if the W2 no-response write limit permits
98-byte values; otherwise it is 18. Fixed app formats only; no arbitrary-MTU
chunk size is guessed. Refuse >255 frames, >65535 bytes or >256 indexed chunks.
At 20×26 each frame is 1560 bytes; four phases are 6240 bytes / 65 large chunks.
The index bound allows at most 15 full frames at this size/capacity, even though
the raw frame-count field is larger. Without large chunks the same four-frame
animation would wrap its sequence index, so the uploader refuses it.

## Ownership and failures

One transfer owns the per-Strip write lock from subscription/setup through
completion. ACK waiters are armed **before** their writes. Each write+ACK has
a deadline, plus a total deadline for setup/lock wait/transfer. Discovery and
encoding occur before that total transfer deadline. Device ERROR, unexpected
transfer replies, timeout, cancellation or transport failure aborts locally.
There is no automatic retry, MANCP-after-failure, unknown abort or rollback.
`AnimationTransferError` indicates custom content may be partial; cancellation
releases locks/subscriptions and propagates. No cleanup tries to restore content
that could not be read back. Application ACKs have no established transaction
ID/deduplication contract; use one controlling central and avoid parallel
transfers/processes on the same peripheral.

The bound test was explicitly owner-authorized and overwrote/replaced whatever
active custom content the controller chose. It used no OTA service, firmware
write, factory reset, inventory query or guessed persistence command. General
storage capacity, slot selection, faster native speeds, other profiles and
failure recovery on physical hardware remain unverified.
