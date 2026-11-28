---
name: Create Effect
description: Generate a new LED effect from a natural-language description, add it to the py-magical-led library catalogue, validate it offline, and add unit tests.
---

# Create a New Magical LED Effect

Use this skill when the user describes a desired LED pattern or animation in natural language and wants it implemented and added to the `py-magical-led` library effect catalogue (`magical_led.list_effects()` / `magical_led.get_effect()`).

## Workflow

1. **Read the effect contract and current catalogue**
   - Read `references/effect-contract.md` (relative to this skill directory).
   - Read `magical_led/effects.py` and `magical_led/__init__.py` to see existing effect classes, naming conventions, and registered entries.

2. **Interpret the user's description**
   - Identify:
     - **Catalogue name** (human-readable, e.g. `"Rainbow Wave"`) and **Python constant name** (`UPPER_SNAKE_CASE`, e.g. `RAINBOW_WAVE`). If the user did not supply a name, choose a concise descriptive one.
     - **Visual pattern & colors**: RGB tuples `(r, g, b)` with integers `0..255`. Remember global brightness is controlled separately on the strip, so use full-range RGB values unless dimmer pixels are part of the visual design (e.g. fading trails or `(0, 0, 0)` off pixels).
     - **Animation & looping**: static (1 frame) vs. animated (cyclic sequence where the last frame transitions cleanly back to frame 0). Support `direction` (`'right'` and `'left'`).
     - **Timing & delivery**:
       - On the verified `STYPE26X20` (`20×26`) controller, autonomous buffered playback (`play_animation` / `store_animation`) fits at most **15 frames** (24,576 bytes with 96-byte chunks).
       - If the effect naturally renders `<= 15` frames on `20×26`, `resolve_delivery('auto')` should return `'buffered'`.
       - If the effect needs `> 15` frames on `20×26` (e.g. smooth multi-row animations, slow fades, rain/snowfall), `resolve_delivery('auto')` should return `'live'`.
       - Never alter `frames()` based on delivery mode or storage; `frames()` must return the exact same visual sequence for live playback, buffered playback, and persistent storage.
   - Only ask clarifying questions if a key visual requirement is genuinely ambiguous; otherwise pick sensible defaults and state them clearly in the summary.

3. **Implement the effect in `magical_led/effects.py`**
   - **Prefer existing classes when they fit:**
     - `StripedEffect` for repeating vertical color bands with `'cut'` or `'wipe_down'` transitions.
     - `StaticEffect` for a single static frame of a `StripedEffect`.
   - **Otherwise, add a new `@dataclass(frozen=True)` class** in `magical_led/effects.py` following `references/effect-contract.md`:
     - Pure Python standard library only (no NumPy or external dependencies).
     - Validate all fields in `__post_init__` (reject `bool` where `int`/`float` is expected, check finite positive intervals, valid RGB channels `0..255`, nonempty `name`).
     - Keep all dataclass fields JSON-serializable (no callables/lambdas on the dataclass) so `magical-led effects --json` works.
     - Derive all coordinates from `topology.width` and `topology.height` — never hard-code `20×26`.
     - Return immutable nested tuples `frames[step][y][x]`, where `y` is `0..height-1` (top to bottom) and `x` is `0..width-1` (left to right).
     - Use a local `random.Random(self.seed)` if randomness is needed so `frames()` is deterministic.
     - Enforce `MAX_FRAMES` (256) and `MAX_TOTAL_PIXELS` (1,000,000) before building oversized output.
     - Implement `frames(self, topology: Topology, *, direction: str = 'right')`, `frame_interval(self, topology: Topology) -> float`, and `resolve_delivery(self, delivery: str = 'auto') -> str`.
   - Define the module-level constant and append it to `_EFFECTS` (ensuring no duplicate normalized names).

4. **Export from `magical_led/__init__.py`**
   - Import the new constant (and any new effect class) in `magical_led/__init__.py` and add them to `__all__`.

5. **Validate and preview offline**
   - Run the bundled validation script from the repository root:
     ```sh
     python3 .agents/skills/create-effect/scripts/validate_effect.py "<Effect Name>"
     ```
   - Also check the CLI offline commands:
     ```sh
     python3 -m magical_led effects
     python3 -m magical_led effects --json
     python3 -m magical_led --dry-run run-effect "<Effect Name>" --width 20 --height 26
     ```
   - Verify that buffered-targeted effects encode cleanly on `20×26` and that live-targeted effects validate cleanly with `prepare_frames`.

6. **Add unit tests in `tests/test_effects.py`**
   - Update `test_collection_names_colors_and_immutability` (or add a dedicated test method) covering:
     - Catalogue registration (`list_effects()`, `get_effect()` case/whitespace lookup) and frozen immutability.
     - Frame count, dimensions on `Topology(20, 26)` and small/odd grids (e.g. `Topology(1, 1)`, `Topology(5, 3)`).
     - Key visual properties of the effect (colors, symmetry/motion, `direction='left'` vs `'right'`, determinism).
     - `frame_interval(topology)` and `resolve_delivery('auto' | 'live' | 'buffered')`.
     - Validation of invalid parameters (if a new effect class was added).
   - Run `python3 -m unittest tests.test_effects -v` and verify all tests pass.

7. **Report back concisely**
   - Summarize the added effect name, constant, class, frame count on `20×26`, default delivery mode (`buffered` vs `live`), whether it fits in the controller's persistent storage slot, and the verification/test results.
   - Note that if the user also uses `ha-magical-led`, its `LIBRARY_EFFECTS` list in `custom_components/magical_led/const.py` is separate from `py-magical-led` and can be updated if they want the new effect in Home Assistant's Effect select entity.
