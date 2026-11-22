# Static interoperability increment · TASK-001

User source: analyze the supplied Magical LED 1.2.0 XAPK, specify BLE strip control precisely, provide a documented generic Python library and minimal CLI, local milestone commits, defer physical testing. Initial baseline: empty repository, `feat/protocol`. Platform-independent encoder and injected transport; Windows local offline validation. Linux/macOS radio behavior unverified.

| User criterion | Software/design refinement | Planned check |
|---|---|---|
| UR-001-AC1: reproduce app strip-control values; distinguish observations from unknowns | SWR-001-AC1, [spec](../protocol.md), [codec design](../architecture/README.md) | Compare power, brightness, asymmetric RGB against externally calculated AES vectors; reject malformed frames |
| UR-002-AC1: control one selected strip from CLI or preview offline | SWR-002-AC1 | Run CLI without BLE for preview; reject missing target; compare preview to control vector |
| UR-003-AC1: reuse library without CLI or physical strip | SWR-003-AC1 | Exercise injected GATT writer, write-mode selection, service and characteristic failures |

Hardware acceptance remains pending. No third-party review or release approval claimed.

Development baseline: `c7d8d4e`; owner accepted the single-session implementation plan on 2026-11-20, including deferred independent and physical review. Exception applies to this offline increment only; expires before release. Compensating evidence: separate .NET vectors, resource and native-table cross-checks, fake GATT assertions, install smoke test. Actual criterion links:

- UR-001-AC1 → SWR-001-AC1 → `magical_led.protocol.plaintext/color/brightness`, `_block.block` → `tests/test_protocol.py::ProtocolTests.test_external_vectors` (TEST-001); edge/chunk tests in same class.
- UR-002-AC1 → SWR-002-AC1 → `magical_led.cli.main` → `tests/test_cli.py::CliTests` (TEST-002), actual CLI process with `-S` and invalid target/argument cases.
- UR-003-AC1 → SWR-003-AC1 → `magical_led.client.Strip` → `tests/test_client.py::ClientTests` (TEST-003), selected characteristic, transport bytes, response flag, subscriptions and direct read.

See [executed checks and remaining gates](../verification.md). Criteria cover offline behavior only, not a physical PASS.

## Hardware integration · TASK-002 / 0.2.0

2026-11-21 user request: integrate the API/CLI capabilities and hardware findings
discussed in this session. Baseline `5ebf113`; code did not change during the
manual experiments. [Observed results](../hardware-session-2026-11-21.md) are
distinct from automated verification of the new convenience methods.

| Criterion | Refinement and implementation | Assertions |
|---|---|---|
| UR-004-AC1: expose tested static RGB/brightness ordering, retain raw API | SWR-004-AC1; `protocol.static_color/effect_scene`, `Strip.send_sequence/set_color/set_brightness/set_effect`, `cli.main` | `ClientTests.test_high_level_static_sequence`, `test_sequence_prevalidation_and_failure`, `test_sequence_cannot_interleave`; `CliTests.test_animation_and_static_brightness` |
| UR-004-AC2: select presets and list known catalogue honestly, expose version read | SWR-004-AC2; `catalogue.catalogue`, `protocol.animation/image/effect`, `Strip.select_animation/select_image/read_version`, `cli.main` | `ProtocolTests.test_catalogue_and_preset_validation`, `ClientTests.test_high_level_selectors/test_plain_version_read`, `CliTests.test_offline_catalogue_is_not_inventory/test_version_read_preview` |

No device inventory support is claimed: only the app catalogue and individually
observed IDs. No new dependency or service. New helper sequences and preset
commands receive fake-transport regression coverage; previously recorded visible
results apply to the individual manual experiments, not automatic acceptance
of every 0.2.0 path or of untested image/animation presets.

## Topology and custom live effects · TASK-003 / 0.3.0

