# Magical LED 1.2.0: BLE application protocol

This specification describes what the Android **central** constructs or accepts. A model's supported commands, LED count, visible effects and timing limits are peripheral properties. No peripheral, radio capture or Android runtime was used. Hex examples are characteristic **values**, without ATT opcode or handle.

## Evidence and how to reproduce

Analyzed 2026-11-20, local XAPK `Magical+LED_1.2.0_APKPure.xapk`, SHA-256 `979130d0c68cf9ca71fdd0baa235e3c858960a2afd12e1ee85fd19d4717b5791`. Its `manifest.json` identifies `com.pinkysinyeeho.magicalled`, version 1.2.0, code 120. Open as ZIP; open the package-named base APK (SHA-256 `dde9117e6329245b0bde3d0c0e7f5d71b87e46edeba2ec0a063b80ce850c269a`) as another ZIP. The other APK is `config.mdpi.apk`. Index **both** `classes.dex` and `classes2.dex`: some UI callers are in the second. Inspect the named DEX methods below and the ELF with `readelf -rW` and `objdump -d -M intel`; no APK code needs to execute. The Git repository distributes neither APK code nor firmware.

## Finding and connecting

`ble.BleConfig.matchProduct` walks length-prefixed advertising data structures. Length counts AD type and data, excludes the length byte. Match AD type `ff` whose payload starts `54 52 00 56`. In Bleak's `manufacturer_data` mapping that is company ID **0x5254** (little endian) and value prefix **00 56**. Do not require the service UUID in advertising or infer compatibility from the display name. For a sufficiently long matching record `getDeviceType` reads the byte at index 5 counting the AD type as index 0. `isType2025` in this build always returns false; the name alone doesn't establish a capability.

`ble.BleManager.<clinit>`, `init`, `write`, `writeBy2`, `writeBy3`, `enableBLEDeviceNotification` identify the following. Discover handles at connection time; 2902 is a **descriptor**, not the notification data characteristic.

| Purpose | UUID |
|---|---|
| Control service | `0000fff0-0000-1000-8000-00805f9b34fb` |
| W1 command | `d44bc439-abfd-45a2-b575-925416129600` |
| R notifications (SDK `Ble$Options.uuid_notify` default; see discovery below) | `d44bc439-abfd-45a2-b575-925416129601` |
| Direct firmware version read (ASCII, not command AES) | `d44bc439-abfd-45a2-b575-925416129602` |
| W2 content transfer | `d44bc439-abfd-45a2-b575-92541612960a` |
| W3 live edit / rhythm | `d44bc439-abfd-45a2-b575-92541612960b` |
| CCCD for subscriptions | `00002902-0000-1000-8000-00805f9b34fb` |

Select the intended peripheral, connect, discover FFF0, subscribe to R before requests needing replies, then write the characteristic value as one operation. For a write-only control, completion of an ATT operation is not confirmation of the displayed state. `writeAll` is app-side iteration over connections, not a radio broadcast. There is a separate firmware-update service AE00, AE01 write, AE02 notify (Bluetooth base UUID suffix); it is not part of lighting control.

**Discovery takes precedence over UUID labels.** In `cn.com.heaton.blelibrary.ble.BleRequestImpl.displayGattServices` the SDK collects characteristics with property `0x10` (notify) or `0x20` (indicate). `setCharacteristicNotificationInternal` sets the corresponding CCCD. `BleManager.init` overrides the SDK's default service FEE9 with FFF0 and read UUID with `…9602`. `BleManager$3$1.onReadSuccess` converts a direct read of at least 13 bytes to ASCII. This differs from a W1 `VER` query. `wirteCharacteristicByUuid` (SDK spelling) sets the bytes and calls Android `writeCharacteristic` without forcing a write type there; the Python client chooses from the discovered properties.

**App timing:** scan period 12 s, connection timeout 10 s (`BleManager.init`). On first successful subscription the app schedules a request for MTU 512 after 200 ms; a request is not a negotiated result. `MainActivity$BleListenerImpl.lambda$onReady$0` waits 500 ms, sends `TIME`, waits 100 ms, sends `STSC`, waits 100 ms, sends `STIN`. These are app synchronization operations, not evidence that a strip needs clock or timer writes to accept a color.

## Command block and transform

Except where noted, W1 plaintext is `[N][ASCII token][binary arguments][zero fill]`, exactly **16 bytes**. `N` is the number of meaningful bytes after itself, not the block length. Arguments are single octets unless stated otherwise, not printable numbers. No IV, sequence, checksum, alignment block or PKCS padding is added. Encrypt **one** block with AES-128 (ECB single-block operation). Decrypt a 16-byte notification before interpreting its token. `Agreement.getEncryptData/getDecodeData` invoke JNI with the same byte array as input and output.

