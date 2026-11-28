# Controller state readback · 2026-11-22

## Result

The known readback surface is **partial**, not a complete current-scene query.
The controller exposes identity, logical grid and timer configuration, but no
discovered getter for current RGB, brightness, speed or selected animation.
The app's corresponding UI values are not proof those settings were read back.

This investigation queried the selected physical controller at source baseline
`06901e8` (Initial import), using existing code only. Windows / standard CPython
3.12.10 / Bleak 1.1.1, same controller as earlier hardware records. Host capture:
2026-11-22 12:21:49–12:22:10 +01:00, followed by extra standard ATT read attempts.
Raw evidence is local and ignored: `.analysis/read_current_state.json` and
`.analysis/read_current_state_extra.json`. Unique address/name suffix omitted here.

## Actual observations

| Field | Observation | Source / qualification |
|---|---|---|
| Controller reachable/powered | Yes | BLE connected; this does **not** establish that LED output is enabled |
| Device name | `MT-<suffix>` | Advertisement and GAP Device Name read |
| Firmware/build label | `TR2103R001-8` plus NUL | Direct FFF0 / …9602 read, ASCII |
| Reported model/grid | `STYPE26X20` | Automatic encrypted notification after subscribing |
| Logical geometry | 20 columns × 26 rows, 520 positions | App profile interpretation of report; actual populated-LED detection is not provided |
| SPI version octet | `0x05` (5) | Response to documented VER query; not a semantic-version string |
| OTA version octet | `0x01` (1) | Same VER response; do not treat this as LED power state |
| Scheduled-on enabled | False | STSC response, enable byte 0 |
| Scheduled-off enabled | False | STSC response, enable byte 0 |
| Schedule day masks / hour / minute fields | All zero | Disabled schedules; configured time fields are **not** current RTC time |
| Inversion | Unknown | No STIN reply in its 8 s observation window; silence is not false/off |
| Negotiated ATT MTU | 248 | Host BLE stack |
| Control-channel no-response write size | 245 bytes | GATT characteristic limits |
| Received advertising signal | −72 dBm at sample time | Host-measured RSSI; not supply/battery level or a physical-distance measurement |
| Advertising manufacturer entry | Key `0x5254`, value `00 56 03` | Raw advertisement, no confirmed current-mode interpretation for the trailing byte |

The firmware/build label and the two separately returned version octets are
different pieces of protocol information. No conversion between them is assumed.
Likewise, manufacturer-data byte 3 does **not** establish that XMAS 03 is running.

### Captured decrypted notifications

```text
STYPE: 0a535459504532365832300000000000
VER:   05564552050100000000000000000000
STSC:  0c535453430000000000000000000000
```

VER ciphertext: `9c2e9568fb5e3df3618ca4981e851725`.
STSC ciphertext: `dc33baf940ddb87e12d99e2e52061293`.
The automatic model notification used the previously observed STYPE ciphertext.
These are actual host-received values, not calculated-only examples.

## GATT enumeration and negative reads

Three services were discovered:

- Generic Access (1800): Device Name (2A00), readable.
- Control service FFF0: W1/W2/W3, notify characteristic …9601, readable
  version characteristic …9602. No brightness/color/effect read characteristic.
- OTA service AE00: AE01 write-only and AE02 notify. No OTA command or subscription
  was used; standard descriptor reads are metadata, not firmware operations.

Only Device Name and the version label advertised characteristic READ support.
There was no discovered Battery Service or Device Information Service offering
additional battery, voltage, model/manufacturer or hardware-revision values.

For completeness, separate **uncached standard ATT reads**, without vendor
commands, were attempted on FFF0 …9600, …960a, …960b and …9601 despite their
missing READ flag. All four returned protocol error **0x02: Read Not Permitted**.
Thus those attributes did not reveal a hidden current-value buffer. The FFF0
CCCD value `0100` reflected our enabled subscription, not LED power/mode state.

## What the app actually does

Read-only reinspection of both DEX files found the known query builders:
`BleProtocol.readOTAVersion` (VER), `readTimerLight` (STSC), and
`getInverStatus` (STIN). Its incoming main handler interprets model, schedule,
LEDON/LEDOFF and inversion messages. No current RGB/brightness/speed/effect-ID
query or response parser was identified in these application paths.

More importantly:

- `MainActivity.initMode` reads `mode`, `speed` and `light` using phone-local
  `SPUtils.get` preferences, with defaults **1, 50 and 50**, then sets static
  `Screen` fields.
- `Screen.getLight/getSpeed/getMode` return those static fields; they do not
  perform BLE reads.
- For example, `LightActivity$4.onStopTrackingTouch` takes the UI seek-bar value,
  updates `Screen.light`, writes phone preference `light`, then sends LIGHT.
- `Agreement.getLight(byte[])` is a power-message parser for LEDON/LEDOFF, **not**
  a brightness getter, despite its name.

Therefore the app's displayed values can be cached/default/last-commanded,
especially after a power cycle or control by another device. They must not be
reported by this library as fresh controller observations.