User source: read grid dimensions through BLE, establish orientation using the
physical device, then accept multiple 2D arrays of colors for a custom effect.
Baseline `5902606`. Detailed source/marker and frame acceptance evidence is in
[topology/live-frame investigation](../topology-live-frames.md). Non-goals:
physical length sensing, unknown-opcode probes, stored-effect overwrite, uploads
and unverified high-rate/atomic display claims.

| Criterion | Software refinement / implementation | Verification |
|---|---|---|
| UR-005-AC1: expose controller-reported logical grid and distinguish physical mounting | SWR-005-AC1; `frames.parse_topology/Topology`, `Strip.read_topology`, CLI `topology` | TEST-006 `FrameTests.test_report_and_unknown_profiles`; `PlaybackTests.test_ble_topology_and_shared_subscriptions/test_timeout_unknown_and_partial_setup_cleanup`; TOPO-001..005 actual reports/markers |
| UR-005-AC2: multiple 2D RGB arrays produce a mapped live custom effect without saves | SWR-005-AC2; `FrameMapping`, `prepare_frames`, `Strip.play_frames`, CLI `play` | TEST-007 `FrameTests.test_normalization_copy_and_transforms/test_bad_pixels_shapes_and_limits`; TEST-008 `PlaybackTests.test_full_first_frame_deltas_and_loop_boundary/test_validation_before_lighting_changes`; CLI frame preview/dispatch tests; FRAME-002 explicit human confirmation |
| UR-005-AC3: bounded playback, honest performance, cancellation and ownership | SWR-005-AC3; `PlaybackResult`, `Strip.play_frames/_write_unlocked`, shared notifications | `PlaybackTests.test_pacing_does_not_catch_up_after_slow_frame/test_cancellation_releases_lock_without_save`; FRAME-001/002 measured counts/times; per-Strip lock and partial-state docs |

Human orientation observation: red origin at top-left; increasing coordinate 1
moves downward on the same string, increasing coordinate 2 moves to the next
string rightward. Endpoints and the live example were confirmed by the user.
Do not extend this acceptance to all known profiles or untested mounting flips.

## Pre-made live effects · TASK-004 / 0.4.0

Source: user requested a collection containing XMAS 01 (two red strings, two
green, repeating) and XMAS 02 (red/white), moving the picture forward one string
every two seconds. Baseline `673922c`. Assumption: forward means rightward with
cyclic wrapping in the calibrated front view; explicitly stated during work,
with a leftward option available. For 20 columns, one translated repeat swaps
five strings in each color direction, not just two changed strings total.

| Criterion | Refinement / implementation | Verification |
|---|---|---|
| UR-006-AC1: exact names, red/red/green/green or red/red/white/white, full-height strings, one-column cyclic translation | SWR-006-AC1; `effects.StripedEffect.frames`, `XMAS_01/XMAS_02`, `get_effect/list_effects` | TEST-009 `EffectTests`: all-row uniformity, actual colors, four phases, each rightward shift including loop boundary, left variant, partial bands and limits |
| UR-006-AC2: advance phases every two seconds; reusable API and CLI, no stored-content overwrite | SWR-006-AC2; `Strip.play_effect`, `play_frames`, `PlaybackResult`, CLI `effects/run-effect` | TEST-010 simulated schedule PASS; helper/CLI tests PASS. Follow-up physical live-path transition/timing FAIL: pattern without expected shifting, progressive repaint with gaps, slow acknowledged writes. See verification and buffered investigation. |

The software requests 2 s including write time and reports overruns, rather
than claiming this proves 2 s visible updates on BLE. The initial failed
discovery attempt did not change the display. Subsequent physical tests did
not meet the intended transition; no release-level acceptance of XMAS timing
is claimed. A buffered-animation candidate is blocked on the owner's decision
about possible custom-content overwrite; no transfer has been started. No
component/dependency additions or new on-wire commands were introduced.

0.4.1 source update: the user explicitly requested continuous repetition when
starting any animation in the new collection. `Strip.play_effect` and CLI
`run-effect` therefore default to continuous; positive repeat counts remain
available for tests. Regression assertions cover default helper dispatch,
continuation beyond the first cycle without reinitialization, CLI previews and
the bounded override. Generic frame playback defaults and physical transition
acceptance are unchanged. Continuous playback requires a live connection/process
and stops through task cancellation or CLI Ctrl+C; it is not controller storage.