The protocol's fixed interoperability constant, in memory order, is `34 52 2a 5b 7a 6e 49 2c 08 09 0a 9d 8d 2a 23 f8`. Evidence: `MainApplication.onCreate` calls `keyExpansionDefault`; x86-64 `libAES.so` SHA-256 `07a21bbd8bdb5da0f05d5c287523c8be1cd3347def67da8e441acbb9c995819d`, routine VA 0x1060 loads 16 bytes via GOT 0x3fc8, relocated to VA 0x4020 (file 0x3020). JNI `cipher` transposes the input into row-major internal state, performs initial AddRoundKey, nine full rounds and one final round without MixColumns, then serializes in external byte order. No client-side transpose is required.

| Action | Plaintext prefix (right-pad with zeros) | Calculated characteristic value, hex |
|---|---|---|
| Power on | `05 4c 45 44 4f 4e` | `ebd372ed98857317f2f54cd2130fdc9c` |
| Power off | `06 4c 45 44 4f 46 46` | `cbb1fdbfc560d5e453c2cbd928b53fab` |
| RGB #123456 | `07 43 4f 4c 4f 34 12 56` | `1153d5d091266d514a11b97aa7887092` |
| Brightness 50 | `06 4c 49 47 48 54 32` | `12be7e044087149279944078890f457a` |

Vectors calculated independently using .NET `Aes.EncryptEcb(..., PaddingMode.None)`. They are not captures.

## W1 command catalogue

Source symbols below are in `.data.Agreement` unless prefixed `BP` (`.ble.BleProtocol`). The length is decimal. `x` means the low eight bits of the app argument. A syntactically valid value need not have an effect on every model.

| N | Token + arguments, in wire order | Meaning / source |
|---:|---|---|
| 5 / 6 | `LEDON` / `LEDOFF` | Main power, `getLightSwitch(boolean)` |
| 7 / 8 | `LIGHTON` / `LIGHTOFF` | Flash-light function, `getFlashLight(boolean)`; distinct from main power |
| 7 | `COLO green red blue` | Solid RGB. `getLedColor` calls `Color.green`, `red`, `blue`, in that order. Alpha omitted. |
| 6 | `LIGHT level` | Brightness; `BP.sendLight(0)` substitutes **1**. Use `LEDOFF` for off. |
| 6 | `SPEED speed` | `getSpeed`, seek-bar value passed through |
| 5 | `EFFE id` | Light effect selector, `getLedEffect`; not the `MODE` namespace |
| 5 | `MODE id` | Display/content mode, `getContentCommand`; e.g. `ImageSelectActivity$5.onFinishSend` selects 1 |
| 5 | `IMAG id` / `ANIM id` | Stored image / animation selectors, `getImageCommand`, `getAnimCommand` |
| 5 | `PLAY x` | Multi-animation playback, `getPlayMoreAmin` |
| 5 | `BACK x` | Text background selector, `getTextBg` |
| 6 | `INVER x` | Set inversion; `getInverCommand` |
| **6** | `STIN 00 00` | Inversion query, `getReadInverCommand`. Preserve the literal length 6 despite four letters. |
| 5 | `EVERT` | `getEvert`, reverse action; precise visual behavior unverified |
| 4 | `MIC x` | Microphone control, `BP.sendMicCommand` |
| 5 | `STOPR` | Stop rhythm, `getStopRhythmCommand` |
| 6 | `CALL status time` | Call indication, `getCallPhone`; time unit not established |
| 8 | `TIME weekday hour minute second` | Device local clock, weekday **Mon=1 … Sun=7** (`DateUtils.getWeekOfDate`), 24-hour fields |
| 12 | `SCHD on onMask onHour onMin off offMask offHour offMin` | Schedule; enable flags 0/1; bit i denotes selected day at app week-list index i, bits 0–6. See `BP.sendTimerLight/convertWeekByte`, `ByteUtils.getByteByArray`. |
| 4 | `STSC` | Read schedule, `readTimerLight` |
| 3 | `VER` | Read version, `getVersion` |
| 6 | `SMVEW action` | DIY edit lifecycle: 1 enter, 0 exit, 2 exit and save (`getEnterDiyCommand`, `getExitDiyCommand`, `getExitDiyAndSaveCommand`) |
| 7 | `DATS kind lengthHi lengthLo` | Start content upload; length in bytes, unsigned big-endian. `BP.sendDataLenth` (app spelling). Text and image use kind 0, DIY uses 1. |
| 8 | `MANY count speed lengthHi lengthLo` | DIY animation upload, `BP.sendAnimDataCommand`; `DiyAnimAgreement.sendDiyAnim` passes image count and transformed speed `10 - trunc(uiSpeed/10)` with zero mapped to 1. |
| 5 | `DATCP` / `MANCP` / `PLACP` | End respective transfers. Both `BP.sendDataDatcpCommand` and `sendDataFinishCommand` emit `DATCP`. |
| 8 / 9 | `LEDFIRST` / `LEDSECOND` | `getWhichCommand(1/2)` creates padded blocks, other arguments return null. No normal send path established. |
| 5 | `STYPE` | `getTypeCommand` returns **six bytes total**, not a 16-byte block. Builder evidence only; do not pass its six bytes to the JNI block transform. |

