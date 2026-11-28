# py-magical-led

A Python library and command-line tool for Bluetooth Low Energy LED controllers
compatible with the **Magical LED** Android app.

Control colors, brightness and built-in animations, discover the LED grid, or
create custom animations from arrays of RGB values. The library includes a
documented, reverse-engineered protocol and an offline packet encoder.

## Features

- Asynchronous Python API and a small CLI, with optional [Bleak](https://github.com/hbldh/bleak) Bluetooth support.
- Power, RGB color, brightness, speed and controller preset selection.
- Live RGB-frame streaming and controller-managed animation playback.
- Explicit persistent storage on verified controller profiles—never an implicit side effect of playback.
- Offline previews and tests that do not require Bluetooth hardware.

## Installation

Requires **Python 3.12 or later**. Live control also requires a BLE adapter,
Bluetooth permissions and a compatible controller. Use a standard CPython
installation and preferably a virtual environment.

From a checkout of this repository:

```console
python -m pip install ".[ble]"
```

For packet encoding, frame generation and offline previews without Bluetooth
dependencies, install the core package instead:

```console
python -m pip install .
```

## Quick start

Discover compatible advertisements:

```console
magical-led scan
```

Replace `DEVICE_ID` with the printed identifier (or set `MAGICAL_LED_DEVICE`
in your environment to omit `--device`). Windows and Linux generally use a
Bluetooth address; macOS uses a CoreBluetooth UUID. Global options such as
`--device`, `--timeout` and `--dry-run` go **before** the command.

```console
magical-led --device DEVICE_ID on
magical-led --device DEVICE_ID color ff8040 --brightness 50
magical-led --device DEVICE_ID brightness 20 --color ff8040
magical-led --device DEVICE_ID status --json
magical-led --device DEVICE_ID sync-clock
magical-led --device DEVICE_ID set-schedule --on 18:30 --on-days weekdays --off 23:00 --sync-clock
magical-led --device DEVICE_ID schedule
magical-led --device DEVICE_ID batch "on" "color ff8040 --brightness 50" "sleep 2" "off"
magical-led --device DEVICE_ID version
magical-led --device DEVICE_ID topology
magical-led --device DEVICE_ID power-state --wait 5
magical-led --device DEVICE_ID off
```

`scan`, `version`, `power-state`, `schedule` and `status` accept `--json` for
machine-readable output. `batch` runs multiple control steps over a single BLE
connection.

Try a command without connecting to a controller:

```console
magical-led --dry-run color 123456
```

The preview prints plaintext and encrypted characteristic values, including
any planned command gaps. It does not open Bluetooth. `python -m magical_led`
is equivalent to `magical-led`; use `magical-led --help` or a subcommand's
`--help` for the available options.

**Color and brightness:** RGB is written as six hexadecimal digits. Brightness
and speed are raw controller values from 0–255, not percentages. Brightness
zero maps to one to match the app; use `off` for power-off. Supply `--color`
when adjusting brightness for a static scene, because the current RGB value
cannot be reliably read back.

**Power readback:** `power-state` listens for a fresh controller notification;
it sends no lighting commands. It prints `on`, `off`, or `unknown` if no report
arrives. The tested controller did not report power in 10-second checks. The
owner observed the LEDs turn on during the check that started with output off,
even though no lighting command was sent. Connecting or subscribing may affect
output on this controller.

## Python API

```python
import asyncio
from magical_led import connect

async def main(identifier):
    async with connect(identifier, timeout=25) as strip:
        await strip.set_power(True)
        await strip.set_color(255, 128, 64, brightness=50)

        topology = await strip.read_topology()
        print(topology.width, topology.height)

asyncio.run(main("DEVICE_ID"))
```

`connect` owns and closes the connection, including on errors. Use
`Strip(already_connected_client)` to borrow a Bleak-compatible connection.
Related methods include `set_brightness`, `set_speed`, `set_effect`,
`select_animation`, `select_image`, `sync_clock`, `read_schedule`,
`set_schedule`, `read_version`, `read_version_info` and `read_state`.
Use `await strip.read_power(timeout=5)` for LED-output power: `True` means on,
`False` means off, and `None` means no fresh report was received.

For lower-level integrations, `plaintext`, `encrypt` and `decrypt` work offline;
`send` accepts one plaintext command, while `send_sequence` serializes a group
of commands. The [protocol specification](docs/protocol.md) documents the wire
format, GATT characteristics, command catalogue and reply handling.

## Custom animations

Animations use `frames[step][y][x]`. Each pixel is an RGB tuple with integer
channels from 0–255, or a packed integer such as `0xFF0000`. Read the topology
to obtain the frame size instead of assuming a particular LED layout.

Inside an asynchronous connection context:

```python
topology = await strip.read_topology()
frames = [
    [[(0, 0, 0) for _ in range(topology.width)]
     for _ in range(topology.height)]
    for _ in range(2)
]
frames[0][0][0] = (255, 0, 0)
frames[1][0][1] = (0, 255, 0)

await strip.play_frames(frames, topology=topology, fps=0.5,
                       repeat=None, brightness=20)
```

The same arrays can be used with separate playback or storage operations:

| Method | Behavior |
|---|---|
| `play_frames(frames, ...)` | Host-streamed live updates; requires an active connection |
| `play_animation(frames, ...)` | Temporary buffered playback; the controller runs autonomously |
| `store_animation(frames, overwrite=True, ...)` | Explicit replacement of the persistent custom animation |

Live playback is progressive, not an atomic frame swap; requested FPS is a
ceiling rather than a guarantee. Controller-managed playback and storage have
stricter capacity limits and are enabled only on verified firmware profiles.
See [animation, delivery and storage documentation](docs/effect-playback-storage.md)
for orientation, timing, cancellation and capacity details.

## Pre-made effects

An optional local collection provides paired red/green and red/white patterns,
with synchronized downward wipes or whole-picture cuts:

```console
magical-led effects
magical-led --device DEVICE_ID run-effect "XMAS 01" --brightness 20
magical-led --device DEVICE_ID run-effect "XMAS 03" --brightness 20
```

Effect definitions are independent of playback delivery and storage. Live
effects repeat until interrupted unless a repeat count is supplied; buffered
effects continue on the controller after the upload command returns.

`magical-led presets` lists a different catalogue: the presets known to the
Android app. Neither listing is an inventory of custom content saved on the
connected controller. See [effect definitions and usage](docs/effect-playback-storage.md)
and [preset catalogue investigation](docs/stored-content.md).

## Compatibility and limitations

The protocol baseline is **Magical LED for Android 1.2.0**. Physical testing
has used firmware **TR2103R001-8**, reporting **STYPE26X20**, on Windows. Bleak
provides Windows, Linux and macOS backends, but physical behavior on other
platforms and controller profiles has not been verified by this project.
Not every strip advertised under a similar app or product name is compatible.
Not all commands and preset IDs have been physically tested; the verification
record distinguishes implemented functionality from observed behavior.

- **Persistent writes are explicit and destructive.** The protocol has no saved-content inventory, backup or verified free-slot query. Storage requires permission to replace the custom program.
- **Capacity depends on the transfer format.** At the tested 20×26 layout, current native-format checks limit transfers to 15 full frames. Oversized effects are rejected before content writes, not silently simplified.
- **Saved speed is a firmware limitation.** The tested controller restores a saved animation after power loss but not its selected speed.
- **Write completion is not visual acceptance.** Commands can cause transient display changes, and failed/cancelled sequences may leave a partial scene. There is no automatic rollback.
- **Effects can flash.** Consider photosensitive observers before selecting animations or effects.

For connection problems, power the controller, disconnect other controlling
apps, check Bluetooth permissions and try a longer discovery window with
`--timeout 25`. Compare a dry-run packet with the documented protocol when a
write completes but the display does not behave as expected.

## Documentation

- [Effects, RGB arrays, playback and persistent storage](docs/effect-playback-storage.md)
- [BLE protocol specification](docs/protocol.md)
- [Live-frame API and coordinate mapping](docs/live-frames.md)
- [Architecture and implementation contracts](docs/architecture/README.md)
- [Verification results and known limitations](docs/verification.md)
- [Hardware test procedure](docs/hardware.md)
- [Third-party components and license records](docs/dependencies/third-party-components.md)
- [Changelog](CHANGELOG.md)

## Development

Run the test suite from the repository root:

```console
python -m unittest discover -s tests -v
```

The automated tests use offline vectors and fake BLE transports; they do not
require a controller. Hardware results are recorded separately. When proposing
support for a new controller, include its model, firmware, host platform and
observed behavior, and distinguish transport success from visible acceptance.

## License

Licensed under the [MIT License](LICENSE).

Copyright (c) 2026 py-magical-led contributors. Third-party components retain
their respective licenses; see the [component inventory](docs/dependencies/third-party-components.md).
