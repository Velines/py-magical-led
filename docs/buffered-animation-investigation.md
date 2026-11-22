# Buffered animation investigation · 2026-11-21

**Latest:** subsequent owner-authorized experiments below verified persistent
animation restoration with SMVEW 2, except startup speed. See
[current playback/storage API](effect-playback-storage.md). Earlier sections
retain the transfer-only results and do not describe the later explicit save.

Status: experimental implementation/test authorized by user on 2026-11-21.
The user explicitly accepted possible replacement of existing custom animation
content for a bounded upload test; no firmware/reset authorization. They
clarified XMAS 03/04 retain paired-string patterns but require whole-string
changes instead of downward live repaint. Related requirement UR-006-AC2.
Live-player code remains at `beb3916`; follow-up diagnostics used existing code
and an analysis-only transport wrapper, not a changed public protocol.

## Why investigate another transport?

- Fast W3 submissions met the host interval but did not produce the user-observed
  shifting at the requested rate.
- At 10 ms gaps, the user saw changes travelling down strings: the per-LED,
  row-major redraw was visible. Four phases took 21.688 s, not the requested 8 s.
- Forcing acknowledged W3 writes with no extra gap took 60.406 s for four phases
  and 1300 pixel writes. ATT completion is still not a display-latch signal.

The software-generated paired-strip frames are tested, but the tested live
methods do not satisfy the intended clean picture shift. Do not equate host
queue speed with controller application or renderer timing.

## App path found in read-only DEX review

`fragment.DiyFragment$2.onItemClick` obtains a locally stored `DiyAnimData`,
constructs the selected animation data and calls
`data.DiyAnimAgreement.sendDiyAnim`. That method obtains the byte payload,
image count and speed, then calls `BleProtocol.sendAnimDataCommand`:

1. W1 encrypted MANY header with frame count, speed and total byte length.
2. Receive/decrypt MANYOK.
3. `DiyAnimAgreement.getSendData` constructs indexed W2 chunks (18 payload bytes
   normally, 96 when the app marks MTU success). These chunks are not W1 AES
   command blocks. Its listener sends the next locally held chunk after REOK.
4. After the final chunk, it calls `BleProtocol.sendDataMancpCommand` (MANCP).
5. Receive/decrypt MANCPOK; the app treats this as successful completion.

`DiyAnimAddActivity.addAnim/updateAnim` concatenates the selected images' data
and stores image metadata/speed in the phone's local `DiyAnimDataDao`. Local
database saves are not proof of peripheral persistence semantics.

This is a plausible way for the controller to own the timing and display whole
animation frames, but exact serialized color/frame ordering, buffer/flash
behavior, frame limits, error recovery and speed-to-seconds mapping still need
verification for TR2103R001-8. Existence of this path does not prove a two-second
interval, an atomic latch, a free slot or preservation of existing custom data.

## Decision required before writing (subsequently authorized)

The discovered protocol has no stored-animation inventory/readback operation,
so we cannot back up the existing controller custom animation first. A MANY
upload may replace that content. No free slot, nonpersistent preview mode or
rollback guarantee has been established. Do not start a transfer merely to see
what happens, and do not send guessed commands to avoid this decision.

Owner options:

- Authorize an experimental custom-animation upload, accepting possible loss
  of existing custom animation content; finish serialization/handshake review,
  bound the test and record exactly what is written before execution.
- Preserve controller content and continue only with live rendering, accepting
  its currently observed progressive/slower transitions or further read-only
  investigation. This does not meet the clean two-second shift yet.

No MANY, W2 animation payload or MANCP was sent in the earlier follow-up tests
before authorization. The subsequent explicitly authorized test is recorded below.

## Serialization and bounded test plan after authorization

Further read-only evidence: `DiyFragment.getSendData` assembles saved frames'
`DiyData.getColorArray()` lists and calls `DataUtils.colorConvertBRGArray`.
Despite its name, that converter writes **green, red, blue**. `LedView.init`
creates child indices with column = index / height, row = index % height;
`getDataColor` collects them in child order. Thus payloads concatenate frames,
then strings left-to-right, then LEDs top-to-bottom, three GRB bytes per LED.

The MANY header contains frame count, raw speed, and big-endian byte length;
it contains **no destination slot ID**. The app maps its UI speed to
`max(1,10-trunc(uiSpeed/10))`, but physical time per raw speed remains unknown.
Do not equate raw speed 10 to two seconds without a physical timing check.