**Lighting effect IDs:** `LightActivity.createMainDatas` indexes five resources (`0x7f0f0022`, `0081`, `004b`, `0025`, `0032` in the same string table). Its selection listener sends the zero-based position **plus one**: 1 Flashing, 2 Hot Wheels, 3 Meteor, 4 Chase, 5 Explosion (default English resources). These are app labels, not observed physical effects. `MODE 1` is not `EFFE 1`.

**Image/animation catalogue:** the app hard-codes 25 default images and 25
default animations, selected using IMAG/ANIM IDs 1–25. This is separate from
the five EFFE entries and is not read from the controller. Custom image lists
come from the app's local database. See [stored-content investigation](stored-content.md)
for the exact source paths and why this does not establish a device directory
or prove which presets exist on the connected firmware.

## R: status, replies and transfer state

For the complete **physically observed readback boundary**, see
[controller state readback](current-state-readback.md). A 2026-11-22 read-only
inspection obtained VER octets 5/1 and disabled on/off schedules through STSC;
STIN did not reply. There is no discovered current RGB/brightness/speed/effect
getter. The app reads its brightness/speed/mode UI values from phone preferences,
not from the controller. GATT control channels reject direct reads (0x02).

The app's receive handlers generally compare bytes starting at offset 1 rather than requiring exact full-block equality. `Agreement.getLight(byte[])` recognizes `LEDON`/`LEDOF` prefixes, returning `LEDON`/`LEDOFF`. `STIN` value at offset 5 is interpreted as 0 or 1. `VER` exposes SPI version at offset 4 and OTA version at offset 5. Treat these as raw bytes; no semantic-version encoding established. `TimerDataManager.setTimerLight` accepts `SCHD` and `STSC` plus the eight schedule fields above, ignoring `SCHDOK` as schedule data. `Agreement.parseType` recognizes strings at offset 1: `STYPE38X20`→2038, `STYPE32X20`→2032, `STYPE26X20`→2026, `STYPE100X1`→1001, `STYPE20X25`→2025; otherwise −1. These are app model IDs, not tested dimensions of the user's strip.

| Flow | Control / reply | Data on W2 | Finish / reply |
|---|---|---|---|
| Text / DIY | `DATS` → `DATSOK` | First indexed chunk; `REOK` advances app's per-device cursor | `DATCP` → `DATCPOK` |
| DIY animation | `MANY` → `MANYOK` | Indexed chunks, advanced by `REOK` | `MANCP` → `MANCPOK` |
| Playlist | `PLAY` → `PLAYOK` | Indexed chunks, advanced by `REOK` | `PLACP` → `PLACPOK` |
| ImageAgreement | `DATS` → `DATSOK` | Encrypted 16-byte image frames, 60 ms sleep per frame, no per-frame `REOK` gate in `sendData` | `DATCP` → `DATCPOK` |

**Buffered DIY animation physical update (0.5.0):** owner-authorized upload on
TR2103R001-8 / STYPE26X20 confirmed MANYOK, 65 REOK barriers and MANCPOK for
four 20×26 frames / 6240 bytes / raw speed 10. Serialization follows
`DiyFragment.getSendData` → `DataUtils.colorConvertBRGArray`: concatenate frames,
then columns, then rows, each pixel **GRB**. Despite the converter name, it is
not BRG. Native XMAS 03 switched whole strings cleanly about every 2 s and
continued after disconnect. Another effect resumed after an actual power cycle;
do not infer permanent retention or a saved startup selection. See
[buffered format/API](buffered-animations.md) and [actual experiment](buffered-animation-investigation.md).