## Buffered effects and storage investigation · TASK-005 / 0.5.0

Baseline `dd0d35a`. User requested device storage and XMAS 03/04 avoiding downward
redraw; clarified the **same paired-string patterns**, not whole-display solid
alternation. The user expressly authorized a bounded upload despite possible
loss of existing custom animation content. No firmware/reset scope was granted.

| Criterion | Refinement / implementation | Verification |
|---|---|---|
| UR-007-AC1: native 03/04 patterns preserve full-height paired colors while avoiding live redraw | SWR-007-AC1; `buffered.encode_animation`, `effects.XMAS_03/XMAS_04`, transport-aware `Strip.play_effect` | TEST-011 encoding assertions; collection frame/palette tests; user confirmed native XMAS 03 clean whole-string changes at about 2 s |
| UR-007-AC2: explicit consent, bounded acknowledged transfer and honest storage semantics | SWR-007-AC2; `upload_animation/upload_effect`, `AnimationUploadResult`, CLI guards and previews | TEST-012 permission-before-I/O, preflight, MANY/W2/MANCP/ACK order, errors, deadline/cancellation cleanup; CLI consent/preview/dispatch tests; actual 6240-byte / 65-chunk acknowledged upload |
| UR-007-AC3: distinguish autonomous playback from power-cycle persistence | SWR-007-AC2; native result fields and [storage contract](../buffered-animations.md) | User confirmed disconnect survival, then corrected actual power-cycle result: another effect resumed. Nonvolatile retention/reselect and multi-slot coexistence remain unknown; no permanent-storage acceptance claimed. |

Raw speed 10 is approximately calibrated only on TR2103R001-8 / STYPE26X20 by
human observation, not an exact general time conversion. Native XMAS 04 has
software coverage but no separate visual confirmation. Live 01/02 retain their
recorded transition failures; native success does not retroactively pass them.

## Independent transitions and persistent store · TASK-006 / 0.6.0

Baseline `99fcf4e`. User requested synchronized full-string top-to-bottom changes
in XMAS 01/02 and separation of visual effects from persistent storage/overwrite.
Material decisions: user selected **every LED row**, explicitly accepting that
the 104-frame cycle does not fit the verified native format, and authorized
single-image/animation replacement for a bounded SMVEW 2 save experiment plus
an unsaved-XMAS-04 isolation test. No firmware/reset scope.

| Criterion | Refinement / source | Verification |
|---|---|---|
| UR-008-AC1: all changing strings advance together row-by-row, full resolution | SWR-008-AC1; `StripedEffect.phase_frames/frames/frame_interval`, live player row snapshots | Renderer assertions cover all changed columns/one row, full phase boundaries and cycle wrap; actual WIPE-002 user-confirmed synchronization |
| UR-008-AC2: effect definition independent of playback delivery and storage | SWR-008-AC2; visual `transition`, explicit delivery, shared renderer, CLI run/store separation | No `.transport`; live/buffered/store dispatch tests; temporary XMAS 04 followed by actual power-cycle restoration of saved XMAS 03 |
| UR-008-AC3: explicit persistent store/overwrite with no silent simplification | SWR-008-AC3; profile capabilities, `store_effect/store_animation`, consent and capacity guards, locked commit | SAVE-001 actual startup resumption; fake-transport command ordering, no-save-after-failure, write-lock concurrency, unknown-profile and 104-frame no-write capacity tests |

SAVE-001 preserves animation/startup selection but **not speed**; the user notes
the original app has the same speed behavior. The API reports that limitation,
not an accepted persistent timing guarantee. ISOLATE-001 also visually confirmed
XMAS 04. Historical 01/02 live tests remain preserved; WIPE-002 verifies the new
explicit synchronized-wipe definition, not the former uncontrolled redraw.
