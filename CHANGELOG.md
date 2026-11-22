# Changes

## 0.6.0 — 2026-11-21

- Make XMAS 01/02 explicit full-resolution synchronized top-to-bottom wipes:
  all changing columns advance one LED row together. Keep 03/04 as cuts.
- Remove transport/storage policy from visual definitions. Add explicit playback
  delivery and separate persistent `store_effect` / `store_animation`, CLI
  `store-effect --overwrite` and read-only `storage-capabilities`.
- Verify SMVEW 2 after acknowledged upload restores XMAS 03 after power loss.
  A temporary unsaved XMAS 04 upload leaves saved XMAS 03 intact. Gate this
  behavior by both observed firmware and model; unknown profiles fail closed.
- Preserve the firmware's startup-speed limitation: animation survives, selected
  speed does not. No claim that speed is persistently saved.
- Keep one write lock through transfer and persistent commit, prefer ATT response
  for save, and never save after a failed transfer. Default playback never saves.
- Render the same visual sequence for all delivery/storage choices. Full 26-row
  wipe cycles exceed verified native capacity and are rejected before writes,
  not simplified; the user explicitly chose full resolution over three bands.
- Breaking 0.5 migration: `.transport` → `.transition`, playback `delivery` instead
  of overwrite flags, persistent replacement only through the separate store API.

## 0.5.0 — 2026-11-21

- Add **XMAS 03** (paired red/green) and **XMAS 04** (paired red/white) with
  buffered controller-side delivery, rather than downward live pixel redraw.
- Implement explicit-consent `upload_animation` / `upload_effect` and native
  delivery from `play_effect`; add CLI `upload-effect`, `--allow-overwrite` and
  raw `--wire-speed`. Native runs return after upload and continue on controller.
- Reproduce app column-major GRB serialization and MANY → MANYOK → indexed W2
  chunks/REOK → MANCP/MANCPOK, with preflight bounds, deadlines, exclusive write
  ownership and no automatic retry/rollback after failure.
- User confirmed XMAS 03 clean whole-string changes about every two seconds at
  speed 10, including after Bluetooth disconnect. Actual power cycle resumed
  another effect: auto-resume is not supported by this test, while nonvolatile
  retention/reselection remains unknown. No permanent-storage claim is made.
- XMAS 04 shares the native path and is software-tested, but not yet visually
  confirmed. Uploads can replace current custom content; no slot/readback or
  coexistence guarantee, firmware update or guessed persistence command added.

## 0.4.1 — 2026-11-21

- Named collection animations now repeat continuously by default in both
  `Strip.play_effect` and CLI `run-effect`. Use `repeat=N` / `--repeat N` for
  bounded playback. `--forever` remains a compatible explicit alias.
- Generic `play_frames` and JSON `play` keep their single-run defaults. No
  change to pacing, on-wire commands, transition limitations or saved content.

## 0.4.0 — 2026-11-21

- Add an immutable local effect collection: **XMAS 01** (red/red/green/green)
  and **XMAS 02** (red/red/white/white), translating one string right with cyclic
  wrapping on a two-second target interval; optional leftward direction.
- Export `StripedEffect`, `XMAS_01`, `XMAS_02`, `get_effect`, `list_effects` and
  `Strip.play_effect`, plus CLI `effects` and `run-effect` with offline previews.
- Support explicit `repeat=None` continuous playback without reinitializing
  between cycles; CLI named effects offer `--forever` as an explicit opt-in.
- Report host-side frame overruns and maximum write duration. Named effects
  default to no extra pixel gap to target 2 s steps; the generic frame API keeps
  its 10 ms default. Timing/appearance on hardware remains unverified for this
  faster setting; conservative gaps can make the requested interval impossible.

## 0.3.0 — 2026-11-21

- Calibrate the tested controller as 20 strings left-to-right, 26 LED positions
  top-to-bottom; frame[y][x] maps to BLE (y,x). Preserve BLE-reported grid versus
  human-observed mounting as separate evidence.
- Add `Topology`, `read_topology`, strict STYPE parsing and timeout/unknown-model
  failures; no invented topology query or fallback dimensions.
- Add `FrameMapping`, bounded RGB-array normalization and unsaved `play_frames`
  with full first-frame writes, subsequent deltas, explicit pacing/repeat,
  submission statistics, cancellation and lock/error contracts.
- Share native notification subscriptions across concurrent/nested consumers.
- Add CLI `topology`, JSON `play`, configurable discovery/connection `--timeout`,
  and a stdlib moving-dot JSON generator. Raw pixel/API compatibility retained.

## 0.2.0 — 2026-11-21

- Integrate hardware findings for TR2103R001-8 / STYPE26X20; retain negative
  results and transient effect changes in the physical-session record.
- Add high-level power, solid-color/brightness scenes, speed, effects, animation
  and image selectors. Keep raw builders and `send` unchanged.
- CLI `color` now disables effects before applying RGB; optional brightness is
  applied first. `brightness --color` restores an explicitly supplied static RGB.
- Add offline `presets` (text/JSON), `animation`, `image` and direct-read `version`
  commands. Clearly distinguish the app catalogue from actual stored content.
- Serialize complete scenes on a per-Strip lock; prevalidate bytes and delay,
  propagate failures without unsafe retries or inferred rollback.
- Add `led.ps1` for the existing portable CPython or project virtual environment.

No device inventory/readback operation was found. Preset catalogue membership
is not hardware acceptance: animations 1/2 and effects 3/4 were observed; image
presets and the remaining animation/effect IDs are not physically verified.

## 0.1.0 — 2026-11-20

Initial static protocol analysis, raw packet codec, BLE transport, minimal CLI,
offline tests and architecture/dependency documentation.
