#!/usr/bin/env python3
"""Offline validator and ANSI terminal preview for py-magical-led effects."""
import argparse
import json
import math
import sys
from dataclasses import FrozenInstanceError, asdict, is_dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from magical_led import Topology, encode_animation, get_effect, list_effects, prepare_frames


def _preview_frame(frame, max_rows: int = 26) -> str:
    lines = []
    for row in frame[:max_rows]:
        cells = [f'\x1b[48;2;{r};{g};{b}m  \x1b[0m' for r, g, b in row]
        lines.append(''.join(cells))
    return '\n'.join(lines)


def validate(name: str, preview_frames: int = 1) -> int:
    effect = get_effect(name)
    effects = list_effects()
    if effect not in effects:
        raise AssertionError(f'{effect.name!r} is not in list_effects()')

    normalized = [' '.join(e.name.split()).casefold() for e in effects]
    if len(normalized) != len(set(normalized)):
        raise AssertionError('duplicate normalized effect names in list_effects()')

    if not is_dataclass(effect):
        raise AssertionError(f'{type(effect).__name__} must be a frozen dataclass')
    try:
        effect.name = 'mutated'
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError(f'{type(effect).__name__} is not frozen')

    json.dumps(asdict(effect))

    auto_delivery = effect.resolve_delivery('auto')
    if auto_delivery not in ('live', 'buffered'):
        raise AssertionError(f'unexpected auto delivery: {auto_delivery!r}')
    if effect.resolve_delivery('live') != 'live' or effect.resolve_delivery('buffered') != 'buffered':
        raise AssertionError('explicit delivery modes must pass through unchanged')

    primary = Topology(20, 26, 'STYPE26X20')
    edge_topologies = (
        primary,
        Topology(1, 1),
        Topology(2, 2),
        Topology(5, 3),
        Topology(25, 20, 'STYPE20X25'),
    )

    for topo in edge_topologies:
        interval = effect.frame_interval(topo)
        if not math.isfinite(interval) or interval <= 0 or not math.isfinite(1 / interval):
            raise AssertionError(f'invalid frame_interval({topo}): {interval!r}')
        for direction in ('right', 'left'):
            rendered = effect.frames(topo, direction=direction)
            if not isinstance(rendered, tuple):
                raise AssertionError(f'frames() must return an immutable tuple, got {type(rendered).__name__}')
            if rendered != effect.frames(topo, direction=direction):
                raise AssertionError(f'frames() is not deterministic for {topo}, direction={direction}')
            prepare_frames(rendered, topo)

    frames_20x26 = effect.frames(primary, direction='right')
    interval_20x26 = effect.frame_interval(primary)
    try:
        transfer = encode_animation(frames_20x26, primary, wire_speed=10)
        buffered_info = (
            f'fits ({transfer.frame_count} frames, {len(transfer.payload)} bytes, '
            f'{len(transfer.chunks)} chunks)'
        )
    except ValueError as exc:
        buffered_info = f'live-only ({exc})'

    print(f'OK: {effect.name} ({type(effect).__name__})')
    print(f'  20x26 frames:   {len(frames_20x26)}')
    print(f'  frame interval: {interval_20x26:g} s ({1 / interval_20x26:g} fps)')
    print(f'  auto delivery:  {auto_delivery}')
    print(f'  buffered 20x26: {buffered_info}')

    if preview_frames > 0:
        count = min(preview_frames, len(frames_20x26))
        for idx in range(count):
            print(f'\n--- Frame {idx}/{len(frames_20x26) - 1} (20x26) ---')
            print(_preview_frame(frames_20x26[idx]))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('name', help='Effect name in magical_led catalogue')
    parser.add_argument('--preview', type=int, default=1, help='Number of 20x26 frames to preview (0 to disable)')
    args = parser.parse_args(argv)
    try:
        return validate(args.name, preview_frames=args.preview)
    except Exception as exc:
        print(f'VALIDATION FAILED: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
