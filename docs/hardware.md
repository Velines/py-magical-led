# First test with a physical controller

Record controller markings, app/firmware version, host OS, Python and Bleak versions, and Git commit. Label each result by model. Keep device identifiers local. Start with one powered strip, disconnect the Android app, and note the initial color, brightness and power so you can restore them.

1. Scan. Check manufacturer prefix and discover service FFF0; record actual characteristic UUIDs, properties and effective MTU. If a candidate is invisible, check Bluetooth permission and whether it is already connected elsewhere.
2. Read `…9602` directly and record the raw ASCII version. Separately subscribe to FFF0 notify/indicate sources (SDK default `…9601`) before writing `VER`. Record the timestamp, direction, characteristic and raw value, then decrypt a 16-byte notification and compare with `VER`. Unknown or absent replies are evidence, not zeros.
3. Send on/off separately, then asymmetric red and green values to distinguish RGB from GRB. Set brightness to 50. For each, compare app and library values and record the actual visible result separately from write completion.
4. Compare effect and speed on a model with a known built-in effect. Confirm what happens on disconnect/reconnect. Restore the initial state.
5. Test media/timer features separately. Capture start, first and last chunk, ACK sequence, mode, MTU, timeouts and persistence with a small known pattern; avoid guessing whether a failed transfer committed. Check weekday order using a single enabled day. Do not use OTA to validate lighting.

Suggested evidence columns: candidate, model, input, expected bytes, observed bytes, visible result, PASS/FAIL/NOT-RUN. [The 2026-11-21 session](hardware-session-2026-11-21.md) now records checks on one physical controller. Untested commands/models remain **NOT-RUN**; successful transport writes do not establish visible acceptance.
