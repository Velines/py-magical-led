# Physical controller session · 2026-11-21 · in progress

Source candidate: `5ebf113` (no implementation changes during these checks).
Windows host, portable standard CPython 3.12.10, Bleak 1.1.1 and Windows
dependencies inventoried in `dependencies/third-party-components.md`.
Controller advertised as `MT-…`; full device address intentionally omitted.
Direct version read: `TR2103R001-8\0`. Initial LEDs off, supply connected.

## Observed GATT

Service FFF0 contains the expected vendor characteristics with suffixes:

| Suffix | Properties |
|---|---|
| 9600, 960a, 960b | write, write-without-response |
| 9601 | notify |
| 9602 | read |

Negotiated MTU 248; reported maximum write-without-response size 245.
The EFFE-0 experiment received ciphertext
`d07400453062999b945eb929f9a3b603`, decrypted to
`0a535459504532365832300000000000` (`STYPE26X20`). This is a model
identifier, not physical measurement of panel dimensions.

## Commands and human observations

| Test | Sent | Transport | Human observation / disposition |
|---|---|---|---|
| HW-001 | LEDON | completed | PASS: LEDs on, previous effect resumed |
| HW-002 | COLO for RGB (255,0,0) alone | completed | FAIL for persistent solid color: briefly red, then prior effect |
| HW-003 | Same COLO, connection held 20 s without other writes | completed | Same brief red; effect resumed before disconnect. Disconnect is not the trigger. |
| HW-004 | EFFE 0; wait 500 ms; COLO red; hold 10 s | completed | PASS: user confirmed steady red after experiment |
| HW-005 | COLO green alone; hold 10 s, disconnect | completed | User confirmed brief original effect, then steady green. Final green channel PASS; transition not effect-free. |
| HW-006 | LIGHT raw level 20 alone; hold 10 s, disconnect | completed | User reported LEDs off. FAIL for expected visibly dimmer green; power state vs imperceptible output not established. |
| HW-007 | LIGHT raw level 80 alone; hold 10 s, disconnect | completed | User saw original effect at lower brightness for about 3 s, then darkness. FAIL for independent steady-green brightness control. |
| HW-008 | LIGHT 80 → wait 500 ms → EFFE 0 → wait 500 ms → COLO green; hold 15 s | completed | PASS for this sequence: user confirmed stable, dimmer green. Subscribed notifications; received same STYPE26X20 block. |
| HW-009 | LIGHT 20 → wait 500 ms → EFFE 0 → wait 500 ms → COLO green; hold 15 s | completed | PASS: user confirmed LEDs on and dimmer than HW-008 (level 80) |
| HW-010 | EFFE 3 alone (app label Meteor); subscribe, hold 15 s | completed | PASS: user confirmed changed effect continuing after disconnect; same STYPE26X20 notification received. Exact visual pattern not described. |
| HW-011 | EFFE 4 alone (app label Chase); hold 15 s | completed | PASS: user confirmed different animation and continuing after disconnect |
| HW-012 | SPEED raw value 20 alone; hold 15 s | completed | User confirmed slower animation. Effect identity and independent persistence not separately confirmed. |
| HW-013 | SPEED raw value 80 alone; hold 15 s | completed | PASS: user confirmed faster than 20 and still Chase |
| HW-014 | LIGHT raw value 80 alone while Chase is running; hold 15 s | completed | PASS for final brighter Chase: user saw brief different effect, then return to Chase at higher brightness. FAIL for transition-free adjustment. |
| HW-015 | ANIM 1 alone; subscribe, hold 15 s | completed | PASS for preset selection: user confirmed a different animation, visual pattern unidentified. Received STYPE26X20 again, not a content listing or explicit ANIM acknowledgement. No upload/save/mode/effect commands sent. |
| HW-016 | ANIM 2 alone; hold 15 s | completed | PASS: user confirmed a different animation from ANIM 1; no upload/save/mode/effect commands sent |

**Finding:** on this firmware, the color frame changes RGB but does not by
itself suppress an already running effect. EFFE 0 followed by COLO produced
persistent red. Do not claim COLO alone always selects a static-color mode.
LIGHT-only tests did not preserve steady green: level 20 appeared off and
level 80 briefly showed a dimmer original effect before darkness. The cause
is unresolved; do not describe brightness as physically verified or infer
a percentage curve from these results. The combined sequence LIGHT → EFFE 0
→ COLO is confirmed for steady green at raw levels 80 and 20, with 20 visibly
dimmer. Both tests used 500 ms between commands and a 15 s connection hold;
minimum required delays have not been established. This validates the combined
sequence on this controller, not an independent LIGHT-only adjustment.

EFFE 3 and EFFE 4 both changed the animation and continued after disconnect.
User confirmed SPEED 20 slower and SPEED 80 faster, retaining Chase at 80.
LIGHT 80 alone while Chase was active briefly displayed a different effect,
then returned to brighter Chase. Thus LIGHT-only adjustment can settle correctly
for this running effect; do not generalize the static-color failure to all modes.
Transient changes during command handling remain unresolved. The 15 s holds
are observation windows, not measured settling times or required delays.

## Stored-content discovery boundary

The five named EFFE entries are app-side constants, not a directory read from
this controller. No stored-content enumeration/readback command has been
identified. IMAG/ANIM selectors alone do not establish which slots are populated.
No unknown command sweep or content uploads were attempted in this session.
Follow-up static inspection found hard-coded app catalogues of 25 images and
25 animations, and a local database query for DIY images. See
[stored-content investigation](stored-content.md). IMAG/ANIM playback on this
controller was initially untested; ANIM 1 has now produced a different animation
without an upload. ANIM 2 also produced a visibly different animation. This does not establish a
content-directory read or confirm all 25 app-listed presets.
Whether EFFE 0 persists across power removal, and whether the same behavior
applies to other firmware, is unverified. Library/CLI integration is implemented
in 0.2.0 using explicit high-level scene helpers and CLI options; see README for
the changed color behavior. The manual results used the earlier raw API, not
the new helpers. No firmware, timer, save or upload commands were sent.