### LED output power: offline APK re-analysis · 2026-11-28

Magical LED 1.2.0 **can update its power icon from a controller notification**.
`MainActivity$BleListenerImpl.onChanged` decrypts the incoming value and passes
it to `Agreement.getLight(byte[])`. That parser requires more than eight bytes
and compares bytes 1–5 with `LEDON` (on) or `LEDOF` (off). It does not check the
length byte at offset 0 or the second `F`. The listener posts `open_light` or
`close_light`; `MainActivity.onEvent` calls `setPower` to update the icon.
These are receive-side matches, not evidence for a request opcode.

The icon alone is not proof of readback. `onReady` also posts `open_light`
without a power report, `setLedPlateState` posts `close_light` when no devices
remain connected, and tapping the icon updates it locally before sending the
power command. The ready sequence sends `TIME` (sets the clock), then `STSC`
and `STIN`; neither DEX exposed a dedicated read-power command. The outbound
`LEDON` and `LEDOFF` are setters, not queries.

**Next hardware check:** With LED output already off, then already on, connect
and subscribe to control notifications (`…9601`) without sending any lighting
commands. Record the raw and decrypted frames and their timing. This will test
whether the controller announces its initial state; the earlier capture had
only `STYPE`, `VER` and `STSC`. If neither run announces power, capture the
Android app's startup exchange to see whether it receives a report and what
immediately precedes it. A report that appears only on a transition is useful
for monitoring, not for querying the initial state. Until a fresh report is
observed, a read-only power check should return **unknown**, not **off**.

The library now implements that passive check as `Strip.read_power(timeout=5)`
and the CLI command `magical-led --device DEVICE_ID power-state --wait 5`.
They use only notifications received during the call, never a cached or
last-commanded value. The parser and subscription behavior were tested offline.

**Powered-on hardware check (2026-11-28):** The owner confirmed LED output was
already on. The CLI returned `unknown` after 10 seconds. A second 10-second
connection using `Strip.read_power()` recorded only `STYPE26X20` at about 31 ms
after subscription started; the API returned `None`. No lighting or W1 query
commands were sent, and LED output was not changed. This does not establish
whether the controller reports power on a state change.
Raw evidence: `.analysis/power-readback-on-2026-11-28.json` (local and ignored).

**Output-off hardware check (2026-11-28):** The owner turned LED output off
while leaving the controller reachable over BLE. The same 10-second passive
read again recorded only `STYPE26X20` at about 31 ms and returned `None`.
The owner saw the output turn on during connection even though this check did
not send a lighting or W1 query command. The run did not isolate BLE connection
from notification subscription, so the precise trigger is unknown. This is not
a sustained off-state sample. Do not assume a fresh BLE connection leaves LED
output unchanged. To isolate the trigger, compare a connection without a
subscription against a connection with one, only when turning on is acceptable.
Raw evidence: `.analysis/power-readback-off-2026-11-28.json` (local and ignored).

## Unavailable versus inferred state

No current readback was established for:

- LED output enabled/disabled in this observation window. Power notifications
  can be parsed **if received**, but none arrived; do not send LEDON/OFF as a test
  and call the result a read.
- Current RGB/pixel framebuffer, brightness, speed, content mode, effect ID,
  selected image/animation, native playback position, saved animation bytes,
  program names, slot directory or free capacity.
- Current RTC time, supply voltage, temperature or battery state.
- Current inversion setting on this firmware (query received no response).

The advertised type, known preset catalogue, local effect names and
`read_storage_capabilities()` profile flags do not fill those gaps. The latter
is **verified support metadata matched to device identity**, not a query of
what is currently playing/saved or of the current speed value. Past successful
set/store calls are also not current state after a reboot or another writer.

## Existing API coverage and next step

Exposed: `read_version`, `read_version_info`, `read_topology`, `read_schedule`,
`read_state`, passive `read_power`, raw `notifications`, and documented queries
via `send(plaintext(...))`. `read_state` / CLI `status` gathers the observed
fields over one connection, keeps unavailable fields as `None`, and records
any timeouts or read errors without fabricating defaults.

A future `read_state` / CLI `status` should preserve actual response timestamps,
raw evidence, query errors/timeouts, and explicit unknown fields (`None`),
separating observed, profile-derived and last-commanded data. It must not return
default brightness 50, inferred saved XMAS names, inversion false after timeout,
or controller power as LED-output power. Even that API would not create missing
firmware getters; further readback would require a separately evidenced protocol
path, not blind command guesses.

## Safety and scope

The only application-level characteristic writes were **read-only semantic
queries VER, STSC, STIN**, matching the app's builders. Standard subscription
CCCD writes occurred to receive replies. No TIME synchronization, power/color/
brightness/speed/mode changes, schedule setter, image/animation selection,
pixel writes, custom uploads, save command, OTA, reset or power cycle was used.
No displayed/saved state change was requested to make a field observable.
No undocumented query codes or potentially state-changing OTA protocol requests
were probed. Unknown firmware commands may exist, but this is the current
evidenced app/GATT readback boundary, not a proof of their impossibility.
