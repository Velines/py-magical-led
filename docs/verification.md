# Offline verification · 2026-11-20 · ready for review

**Latest increment:** [0.6.0 independent effects and persistent saves](#060-independent-effects-and-persistent-saves--2026-11-21),
[0.5.0 buffered controller playback](#050-buffered-controller-playback--2026-11-21),
[0.4.1 continuous collection default](#041-continuous-collection-default--2026-11-21),
[0.4.0 pre-made effects](#040-pre-made-effects--2026-11-21),
[0.3.0 topology and live frames](#030-topology-and-live-frames--2026-11-21),
[calibration/custom-effect observations](topology-live-frames.md), and earlier
[physical-session observations](hardware-session-2026-11-21.md). The
following 0.1.0 report is retained as historical evidence, not current scope.

Tested source was committed as **`a29a7c5406b040268957bc521cc8f2894dc6e44f`** on `feat/protocol`. Earlier `c7d8d4e` is the preliminary static spec; use the later specification, including its correction distinguishing version **read** from **notify**. Working directory for checks: repository root on Windows NT 10.0.26200 x64. No radio operation was run.

| Check | Command / evidence | Result |
|---|---|---|
| Input identity | PowerShell `Get-FileHash`; ZIP manifest, base/split APK, both DEX files inventoried | PASS; input and ELF identifiers in [spec](protocol.md). `classes.dex`: `223d4355de70cb40c6c7b904aee34bdfaac89e1bb82d3df1727190bc6223e120`; `classes2.dex`: `447e962b584db701e9f0fd04bf24cb31e25c807e2b7a7cf5fb99f3f134bbf844`. |
| Native transform | `readelf -rW`, `objdump -d -M intel`; compared all 256 computed forward and inverse S-box entries to x86-64 ELF offsets 0x1980 / 0x1880 | PASS, no differing entries. Static comparison only. |
| App-labeled effect order | Read DEX resource IDs in `LightActivity.createMainDatas` and position increment in `$7.onItemSelected`, resolve in default `resources.arsc` | PASS, five IDs mapped; no visible-effect claim. |
| Library, fake GATT, CLI | CPython 3.12.12 `python -m unittest discover -s tests -v` | **PASS, 11/11**, exit 0. See cases below. |
| Build and install | pip 25.3 `wheel --no-build-isolation --no-deps --no-index --no-cache-dir --wheel-dir .analysis/candidate .`; `pip install --no-index --no-deps --target .analysis/check <wheel>` | PASS, exit 0. `pymagical_led-0.1.0-py3-none-any.whl`, SHA-256 `a45bf7932e0b6bad13d7c32e6b6188b661c6ba1d00e461df038eef18246b88ea`. Wheel contents: project modules and distribution metadata only. |
| Installed executable | `.analysis/check/bin/magical-led.exe --dry-run color 123456` using the isolated target on `PYTHONPATH` | PASS, exit 0; `plain 07434f4c4f3412560000000000000000`, `wire 1153d5d091266d514a11b97aa7887092`. |
| Windows backend import | Standard python.org CPython 3.12.10 x64, installed wheel and resolved `[ble]` dependencies; call Bleak `get_platform_client_backend_type()` and `get_platform_scanner_backend_type()`; check asymmetric RGB vector | PASS, exit 0: `BleakClientWinRT`, `BleakScannerWinRT`. No connection or discovery requested. |
| Inkscape Python backend import | Same Windows dependency wheels, bundled GCC/UCRT Python 3.12.12 | FAIL: `ModuleNotFoundError: winrt._winrt`; that interpreter works for offline use but is not the standard Windows extension ABI. Use standard CPython for live Bluetooth. |
| Hardware / other OS / independent reviewer | [First hardware session](hardware.md) | NOT-RUN. Linux/macOS backends, radio compatibility, app-to-strip timing, persistence and visual results remain unverified. |

Offline tests exercise independent expected AES ciphertexts for power/brightness/asymmetric RGB, decryption, clock/length/brightness quirks, malformed arguments, short final chunks in both formats, and sequence rollover refusal. Async tests assert service-scoped characteristic objects, W1/W2/W3 values, write response mode, size limits, missing/unsupported characteristics, notification cleanup on timeout, and the unencrypted version read. CLI tests spawn the interpreter with `-S` (no site packages), check both output lines, and check error status for missing target and bad input.

The Windows dependency resolver also reported an unrelated preinstalled `beautifulsoup4` / missing `soupsieve` conflict in the bundled interpreter; neither is in the project or resolved Bleak wheel set. The actual standard-ABI backend check used a separate interpreter. No dependency or APK was bundled into the project wheel.

**Handoff:** owner to run the [hardware checks](hardware.md) against the exact controller and record its model, candidate and observed results. Offline development criteria are ready for review; independent requirements/behavior review, formal trace audit, physical verification and release/distribution approval remain open. No release, upload or deployment was performed.

## 0.2.0 integration · 2026-11-21

Source candidate **`bda9838a910201473d8293c5aa04228fd35fc173`**, branch
`feat/protocol`. Same Windows host and tools as above; standard portable
CPython 3.12.10 / Inkscape Python 3.12.12, Bleak 1.1.1. Commands below ran from
the repository root unless noted. No new dependencies or shipped vendor assets.

| Check | Executed command / observation | Result / exit |
|---|---|---|
| Full regressions | Inkscape Python `-m unittest discover -s tests -v` | PASS, **20 tests**, exit 0 |
| Scene ordering and validation | `ClientTests.test_high_level_static_sequence`, `test_sequence_prevalidation_and_failure`, `test_sequence_cannot_interleave` | PASS: explicit raw brightness, EFFE 0, GRB frame order; prevalidation before first write, stop on failure, concurrent power write cannot interleave |
| CLI/API dispatch | CLI subprocess tests with `-S`; mocked live dispatcher | PASS: same static scene frames, animation vector, direct read, no BLE dependency needed for previews |
| Catalogue semantics | JSON subprocess output / preset tests | PASS: 25 animations, 25 images, effect IDs 0–5, model-specific observed entries, `device_inventory=false`; invalid known-catalogue IDs rejected |
| Build/install | pip `wheel --no-build-isolation --no-deps --no-index --no-cache-dir --wheel-dir .analysis/integration-dist .`; `pip install --no-index --no-deps --target .analysis/integration-install <wheel>` | PASS, exit 0 for both; installed metadata reports 0.2.0 |
| Installed package smoke | Standard CPython with isolated installed package/dependency paths; `main(['--dry-run','brightness','20','--color','00ff00'])` | PASS, exit 0: exact LIGHT 20, EFFE 0, COLO-green wire values from manual session |
| Portable launcher | `led.ps1 --dry-run color 00ff00 --brightness 20`; `presets animations --json`; `--dry-run animation 2` | PASS, exit 0; no package installation or activation |
| Launcher outside repository | From `D:\PRJ`, absolute launcher path with `--dry-run animation 2` and `--dry-run version` | PASS, exit 0; source and dependencies resolved relative to script |
| Integrated live version read | `led.ps1 --device <selected-local-id> version` | PASS, exit 0; raw `545232313033523030312d3800`, text `TR2103R001-8`; no lighting writes |
| Documentation / diff | Relative Markdown file-link check; `git diff --cached --check`; source/doc/inventory review | PASS, no broken file links or whitespace errors; no APK, DEX, firmware or credentials staged |

Built wheel: `py_magical_led-0.2.0-py3-none-any.whl`, SHA-256
`5b945d47f58b60a9e1d2e2d71d6bec3b478a5b2168738a305c6addfca81088fd`.
It is a local validation artifact in the ignored analysis directory, not a
published release. No changes were made to the old installed 0.1.0 copies;
`led.ps1` loads current checkout source. Users of an installed package should
reinstall from this checkout to pick up 0.2.0.

**Verification boundary:** human-confirmed visible results are recorded per
manual experiment in the hardware-session document. New high-level helpers
reproduce those byte sequences in automated tests, but no additional physical
scene acceptance was inferred from unit tests. Only the new version CLI command
was exercised live during integration. Image playback, most preset IDs,
minimum command delays, power-cycle persistence, Linux/macOS radio operation,
diagram rendering and independent review remain NOT-RUN. Transient wrong-effect
output is an open firmware/interaction finding, not hidden by the convenience API.

**Handoff:** implementation ready for user review. Next useful physical check:
run the integrated `color ... --brightness ...` CLI and confirm final state,
then optionally test image presets individually. No unknown-opcode scans,
uploads, saves, firmware changes, publication or deployment occurred.

## 0.3.0 topology and live frames · 2026-11-21

Delivered source candidate **`231a40f221b3529c309bfe7448498c34c594bae9`**,
baseline `5902606`, branch `feat/protocol`. Same Windows host and existing
CPython/Bleak/build-tool versions as above; no new dependencies. Inputs and
accepted mounting observations are in [calibration evidence](topology-live-frames.md).

| Check | Executed command / assertion | Result / exit |
|---|---|---|
| Full source regressions | Inkscape Python `-m unittest discover -s tests -v` | PASS, **33 tests**, exit 0 |
| BLE-derived dimensions | Strict packet/profile parse tests plus real CLI `led.ps1 --timeout 25 --device <selected-local-id> topology` | PASS: width 20, height 26, pixel_count 520, raw STYPE26X20, orientation-from-BLE false; exit 0, no lighting writes |
| Discovery failure preserved | Initial CLI topology with original 10 s discovery window | FAIL: target not found advertising; no commands sent. Longer 25 s discovery subsequently succeeded; CLI exposes timeout instead of hiding retries. |
| Topology error/lifecycle tests | Unknown/invalid report, timeout, cache, shared/nested notification consumers, callback isolation and partial subscription setup failure | PASS; no default grid or W1 query, cleanup asserted |
| Frame encoding/geometry | RGB triples/packed integers, copied buffers, shape/channel rejection, frame/pixel bounds, transpose/flips, first-frame native coordinates and GRB bytes | PASS; synthetic sizes plus fixture; hardware only confirms default mapping on the tested device |
| Playback lifecycle | Full first frame, delta/loop boundary, sequence lock/cancellation, stop on first pixel error, pacing overrun test | PASS; no implicit save or rollback; failure/cancellation tests assert lock release |
| Source CLI dry run | `led.ps1 --dry-run play .analysis/topology-moving-dot.json --fps 0.5 --repeat 2` | PASS, 8 frames / 534 planned writes, input-derived dimensions explicitly not a BLE read |
| Visible custom effect | FRAME-002 in calibration record, CLI `play ... --fps 0.5 --repeat 2 --brightness 20` | PASS for the tested in-progress playback: user explicitly confirmed colored point movement/direction/final position. 8 frames / 534 writes / 22.813 s excluding setup; no save/upload. See candidate qualification below. |
| Build/install | pip `wheel --no-build-isolation --no-deps --no-index --no-cache-dir --wheel-dir .analysis/frames-dist .`; `pip install --no-index --no-deps --target .analysis/frames-install <wheel>` | PASS, exit 0 for both; installed metadata 0.3.0 |
| Installed package smoke | Standard CPython with isolated installed package/dependency paths, parse STYPE and `main(['--dry-run','play','tests/fixtures/tiny-frames.json','--repeat','2'])` | PASS, exit 0; 2×2 synthetic input, 4 frames / 10 planned writes |
| Documentation / staging | Relative Markdown file-link check; `git diff --cached --check`; source/doc/component review | PASS; no broken file links or whitespace errors; staged example/fixture are synthetic, no APK/vendor assets |

Local wheel `py_magical_led-0.3.0-py3-none-any.whl`, SHA-256
`36b25e1db85b78d19cd067be10d0b8f23b0529ac13f29ab35b1bcfe9cc85a654`.
No package was published. `led.ps1` loads current checkout source; existing
installed distributions need reinstalling to pick up 0.3.0.

**Candidate qualification:** the human-confirmed frame demo ran during
implementation, followed by an additional total-pixel memory bound and test/doc
refinements. Valid-frame pixel encoding, orientation and playback sequence did
not change. The final candidate's offline tests/build and actual BLE topology
read passed; a second human visual acceptance of the exact committed candidate
was not requested or implied. No all-platform or release acceptance is claimed.

**Limits and handoff:** live W3 refresh is progressive, not atomic. 22.813 s
includes requested frame holds and is not peak throughput. Faster pixel delays,
other controller profiles, physical flips/transposes, power-cycle persistence,
automatic restoration after partial failure, and independent verification remain
NOT-RUN. Final observed output was an unsaved yellow point at the top of string
four. The user can now supply bounded RGB 2D arrays through `play_frames` or JSON
through CLI `play`; see [API and limits](live-frames.md). Implementation is ready
for review, with no saves, uploads, firmware changes, push or release performed.

## 0.4.0 pre-made effects · 2026-11-21

Source candidate **`beb39168cfcc7584dea66228341074fd102bb77a`**, baseline
`673922c`, branch `feat/protocol`. Same Windows host and existing CPython,
Bleak and build-tool versions. User scope: XMAS 01 and XMAS 02 paired-string
patterns and two-second translation, with reusable collection/API/CLI.

| Check | Executed command / assertions | Result / exit |
|---|---|---|
| Full source suite | Inkscape Python `-m unittest discover -s tests -v` | PASS, **42 tests**, exit 0 |
| Patterns and names | `EffectTests`: exact RGB palettes/names, full-height columns, initial paired bands, all four one-column right shifts/loop boundary, left variant, partial-width/small grids, immutable registry and memory bounds | PASS; both 20×26 effects have four phases, ten changed columns / 260 changed LEDs per transition |
| Scheduling / continuation | `PlaybackTests.test_named_effect_two_second_schedule`, `test_continuous_repeat_does_not_reinitialize_each_cycle`, existing slow-link/cancellation tests | PASS: simulated fast link submits 8 phases in 16 s excluding setup; continuous cycles retain delta state without re-clearing; overruns reported without catch-up bursts |
| CLI / dispatch | `CliTests.test_library_effect_listing_and_preview`, mocked live dispatch and overrun warning | PASS: separate library collection, named lookup, explicit offline geometry, bounded/continuous previews, canonical-name dispatch, timing warning |
| Portable launcher outside repo | From `D:\PRJ`, absolute `led.ps1 effects` and `--dry-run run-effect 'XMAS 01' --width 20 --height 26 --repeat 2` | PASS, exit 0; 8 frames / 2340 planned pixel writes / 2 s target step |
| Build/install | pip `wheel --no-build-isolation --no-deps --no-index --no-cache-dir --wheel-dir .analysis/effects-dist .`; `pip install --no-index --no-deps --target .analysis/effects-install <wheel>` | PASS, exit 0 for both; installed metadata 0.4.0 |
| Installed smoke | Standard CPython with isolated installed package/dependency paths, check both exported names and CLI offline XMAS 02 preview at 20×26, repeat 2 | PASS, exit 0; 8 frames / 2340 planned pixel writes |
| Attempted physical XMAS test | `led.ps1 --timeout 25 --device <selected-local-id> run-effect 'XMAS 01' --repeat 2 --brightness 20` | FAIL at discovery, exit 1: selected device not found advertising. No effect initialization or pixel writes occurred. Visible pattern, zero-extra-gap delivery and actual 2 s timing NOT-RUN. |
| Documentation / diff | Relative Markdown file-link check; `git diff --cached --check`; source/doc/inventory review | PASS; no broken file links or whitespace errors; no external assets, vendor code or dependencies added |

Local wheel `py_magical_led-0.4.0-py3-none-any.whl`, SHA-256
`f030044fd518cafa49d69b00c6d34b4123cdbeee581634308ce0682e295f654a`.
It remains an ignored validation artifact, not a published release.

**Timing disposition:** the user-requested physical two-second step remains
unverified. Generic 10 ms gaps alone would require 2.6 s per 260-pixel transition;
the named helper defaults to zero extra gap, while still awaiting/yielding per
write. That target is software-tested under a simulated fast link, not a radio
delivery guarantee. Raw `play_frames` retains its 10 ms default. New finite-run
statistics report timing overruns; continuous runs should follow a successful
bounded physical check. W3 updates remain progressive, not atomic strip swaps.

**Handoff:** collection/API/CLI implementation ready for review, hardware
acceptance pending. Power the controller, disconnect other centrals, run a
bounded XMAS 01 cycle at low brightness and confirm full-height bands, direction,
wrap and actual interval; then check XMAS 02/white separately. No saved effect
was overwritten, no firmware/upload/save commands were sent during this task,
and nothing was pushed or published.

### XMAS 01 hardware retry · 2026-11-21

Candidate `f9e19b8` (implementation `beb3916`), following the user's confirmation
that the controller was available again. Actual command:
`led.ps1 --timeout 25 --device <selected-local-id> run-effect 'XMAS 01' --repeat 2 --brightness 20`.
Exit 0. Reported 8 submitted frames, 2340 pixel writes, **16.047 s** excluding
setup, **0 overrun frames**, maximum frame-write time **1.719 s**, effective
0.4985 FPS. The host met the two-second target in this bounded run, but the
user then confirmed only the paired pattern and reported that it was not
shifting, at least not every two seconds. **FAIL for visible animation/timing**;
host completion did not prove delivery/application. No save was requested.
XMAS 02 is not yet tested.

Diagnostic follow-up: same effect, repeat 1, brightness 20,
`--pixel-delay 0.01`. Exit 0; four submitted phases / 1300 pixel writes /
21.688 s excluding setup, four overrun frames, max write duration 8.688 s.
This intentionally slower run tests whether pacing restores visible movement;
the user confirmed changes proceeding down the strings. This is a progressive
repaint, not the requested whole-picture transition. Zero-gap overload/drop is
still a hypothesis, not a proven cause.

Further diagnostic: one XMAS 01 cycle at brightness 20, zero extra gap, with
an analysis-only client proxy forcing GATT `response=True` for W3. Existing
source player/encoder used unchanged; no diagnostic proxy added to the library.
All 1300 W3 writes completed at ATT level. Four phases took **60.406 s**, with
four overruns, maximum frame-write duration **24.265 s**, effective 0.06622 FPS.
This did not meet timing and does not establish atomic visible updates.
**FAIL for the requested transition with the tested live paths.**

Next candidate approach is the app's buffered MANY/W2/MANCP animation transfer.
Read-only static review only; uploading may replace existing custom content,
which cannot currently be backed up over the discovered BLE protocol. See
[buffered investigation](buffered-animation-investigation.md). No such upload,
firmware operation, save or persistent-content replacement was performed.

### XMAS 02 bounded physical submission · 2026-11-21

At the user's request, candidate `d781bbf` ran
`led.ps1 --timeout 25 --device <selected-local-id> run-effect 'XMAS 02' --repeat 1 --brightness 20 --pixel-delay 0.01`.
Exit 0. Four submitted phases / 1300 pixel writes / 21.641 s excluding setup /
four overruns / max write duration 8.641 s. No save/upload. The user next
requested continuous default playback rather than confirming visible pattern
details, so appearance/transition acceptance remains pending.

## 0.4.1 continuous collection default · 2026-11-21

Source candidate **`87bed0c416d11ba90e11a4e9ea3b34a9f59b4cf6`**, baseline
`d781bbf`. User-requested behavior: starting an animation in the library
collection should repeat continuously without needing an explicit repeat flag.

| Check | Executed command / assertions | Result / exit |
|---|---|---|
| Full source regressions | Inkscape Python `-m unittest discover -s tests -v` | PASS, **43 tests**, exit 0 |
| API default | Helper test calls `play_effect('XMAS 02')` with no repeat argument and asserts delegation uses None | PASS |
| Actual loop behavior | `PlaybackTests.test_named_effect_continues_past_first_cycle_by_default` executes real player with a fake transport, cancels after entering phase 0 of the second cycle | PASS: continues past four phases without a second initialization; write lock released on cancellation |
| CLI policies | Offline previews and mocked live dispatch | PASS: omitted repeat is continuous; explicit `--repeat 1` is four frames / 1300 writes at 20×26; `--forever` alias retained; bounded/mutual-exclusion behavior preserved |
| Generic player defaults | Installed signature assertions and existing bounded generic-frame tests | PASS: `play_frames` retains repeat=1; named `play_effect` defaults to None |
| Build/install | pip `wheel --no-build-isolation --no-deps --no-index --no-cache-dir --wheel-dir .analysis/continuous-dist .`; `pip install --no-index --no-deps --target .analysis/continuous-install <wheel>` | PASS, exit 0; installed metadata 0.4.1 |
| Installed smoke | Standard CPython, isolated installed package/dependency paths; assert signatures; CLI dry-run XMAS 01 without repeat flag | PASS, exit 0; continuous=true, unbounded frame/write totals represented by null |
| Documentation / diff | Relative Markdown file-link check; `git diff --cached --check`; source/doc review | PASS; no broken file links or whitespace errors |

Local wheel `py_magical_led-0.4.1-py3-none-any.whl`, SHA-256
`af5dbc26924caea0cef82e7225cbf6325cf3ab9a107093a7a2fe4b766e6263be`.
Environment/toolchain/dependencies unchanged from prior entries; no network
services, third-party packages or protocol operations added.

No new physical run was started for this default-only change, to avoid leaving
an unattended infinite animation. This does **not** fix or accept the known
visible transition/timing failures. Playback remains live/unsaved and requires
the process/connection to remain active. CLI Ctrl+C or Python task cancellation
stops streaming and disconnects through the existing ownership contract; the
last/partial image may remain. Buffered upload authorization is still pending;
no overwrite, upload, save, push or release was performed.

## 0.5.0 buffered controller playback · 2026-11-21

Delivered source candidate **`e9568c95ca86b998e1acb58a62934448984f08ba`**, baseline
`dd0d35a`. Same Windows / CPython 3.12.12 development and standard portable
3.12.10 / Bleak 1.1.1 / pinned build tooling as prior increments. User explicitly
clarified paired-string XMAS 03/04 and authorized a bounded custom-animation
upload despite possible replacement of existing custom content. No reset or
firmware authorization. [Exact bytes and observations](buffered-animation-investigation.md).

| Check | Executed command / assertions | Result / exit |
|---|---|---|
| Full source regressions | Inkscape Python `-m unittest discover -s tests -v` | PASS, **53 tests**, exit 0 |
| Native encoding | TEST-011 asymmetric 2D RGB → frame/column/row GRB; MANY count/speed/big-endian size; padded indexed chunks and size/index bounds | PASS; no per-chunk command encryption or sequence rollover |
| Consent / preflight | TEST-012 rejects missing consent before subscriptions/writes; CLI rejects before connecting; validates actual GATT write limit before MANY | PASS; no implicit upload when listing/previewing or running live 01/02 |
| Transfer lifecycle | MANYOK → per-chunk REOK → MANCPOK; ERROR/unexpected reply, per-step/total deadline, cancellation cleanup and no finish/retry after failure | PASS with fake transport; lock and subscriptions released |
| Collection routing | XMAS 03/04 select buffered path; 01/02 retain live streaming; explicit `upload_effect` can buffer any name | PASS; reject host repeat counts/live pacing for autonomous buffered delivery |
| Physical authorized upload | Public API `play_effect('XMAS 03', topology=<BLE-derived>, allow_overwrite=True, wire_speed=10, brightness=20)` | PASS at application ACK level: four frames / 6240 bytes / 65 chunks, MANYOK + 65 REOK barriers + MANCPOK, elapsed 2.594 s including optional brightness settle |
| Visible native result / disconnect | User observation after 12 s hold then closing Bluetooth | PASS: paired red/red/green/green, clean whole-string changes, about two seconds per step, continues after disconnect |
| Actual power cycle | User's later performed test (earlier yes was retracted before testing) | FAIL for auto-resume: another effect returned. Does not distinguish erased buffer from a different startup selection; nonvolatile retention/reselect remains unknown |
| White XMAS 04 | Generated pattern, shared native encoder/handshake and CLI preview | Software PASS; physical appearance NOT-RUN |
| CLI source and isolated install | `led.ps1 effects`; offline `upload-effect XMAS 03` preview; standard CPython installed-wheel `run-effect XMAS 03` preview | PASS, exit 0; four frames / 6240 bytes / 65 chunks; final encoder SHA matches the actually uploaded payload |
| Build/install | pip `wheel --no-build-isolation --no-deps --no-index --no-cache-dir --wheel-dir .analysis/buffered-final-dist .`; `pip install --no-index --no-deps --target .analysis/buffered-final-install <wheel>` | PASS, exit 0 for both; metadata 0.5.0 and installed-module path checked |
| Documentation / staging | Relative Markdown file-link check; `git diff --cached --check`; source/doc/inventory scan | PASS; no new dependencies, firmware/vendor assets or device addresses staged |

Final local wheel `py_magical_led-0.5.0-py3-none-any.whl`, SHA-256
`50ddd8d50b81a13c40d30000861b802e58fa613f1d72854bcbfc424da067aad3`.
No package was published. The actual native upload occurred during implementation;
later changes added CLI/argument guards/docs without changing its valid default
packet sequence. The final installed preview reproduces payload SHA-256
`6e1e31f5541846595de4a74d8e92fda3ffec2f42809aa77ab6c672f17d416caa`
and header `084d414e59040a186000000000000000`, matching the physical experiment.

**Handoff and limits:** native 03 playback is controller-managed, not host FPS
scheduling; speed 10 is only approximately human-calibrated on this firmware.
It does not prove a general raw-speed conversion, nonvolatile retention, startup
configuration, multiple simultaneous stored names or free slots. Every high-level
upload requires overwrite consent and may leave partial custom content on
failure; no backup/readback/rollback is available. The next optional physical
check is buffered XMAS 04 at low brightness with explicit overwrite consent.
No extra Bluetooth writes were sent during or after the power-cycle observation.
No guessed persistence command, OTA, firmware write, reset, push or release occurred.

## 0.6.0 independent effects and persistent saves · 2026-11-21

Source candidate **`6b52994c3f57af21966e89295eac61f50788d30e`**, baseline
`99fcf4e`. User requested synchronized row wipes and effect-independent storage,
chose full 26-row resolution despite device capacity limits, authorized the
known SMVEW 2 save experiment (including possible custom-image replacement),
then authorized temporary XMAS 04 playback/power cycling to test isolation.
Environment and dependencies unchanged. [Current API](effect-playback-storage.md).

| Check | Executed evidence | Result |
|---|---|---|
| Full source regressions | Inkscape Python `-m unittest discover -s tests -v` | PASS, **60 tests**, exit 0 |
| Synchronized visual rendering | Row-front tests: one changed row, all ten changing columns, phase endpoints and wrap, identical renderer for every delivery/storage choice | PASS: XMAS 01/02 are 104 snapshots at 20×26, no `.transport` field or storage-dependent simplification |
| Persistent commit | Fake transport asserts MANCPOK before SMVEW 2, 1 s/6 s settle calls, ATT response preference, no commit after failed transfer | PASS |
| Ownership | Competing write started after upload waits until persistent commit/settle releases the same lock | PASS; no buffer replacement can interleave locally between upload and save |
| Consent / compatibility / capacity | Store requires overwrite=True; both model and firmware must match verified profile; full wipe rejects before content writes | PASS: 104-frame / 162240-byte wipe exceeds native bounds rather than being coarsened |
| Generic arrays | `play_frames`, new temporary `play_animation`, and `store_animation` accept the same shape/color contract | PASS with fake transport and installed API inspection; temporary array play sends no save |
| SAVE-001 actual hardware | Old public upload API for XMAS 03, then known SMVEW 2 once after 1 s; wait 6 s, disconnect; owner performs actual power cycle | PASS for animation/startup restoration; FAIL for saved speed. Upload 6240 bytes / 65 chunks in 3.578 s, same known payload/header; user notes original app's speed behavior too |
| ISOLATE-001 actual hardware | Upload XMAS 04 without SMVEW 2, hold 12 s, disconnect; owner power-cycles | PASS: clean native red/white animation observed while powered, then saved XMAS 03 red/green resumes. Saved program was not replaced by ordinary buffered play |
| Runtime profile read | CLI `storage-capabilities`, no content writes | PASS: BLE STYPE26X20 + firmware TR2103R001-8, width20/height26, temporary and save support verified, startup speed retained=false |
| WIPE-001/002 actual hardware | CLI `run-effect XMAS 01 --repeat 1 --brightness 20`, two requested runs | Host exit 0 both. Repeat: 104 snapshots / 1550 W3 writes / 17.531 s including 9.046 s initial draw, 12 snapshot overruns. User confirmed visually synchronized top-to-bottom color fronts after initialization |
| CLI policies | Offline and mocked live tests for delivery choice, no playback overwrite flag, separate store/overwrite, speed warning and capacity rejection | PASS |
| Build/install | pip `wheel --no-build-isolation --no-deps --no-index --no-cache-dir --wheel-dir .analysis/independent-effects-final-dist .`; install to `.analysis/independent-effects-final-install` | PASS, exit 0; standard CPython isolated installed smoke confirms 0.6.0, 104-frame renderer and all three array APIs |
| Installed persistent preview | `main(['--dry-run','store-effect','XMAS 03','--width','20','--height','26'])` | PASS, four frames / 6240 bytes / 65 chunks, known payload hash and SMVEW 2 hex; no Bluetooth writes |
| Documentation / staging | Relative Markdown file-link check; `git diff --cached --check`; source/doc/component review | PASS; no broken relative file links, whitespace issues, new dependencies or vendor assets |

Final local wheel `py_magical_led-0.6.0-py3-none-any.whl`, SHA-256
`ddfb63b0681e369838c2d04723f80eaa5a5ae7d182fe8005b8c57b92d856e972`.
It remains an ignored validation artifact, not a published release.

Hardware experiments occurred during implementation. The save opcode, timing
sequence and payload were physically verified before the final API refactor;
the final store implementation is unit-tested (including ATT response preference)
and does not claim a fresh automated power cycle/readback. The final row renderer
matches the user-observed WIPE-002 path; later changes were API wrappers, guards,
comments/help and tests, not changed pixels. No additional permanent write was
performed merely to exercise a wrapper or rebuild a wheel.

**Limits/handoff:** live row writes are visually synchronized, not electrically
atomic or hard-real-time. Initial draw and soft timing are reported honestly.
Full-resolution 01/02 cannot be stored on the verified native format; user
explicitly rejected a coarse alternative. 03/04 fit. Saved animation survives
power loss, selected speed does not; the API/CLI warns accordingly. Unknown
profiles, undocumented storage slots and exact clock recovery remain unsupported.
No firmware update, factory reset, guessed opcode, push, tag or publication occurred.
