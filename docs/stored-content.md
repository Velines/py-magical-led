# Stored content and the app catalogue

Rechecked 2026-11-21 against both DEX files and `resources.arsc` from the
hashed 1.2.0 input in [protocol.md](protocol.md). This was static local
inspection; **no additional controller commands were sent** for this recheck.

## Findings

There are three distinct catalogues, not one device directory:

| Kind | App catalogue | Command | Evidence |
|---|---|---|---|
| Lighting effects | Five named effects, IDs 1–5 | `EFFE id` | `LightActivity.createMainDatas`, `$7.onItemSelected` |
| Default images | 25 entries, IDs 1–25 | `IMAG id` | `ImageFragment.<clinit>`, `$1.onItemClick`, `sendImageData` |
| Default animations | 25 entries, IDs 1–25 | `ANIM id` | `ImageFragment.<clinit>`, `$2.onItemClick`, `sendContent`, `$3.run`, `BleProtocol.sendAmin` |

`ImageFragment.<clinit>` constructs both 25-element lists from Android resource
IDs before connecting to any peripheral. `initImageDatas` and `initAnimData`
give those lists directly to adapters. The click listeners add one to the
zero-based selection position. `sendAmin` calls `Agreement.getAnimCommand`,
encrypts its 16-byte value and calls `BleManager.writeAll`. This path selects
a preset; it does not fetch a list or upload animation frames.

The image resource names are `default_2038_image_1` through
`default_2038_image_25`, resolved to BMP files under `res/mipmap-xxhdpi-v4/`.
The animation resources are arrays named `anim1` through `anim25`: 10 entries
each except `anim7` and `anim17` (8 each), and `anim20` (7). These are **APK
resource identifiers and array lengths**, not controller storage records,
human-readable names, or measured hardware frame counts. The resource name's
`2038` must not be interpreted as the model of the connected STYPE26X20 device.
No vendor images or animation assets are copied into this repository.

## Custom / DIY content

`DiyFragment.getDiyImageList` queries the app's `DiyDataDao` using
`queryBuilder()`, filters `DiyType` and `ImageType`, orders by `DiyId`, and calls
`list()`. That is a local greenDAO database operation, not a BLE read.
`DataManager.getDiyDatas` returns its in-memory field. These lists cannot be
used to infer the contents of a controller used with a different phone or
installation.

`AnimAgreement.sendMoreDefaultAnim` takes caller-supplied bytes and begins the
PLAY/PLAYOK transfer flow; the reply handler advances locally held transfer
data. It does not retrieve the saved playlist. Avoid PLAY and upload commands
when merely trying to inspect presets or preserve custom content.

## What can be listed reliably?

- **The app-supported catalogue:** yes, five effect labels and image/animation
  IDs 1–25, with the provenance above.
- **The connected controller's populated slots, custom content or saved
  playlist:** no supported enumeration/readback mechanism was found in the
  inspected app paths, command builders or receive handlers. The app-specific
  direct BLE-read call site found in the DEX inspection reads firmware version;
  version/model notifications are not a content directory.
- **Preset support on this controller:** effects 3 and 4 are physically
  confirmed. ANIM 1 and ANIM 2 subsequently produced different animations on the
  physical controller without an upload (HW-015/HW-016 in the session record); IMAG and the
  full ANIM range are not verified. Selecting a known preset can test
  visible playback, but does not prove a directory API or expose custom data.

This is a conclusion about the analyzed app, not proof that no undocumented
firmware command exists. Do not invent a `LIST`/`READ` request or scan unknown
opcodes on a controller whose stored content should be preserved.
