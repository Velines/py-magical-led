# Topology and live RGB-frame investigation · TASK-003

Status: ready for review, 2026-11-21. User request: obtain dimensions from BLE,
establish physical orientation interactively, then expose a Python API taking
a sequence of 2D RGB arrays for a custom live effect. Baseline `5902606`.
No saved-content overwrite, upload or firmware change authorized by this task.

## Evidence versus interpretation

- The controller sent encrypted `d07400453062999b945eb929f9a3b603`, which
  decrypts to `0a535459504532365832300000000000`: `STYPE26X20`. This was
  reconfirmed by subscribing without lighting/query writes.
- `Agreement.parseType` maps that string to model ID 2026. For 2026,
  `Screen.getLedSize` returns `[20,26]`.
- `LedEditActivity.init` passes those values to `LedView.init`, whose first
  argument becomes `widthCount` and second becomes `heightCount`.
- The app thus presents **20 columns, 26 rows, 520 logical positions**.
  `STYPE26X20` alone does not establish physical string count, mounting direction,
  serpentine wiring or length in real-world units. Those remain to be observed.
- `LedView.get2038RealTime` creates `[5,coord1,coord2,green,red,blue,zeros]`;
  the callback encrypts it and sends W3. Despite the method name, `getRealTime`
  routes to it regardless of the passed screen type. Pixel coordinates and
  frame streaming have not yet been physically confirmed.

## Bounded plan

1. Use low brightness and unsaved live-edit controls to locate an origin point.
2. Locate adjacent points on each axis and endpoints, with user observations
   referenced to a fixed front view. Determine whether coordinates select
   individual LEDs, lines or another unit before implementing a mapping.
3. Implement bounded, timeout-protected BLE topology discovery; preserve raw
   report and source, do not claim physically measured string counts.
4. Implement explicitly mapped 2D RGB-frame playback only after live writes are
   understood. Standard Python sequences are the baseline input; no NumPy
   dependency required. Measure/report actual update constraints rather than
   promising arbitrary FPS, atomic refresh or controller-side storage.
5. Test encoding, dimensions, orientation transforms, pacing, cancellation and
   errors with a fake transport; obtain physical confirmation separately.

## Marker experiments

| ID | Commands / target | Evidence / result |
|---|---|---|
| TOPO-001 | LIGHT 20 → EFFE 0 → COLO black → SMVEW 1, each 500 ms apart; W3 `pixel(0,0,255,0,0)`; hold 12 s | PASS for single-pixel control: user saw one red LED at the very top. Horizontal location, string association and remaining background not yet confirmed. Same STYPE26X20 notification. |
| TOPO-002 | Reconnect without re-entering edit mode; W3 green `(0,1)`, wait 500 ms, blue `(1,0)`; hold 12 s | PASS for axis distinction: user reports green on another string and blue on red's string at the second LED. Thus coordinate 1 is position along a string; coordinate 2 is string selector. Left/right direction not yet confirmed. |
| TOPO-003 | W3 magenta `(25,0)`, wait 500 ms, yellow `(0,19)`; hold 12 s | PASS for endpoints: user confirmed magenta at bottom of red/blue string and yellow at top of farthest string. Follow-up explicitly places red string on the left in chosen front view. No save/upload. |

After TOPO-002, combining the model's grid with the observed axes suggests
20 strings × 26 LEDs/string. TOPO-003 confirms those endpoint locations
visually. This combines controller-reported grid dimensions and human marker
observations; it is not a sensor measurement of physical length or wiring.

## Accepted coordinate convention and implementation contract

User's front view: origin top-left, 20 strings from left to right and 26 LED
positions per string from top to bottom. `frame[y][x]` maps to W3 `(y,x)`.
Only this mounting/controller was physically checked; the BLE report itself
does not transmit origin/rotation, metre dimensions, serpentine wiring or
individual LED-presence sensing. No additional serpentine transformation is
appropriate for the already two-dimensional coordinate protocol.

Planned API: `await strip.read_topology(timeout=5)` listens for the STYPE report
without an invented query; reports app-interpreted logical dimensions and raw
report provenance. Unknown reports/timeouts fail explicitly. `play_frames`
accepts a bounded finite collection of 2D RGB frames (RGB triples or packed
0xRRGGBB), validates the complete input before lighting writes, then initializes
unsaved edit mode. First frame writes every position; later frames write only
differences. Optional transpose and flips map input coordinates to the native
grid; defaults match the tested front view. Playback owns the Strip write lock,
uses a conservative inter-pixel gap, and reports submitted-frame/write counts
and actual elapsed time. It does not promise atomic refresh or target FPS.
Failures/cancellation propagate and release locks; no implicit save or rollback
is sent, and a partial image may remain. A subsequent playback rewrites the
whole first frame rather than trusting stale cached pixel state.

## Integrated physical checks

The new CLI/API was exercised after the marker tests, before the implementation
milestone commit. The delivered source is captured by `231a40f`; subsequent
input-memory-bound/test refinements did not change the valid demo's pixel
encoding or order. The table records the actual in-progress implementation
experiments, not a claim that the user retested the exact final commit.

| ID | Operation | Actual result |
|---|---|---|
| TOPO-004 | CLI `topology` with original 10 s discovery window | FAIL: selected controller not found advertising in that window. No lighting writes. |
| TOPO-005 | API connect timeout 25 s; `read_topology(timeout=8)` | PASS: `Topology(width=20,height=26,reported_type='STYPE26X20')`, 520 logical pixels. No lighting writes. CLI now exposes global `--timeout` (default 20 s). |
| FRAME-001 | CLI `play` generated four top-row single-dot RGB frames, fps 0.5, repeat 2, brightness 20 | Host PASS: 8 submitted frames, 534 pixel writes, 22.703 s excluding setup, effective 0.3524 FPS. User requested repeat rather than confirming this first run. |
| FRAME-002 | Repeat same CLI/frame data and settings | Host PASS: 8 submitted frames, 534 pixel writes, 22.813 s excluding setup, effective 0.3507 FPS. User explicitly confirmed red→green→blue→yellow, left-to-right across the top of the first four strings, twice, ending yellow on string four. |

The first full frame writes 520 positions; later changes write two pixels each
(old dot black, new dot colored), including the loop boundary. The observed
elapsed time includes the requested 2 s per-frame holds; it is **not** a maximum
achievable link-rate benchmark. No full-frame atomic latch or minimum safe
inter-pixel gap was established. Final state: unsaved yellow point at top of
fourth string; no save or upload occurred.

TOPO-001 W3 plaintext: `05000000ff0000000000000000000000`.
This test enters unsaved edit mode; no save (`SMVEW 2`), upload or edit-exit
command was sent. The connection was closed after the observation hold.