First upload plan: four 20×26 XMAS 03 (red/green) phases, 6240 payload bytes,
raw speed 10, 65 indexed 96-byte-payload W2 chunks (98-byte values). This fits
the previously observed 245-byte write-without-response limit. Subscribe before
MANY, then stop-and-wait on MANYOK, REOK for each chunk, and MANCPOK. Validate
everything before the header; use per-step and total deadlines, no automatic
retry or guessed abort. A failed transfer can leave content partially replaced.
No additional live pixel redraw, flash/OTA or reset commands are part of this test.

The library must require explicit overwrite consent for every buffered upload;
ordinary live effects must not silently become uploads. Test clean frame
switching/autonomous playback first. Power-cycle persistence and available
storage slots remain unverified until separately observed. One completed
transfer is not evidence that multiple named effects coexist on the controller.

## Authorized XMAS 03 test result

Four phases, 6240 GRB payload bytes, 65 chunks, raw speed 10, brightness 20.
Payload SHA-256 `6e1e31f5541846595de4a74d8e92fda3ffec2f42809aa77ab6c672f17d416caa`.
MANY plaintext `084d414e59040a186000000000000000`.
MANYOK decrypted `064d414e594f4b18600000000000000000`; the trailing 0x1860
echoes byte length outside the token-length field. All 65 REOK barriers
completed; MANCPOK decrypted `074d414e43504f4b0000000000000000`.
API elapsed time 2.594 s including optional brightness delay and subscription.

After 12 s without further writes, the connection closed. The user confirmed
**clean whole-string changes, approximately 2 s per step, continuing after
Bluetooth disconnect**. This verifies controller-managed playback of the
paired-string red/green program on the tested TR2103R001-8 / STYPE26X20.

**Actual power-cycle result:** the user corrected an initial answer before
testing and then reported a different effect resumes after a real power cycle.
Only that performed test counts. XMAS 03 does **not auto-resume** on power-up.
This does not distinguish lost animation bytes from a different saved startup
mode; nonvolatile retention/readback/reselect remains unverified. Do not equate
MANCPOK, autonomous looping or disconnect survival with permanent storage.

No further uploads or guessed persistence commands were sent during the user's
power-cycle check. XMAS 04 uses the same buffered transport but white instead
of green; its physical appearance was not yet independently confirmed at that stage.

## Explicit save experiment and temporary-play isolation (0.6)

The user authorized testing the known single-image save command after native
animation upload, accepting possible replacement of custom images as well as
animations. No guessed opcode, firmware operation or reset was authorized/used.

**SAVE-001:** upload XMAS 03 (same four phases / 6240 bytes / 65 chunks, speed
10, brightness 20). MANYOK/REOK/MANCPOK completed; upload time 3.578 s. Wait 1 s,
send SMVEW 2 once, wait 6 s, disconnect. Plaintext
`06534d56455702000000000000000000`, encrypted
`517e2c45b651172de8af469f83918021`. No separate save ACK was observed. After an
actual power cycle the user confirmed **XMAS 03 animation resumes, but at the
wrong speed**, also observed with the original app. This supersedes the earlier
transfer-only persistence result: upload alone was insufficient; explicit save
restores animation/startup selection but does not retain selected speed.

**ISOLATE-001:** temporarily upload XMAS 04 (four phases / 6240 bytes / 65 chunks,
speed 10, brightness 20); upload time 3.875 s, MANCPOK confirmed. Payload SHA-256
`ec40f0121ee60bc6311ada69f4eea801c7db1ad2a93445cb3ec44606da612531`.
No SMVEW 2 was sent. After a 12 s hold, disconnect. User confirmed clean
red/red/white/white whole-string playback. Actual power cycle then restored
**saved XMAS 03 red/green**, not the temporary XMAS 04. This verifies logical
temporary-play/persistent-program separation on this controller; it is not a
physical flash-memory inspection or proof of multiple addressable slots.

The supported profile is matched to BLE STYPE26X20 and directly read firmware
TR2103R001-8. Safe ordinary buffered playback and explicit persistent storage
are now separate APIs. Unknown profiles fail closed for those verified operations.

**WIPE-001/002:** following the user's choice of every LED row rather than three
coarse steps, XMAS 01 renders 104 row snapshots at a requested 2/26 s interval.
Both bounded live runs submitted 104 snapshots / 1550 W3 pixel writes at
brightness 20, with no save command. First run: 17.578 s including initial draw,
4 overruns, maximum write 9.078 s; user requested a repeat rather than accepting
that observation. Repeat: 17.531 s, 12 overruns, maximum write 9.046 s. The user
confirmed **all changing red/green strings advance down together at the same
height**. Initial draw uses a conservative 10 ms gap; timing after it remains
soft, not a simultaneous electrical row operation or hard two-second guarantee.