**Explicit persistence update (0.6.0):** a further authorized experiment sent
SMVEW 2 one second after MANCPOK, waited six seconds, then disconnected. An
actual power cycle restored XMAS 03 animation, but not its selected speed. A
subsequent temporary XMAS 04 upload **without** SMVEW 2 played normally; power
cycling restored the saved XMAS 03. Thus the library now separates temporary
play from explicit persistent save on this verified model/firmware. This use
of the known save opcode was physically tested, not inferred merely from its
single-image-editor app call site. See [current storage API](effect-playback-storage.md).

`.data.{Text,Diy,DiyAnim,Anim}Agreement.getSendData`: chunk into **18 payload bytes** without app MTU-success flag; with flag, **98** for Text, **96** for Diy/DiyAnim/Anim. Allocate `capacity+2` even for last frame. Byte 0 = actual payload length + 1; byte 1 = zero-based frame number narrowed to one byte; copy payload from byte 2, pad unused capacity with zero. These indexed frames go to `writeBy2` **without command AES**. Do not infer the capacity from arbitrary negotiated MTU or assume wrapping frame numbers work. Terminal `ERROR` is recognized in text/DIY paths. ACKs are application notifications, not GATT write responses. No universal retry/timeout guarantee established.

`.data.ImageAgreement.sendData` instead splits the serialized bitmap into 15-byte pieces, forms `[actual length][payload][zero fill to 16]`, encrypts each block, writes W2. There is no frame index in this path. Content serialization is model dependent (`Text536/1248/1456/1664`, `ImageAgreement.getBitmapBytes*`, `Agreement.getDiyBytes1248`); sending RGB triples as a generic bitmap would be incorrect.

## W3: real-time data

For a single edited point `LedView.getRealTime` routes to `get2038RealTime` regardless of the passed screen type. Plaintext = `05 coord1 coord2 green red blue` plus ten zero bytes. Both coordinates are narrowed to one octet; edit mode 2 clears all three color bytes. The app encrypts once and writes W3. `LedEditActivity.sendDiyImageData` delays 10 ms per list item before scheduling sends. Distinguish coordinate arguments from actual panel orientation; no physical origin or axis direction was measured.

**Physical calibration update (2026-11-21):** on the connected STYPE26X20
controller, coord1 is LED position down a string (0–25), coord2 is string
left-to-right (0–19) in the agreed front view. Single colored origin, adjacent
axis and endpoint markers were confirmed, followed by custom frame playback.
`Screen.getLedSize` maps this reported type to [20 columns,26 rows]; do not
blindly treat the reported numeral order as [width,height]. The read-only BLE
subscription yielded STYPE without an extra W1 query. See
[calibration record](topology-live-frames.md) and [live-array API](live-frames.md).
The earlier static-analysis caveat above applies to the original analysis;
this calibration is specific to the tested mounting/model.

`MusicPlayerManager$2.onWaveDataCapture` obtains a block from `FftConvertUtils.getFftData`, encrypts it and writes W3; `MicrophoneFragment.sendRhythmData` also encrypts before W3. The music encoder packs successive levels into high/low nibbles, then copies 13 packed bytes into positions 1–13 of a zero-initialized 16-byte block with byte 0 = 15. The last two bytes are zero. `LedEditActivity.sendDiyImageData` and `$7.run` send encrypted edit blocks via the same characteristic. `BP.sendFftDataToDevice` misleadingly builds a `TIME` command: follow actual audio call sites, not that method name.

## Verification boundary

### Physical findings: TR2103R001-8, STYPE26X20 (2026-11-21)

See the [session record](hardware-session-2026-11-21.md) for individual commands,
human confirmations and limitations. LEDON resumed the saved effect. EFFE 3 and
4 selected different continuing animations; SPEED 80 was faster than SPEED 20,
with Chase retained. COLO alone briefly produced red before the previous effect
resumed. EFFE 0 followed by COLO produced steady red, and subsequent green was
confirmed. LIGHT → EFFE 0 → COLO produced steady green at levels 20 and 80,
with 20 dimmer. LIGHT alone did not maintain static green in those tests, but
LIGHT 80 during Chase eventually produced brighter Chase after briefly showing
a different effect. These observations establish useful sequences, not a fully
understood controller state machine or transition-free behavior.

The W1 table covers builders found in `Agreement` and `BleProtocol`. The adjacent transfer protocols above describe the transport, not a promise of universal panel compatibility. Exact per-model bitmap/glyph rasterization, effect names/ranges, live-edit pixel mapping, reply latency, controller persistence and negotiated write properties need further comparison or hardware evidence. No OTA flashing sequence or proprietary font/image assets are included. See [hardware validation](hardware.md).
