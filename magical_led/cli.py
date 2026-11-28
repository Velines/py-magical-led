"""CLI global options precede the subcommand. Dry-run never opens the radio."""
import argparse
import asyncio
from datetime import datetime
import os
import re
import shlex
import sys
import json
from pathlib import Path
from dataclasses import asdict

from . import brightness, clock, connect, encrypt, plaintext, power, scan
from . import animation, catalogue, effect_scene, image, static_color
from .protocol import VERSION_READ
from .frames import Topology, FrameMapping, prepare_frames
from .effects import get_effect, list_effects
from .buffered import encode_animation, AnimationUploadResult, PersistentStoreResult
from .state import Schedule, ScheduleRule, weekday_mask


def _octet(text):
    value = int(text)
    if not 0 <= value <= 255:
        raise argparse.ArgumentTypeError('expected integer 0..255')
    return value


def _rgb(text):
    if not re.fullmatch(r'#?[0-9a-fA-F]{6}', text):
        raise argparse.ArgumentTypeError('expected RRGGBB, e.g. 12abef')
    return bytes.fromhex(text.lstrip('#'))


def _positive(text):
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError('expected a positive integer')
    return value


def _finite(text):
    import math
    value = float(text)
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError('expected a finite positive number')
    return value


def _gap(text):
    import math
    value = float(text)
    if not math.isfinite(value) or value < 0:
        raise argparse.ArgumentTypeError('expected a finite nonnegative number')
    return value


def _hhmm(text):
    match = re.fullmatch(r'(\d{1,2}):(\d{2})', text.strip())
    if not match:
        raise argparse.ArgumentTypeError('expected HH:MM in 24-hour format')
    hour, minute = int(match.group(1)), int(match.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise argparse.ArgumentTypeError('expected HH:MM from 00:00 to 23:59')
    return (hour, minute)


def _days(text):
    try:
        return weekday_mask(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _iso_datetime(text):
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('expected ISO-8601 date/time, e.g. 2026-11-28T18:30:00') from exc


def _format_rule(label, rule):
    if not rule.enabled:
        return f'{label:<8}disabled ({rule.time}, days={",".join(rule.weekdays) or "none"})'
    return f'{label:<8}enabled  {rule.time} ({",".join(rule.weekdays) or "none"})'


def _format_state(state):
    lines = [
        f'firmware    {state.firmware or "unknown"}',
        f'ver         {f"spi={state.version_info.spi} ota={state.version_info.ota}" if state.version_info else "unknown"}',
        f'topology    {f"{state.topology.width}x{state.topology.height} ({state.topology.reported_type})" if state.topology else "unknown"}',
        f'power       {"unknown" if state.power is None else "on" if state.power else "off"}',
    ]
    if state.schedule is None:
        lines.append('schedule    unknown')
    else:
        lines.append('schedule    ' + _format_rule('on', state.schedule.on))
        lines.append('            ' + _format_rule('off', state.schedule.off))
    if state.errors:
        lines.append('errors      ' + '; '.join(state.errors))
    return '\n'.join(lines)


def _batch_step_parser():
    step = argparse.ArgumentParser(prog='batch', add_help=False)
    sub = step.add_subparsers(dest='cmd', required=True)
    for name in ('on', 'off'):
        sub.add_parser(name, add_help=False)
    rgb = sub.add_parser('color', add_help=False)
    rgb.add_argument('rgb', type=_rgb)
    rgb.add_argument('--brightness', type=_octet)
    light = sub.add_parser('brightness', add_help=False)
    light.add_argument('value', type=_octet)
    light.add_argument('--color', type=_rgb)
    fx = sub.add_parser('effect', add_help=False)
    fx.add_argument('value', type=int, choices=range(6))
    fx.add_argument('--brightness', type=_octet)
    fx.add_argument('--speed', type=_octet)
    for name in ('speed', 'mode'):
        sub.add_parser(name, add_help=False).add_argument('value', type=_octet)
    for name in ('animation', 'image'):
        sub.add_parser(name, add_help=False).add_argument('value', type=int, choices=range(1, 26))
    sync = sub.add_parser('sync-clock', add_help=False)
    sync.add_argument('--time', type=_iso_datetime)
    pause = sub.add_parser('sleep', add_help=False)
    pause.add_argument('seconds', type=_gap)
    return step


def _compile_batch(steps, default_delay):
    """Validate and compile all batch steps into ('frame', bytes) / ('sleep', seconds) ops."""
    step_parser = _batch_step_parser()
    ops = []
    for raw_step in steps:
        tokens = shlex.split(raw_step)
        if not tokens:
            raise ValueError('batch step must not be empty')
        try:
            parsed = step_parser.parse_args(tokens)
        except SystemExit as exc:
            raise ValueError(f'invalid batch step: {raw_step!r}') from exc
        if parsed.cmd == 'sleep':
            ops.append(('sleep', parsed.seconds))
            continue
        if parsed.cmd in ('on', 'off'):
            frames = (power(parsed.cmd == 'on'),)
        elif parsed.cmd == 'color':
            frames = static_color(*parsed.rgb, level=parsed.brightness)
        elif parsed.cmd == 'brightness':
            frames = (brightness(parsed.value),) if parsed.color is None else static_color(*parsed.color, level=parsed.value)
        elif parsed.cmd == 'effect':
            frames = effect_scene(parsed.value, level=parsed.brightness, speed=parsed.speed)
        elif parsed.cmd in ('animation', 'image'):
            frames = ((animation if parsed.cmd == 'animation' else image)(parsed.value),)
        elif parsed.cmd == 'sync-clock':
            frames = (clock(datetime.now() if parsed.time is None else parsed.time),)
        else:
            frames = (plaintext({'mode': 'MODE', 'speed': 'SPEED'}[parsed.cmd], parsed.value),)
        for frame in frames:
            if ops and ops[-1][0] == 'frame' and default_delay > 0:
                ops.append(('sleep', default_delay))
            ops.append(('frame', frame))
    return ops


def _playback_result(result):
    if isinstance(result, PersistentStoreResult):
        print(json.dumps({**asdict(result), 'persistent_save_command_written': True}, indent=2))
        if result.startup_speed_retained is False:
            print('Warning: this firmware restores the saved animation but not its selected speed after power loss.', file=sys.stderr)
        return
    if isinstance(result, AnimationUploadResult):
        print(json.dumps({**asdict(result), 'uploaded_to_controller': True, 'persistent_save_requested': False,
                          'host_streaming': False}, indent=2))
        return
    print(json.dumps({**asdict(result), 'effective_fps': result.effective_fps,
                      'saved_to_controller': False}, indent=2))
    if result.overrun_frames:
        print(f'Warning: {result.overrun_frames} frame(s) exceeded the requested interval '
              '(including initial draw); playback did not catch up by bursting.', file=sys.stderr)


def _format_effect_line(effect):
    if all(hasattr(effect, attr) for attr in ('colors', 'strips_per_band', 'step_seconds', 'transition')):
        colors = ', '.join('#' + ''.join(f'{c:02X}' for c in rgb) for rgb in effect.colors)
        return (f'{effect.name}\t{colors}\t{effect.strips_per_band} strips/color\t'
                f'{effect.step_seconds:g} s target/step\t{effect.transition}')
    parts = [effect.name]
    colors = getattr(effect, 'colors', None)
    if colors is None and hasattr(effect, 'base'):
        colors = getattr(effect.base, 'colors', None)
    if colors:
        parts.append(', '.join('#' + ''.join(f'{c:02X}' for c in rgb) for rgb in colors))
    description = getattr(effect, 'description', None)
    if description:
        parts.append(description)
    elif hasattr(effect, 'base'):
        parts.append(f'static ({effect.base.name})')
    step_seconds = getattr(effect, 'step_seconds', None)
    if step_seconds is not None:
        parts.append(f'{step_seconds:g} s target/step')
    transition = getattr(effect, 'transition', None)
    if transition is not None:
        parts.append(transition)
    parts.append(f'auto:{effect.resolve_delivery("auto")}')
    return '\t'.join(parts)


def _upload_preview(effect, topology, mapping, direction, wire_speed, *, persistent=False):
    import hashlib
    width, height = mapping.input_size(topology)
    transfer = encode_animation(effect.frames(Topology(width, height), direction=direction),
                                topology, mapping=mapping, wire_speed=wire_speed)
    return {'source': 'offline custom-animation upload plan; not connected',
            'name': effect.name, 'width': topology.width, 'height': topology.height,
            'frame_count': transfer.frame_count, 'bytes': len(transfer.payload),
            'chunks': len(transfer.chunks), 'assumed_chunk_payload_capacity': 96,
            'header_plain': transfer.header.hex(),
            'payload_sha256': hashlib.sha256(transfer.payload).hexdigest(),
            'wire_speed': wire_speed, 'persistent_save_requested': persistent,
            'save_command_hex': plaintext('SMVEW', 2).hex() if persistent else None,
            'persistent_overwrite_consent_required': persistent,
            'verified_profile_required': 'TR2103R001-8 / STYPE26X20',
            'startup_speed_retained_on_verified_profile': False}


def _load_frames(path):
    # Bounded document read; library callers may instead pass their own arrays.
    with Path(path).open('rb') as source:
        contents = source.read(4 * 1024 * 1024 + 1)
    if len(contents) > 4 * 1024 * 1024:
        raise ValueError('frame JSON exceeds the 4 MiB CLI limit')
    document = json.loads(contents)
    if not isinstance(document, dict) or set(document) != {'frames'}:
        raise ValueError('expected a JSON object with exactly one key: frames')
    if not isinstance(document['frames'], list) or not document['frames']:
        raise ValueError('frames must be a nonempty JSON list')
    return document['frames']


def main(argv=None):
    # trace: SWR-002-AC1
    parser = argparse.ArgumentParser(prog='magical-led', description=__doc__)
    target = parser.add_mutually_exclusive_group()
    target.add_argument('--device', metavar='ID', help='address or CoreBluetooth UUID (or set MAGICAL_LED_DEVICE)')
    target.add_argument('--dry-run', action='store_true', help='print plaintext and on-wire hex')
    parser.add_argument('--timeout', type=_finite, default=20, help='BLE discovery/connection timeout in seconds (default: 20)')
    sub = parser.add_subparsers(dest='cmd', required=True)
    scanner = sub.add_parser('scan', help='list devices with matching manufacturer data')
    scanner.add_argument('--json', action='store_true', help='machine-readable scan results')
    listing = sub.add_parser('presets', help='offline app catalogue, NOT device storage inventory')
    listing.add_argument('kind', nargs='?', default='all', choices=['all', 'effects', 'animations', 'images'])
    listing.add_argument('--json', action='store_true', help='machine-readable catalogue with observation provenance')
    library = sub.add_parser('effects', help='list library-made effects, separate from controller presets')
    library.add_argument('--json', action='store_true')
    runner = sub.add_parser('run-effect', help='play a named visual effect temporarily or persistently (--persist)')
    runner.add_argument('name', help='e.g. "XMAS 01"')
    repetitions = runner.add_mutually_exclusive_group()
    repetitions.add_argument('--repeat', type=_positive, default=None, help='stop after this many complete cycles (default: continuous)')
    repetitions.add_argument('--forever', action='store_true', help='stream until Ctrl+C (already the default)')
    runner.add_argument('--brightness', type=_octet)
    runner.add_argument('--direction', choices=['right', 'left'], default='right')
    runner.add_argument('--pixel-delay', type=_gap, default=0, help='extra seconds between pixel writes; default 0 targets two-second steps')
    runner.add_argument('--delivery', choices=['auto', 'live', 'buffered'], default='auto', help='playback delivery mode')
    runner.add_argument('--wire-speed', type=int, choices=range(1, 11), help='buffered effects only; raw controller speed, default 10')
    runner.add_argument('--persist', action='store_true', help='persist the effect to the controller custom slot (overwrites existing custom content)')
    runner.add_argument('--width', type=_positive, help='required for offline preview only')
    runner.add_argument('--height', type=_positive, help='required for offline preview only')
    for flag in ('flip-x', 'flip-y', 'transpose'):
        runner.add_argument('--' + flag, action='store_true')
    upload = sub.add_parser('upload-effect', help='upload a named effect to the active custom-animation buffer; may overwrite')
    upload.add_argument('name')
    upload.add_argument('--replace-buffer', '--allow-overwrite', dest='replace_buffer', action='store_true')
    upload.add_argument('--wire-speed', type=int, choices=range(1, 11), default=10)
    upload.add_argument('--brightness', type=_octet)
    upload.add_argument('--direction', choices=['right', 'left'], default='right')
    upload.add_argument('--width', type=_positive, help='offline preview only')
    upload.add_argument('--height', type=_positive, help='offline preview only')
    for flag in ('flip-x', 'flip-y', 'transpose'):
        upload.add_argument('--' + flag, action='store_true')
    store = sub.add_parser('store-effect', help='persist an effect in the custom location on a verified profile')
    store.add_argument('name')
    store.add_argument('--overwrite', action='store_true', help='required: no saved-content inventory/backup is available')
    store.add_argument('--wire-speed', type=int, choices=range(1, 11), default=10)
    store.add_argument('--brightness', type=_octet)
    store.add_argument('--direction', choices=['right', 'left'], default='right')
    store.add_argument('--width', type=_positive, help='offline preview only')
    store.add_argument('--height', type=_positive, help='offline preview only')
    for flag in ('flip-x', 'flip-y', 'transpose'):
        store.add_argument('--' + flag, action='store_true')
    sub.add_parser('storage-capabilities', help='read identity and report verified temporary/persistent support')
    ver = sub.add_parser('version', help='read raw firmware version from the selected device')
    ver.add_argument('--json', action='store_true', help='machine-readable version output')
    sub.add_parser('topology', help='listen for BLE grid report; mounting is not sensed')
    power_state = sub.add_parser('power-state', help='listen for LED power; print unknown if no report arrives')
    power_state.add_argument('--wait', type=_finite, default=5, help='notification deadline in seconds (default: 5)')
    power_state.add_argument('--json', action='store_true', help='machine-readable power output')
    status_cmd = sub.add_parser('status', help='read firmware, VER, topology, schedule and any power report in one connection')
    status_cmd.add_argument('--wait', type=_finite, default=3, help='per-query notification timeout in seconds (default: 3)')
    status_cmd.add_argument('--json', action='store_true', help='machine-readable status snapshot')
    sync_clk = sub.add_parser('sync-clock', help='sync controller wall clock (TIME); defaults to current local time')
    sync_clk.add_argument('--time', type=_iso_datetime, help='explicit ISO-8601 local date/time')
    sched_read = sub.add_parser('schedule', help='read configured weekly on/off schedule (STSC)')
    sched_read.add_argument('--wait', type=_finite, default=5, help='notification timeout in seconds (default: 5)')
    sched_read.add_argument('--json', action='store_true', help='machine-readable schedule output')
    sched_set = sub.add_parser('set-schedule', help='write weekly on/off schedule (SCHD)')
    sched_on = sched_set.add_mutually_exclusive_group()
    sched_on.add_argument('--on', type=_hhmm, metavar='HH:MM', help='enable scheduled power-on at HH:MM (24-hour)')
    sched_on.add_argument('--no-on', action='store_true', help='disable scheduled power-on (default)')
    sched_set.add_argument('--on-days', type=_days, help='weekdays for scheduled-on, e.g. mon,tue,wed or weekdays/daily')
    sched_off = sched_set.add_mutually_exclusive_group()
    sched_off.add_argument('--off', type=_hhmm, metavar='HH:MM', help='enable scheduled power-off at HH:MM (24-hour)')
    sched_off.add_argument('--no-off', action='store_true', help='disable scheduled power-off (default)')
    sched_set.add_argument('--off-days', type=_days, help='weekdays for scheduled-off, e.g. mon,tue,wed or weekdays/daily')
    sched_set.add_argument('--sync-clock', action='store_true', help='also send TIME before SCHD')
    batch_cmd = sub.add_parser('batch', help='run multiple control steps over one BLE connection')
    batch_cmd.add_argument('steps', nargs='+', metavar='STEP', help='quoted command steps, e.g. "on" "color ff8040" "sleep 2" "off"')
    batch_cmd.add_argument('--delay', type=_gap, default=0.5, help='gap between consecutive frames in seconds (default: 0.5)')
    playback = sub.add_parser('play', help='play JSON RGB frames live, buffered (--buffered), or persistent (--persist)')
    playback.add_argument('file', help='JSON object with a frames array')
    playback.add_argument('--fps', type=_finite, default=1, help='requested ceiling for live mode; BLE may be slower')
    playback.add_argument('--repeat', type=_positive, default=None, help='live mode cycle count (default: 1)')
    playback.add_argument('--buffered', action='store_true', help='upload as temporary controller-managed buffered animation')
    playback.add_argument('--persist', action='store_true', help='persist to controller custom slot (overwrites existing custom content)')
    playback.add_argument('--wire-speed', type=int, choices=range(1, 11), default=10, help='buffered/persist wire speed 1..10 (default: 10)')
    playback.add_argument('--brightness', type=_octet)
    playback.add_argument('--flip-x', action='store_true')
    playback.add_argument('--flip-y', action='store_true')
    playback.add_argument('--transpose', action='store_true')
    for name in ('on', 'off'):
        sub.add_parser(name)
    rgb = sub.add_parser('color', help='disable effect, then set solid RGB')
    rgb.add_argument('rgb', type=_rgb)
    rgb.add_argument('--brightness', type=_octet, help='set brightness before applying static RGB')
    light = sub.add_parser('brightness', help='raw LIGHT; supply --color to preserve static RGB')
    light.add_argument('value', type=_octet)
    light.add_argument('--color', type=_rgb, help='reapply this RGB using LIGHT, EFFE 0, COLO')
    fx = sub.add_parser('effect', help='select app effect 1..5, or 0 to disable')
    fx.add_argument('value', type=int, choices=range(6))
    fx.add_argument('--brightness', type=_octet)
    fx.add_argument('--speed', type=_octet)
    for name in ('speed', 'mode'):
        sub.add_parser(name).add_argument('value', type=_octet)
    for name in ('animation', 'image'):
        sub.add_parser(name, help=f'select app-listed {name} preset; no upload').add_argument('value', type=int, choices=range(1, 26))
    args = parser.parse_args(argv)
    if args.cmd not in ('scan', 'presets', 'effects') and not args.device and not args.dry_run:
        env_device = os.environ.get('MAGICAL_LED_DEVICE', '').strip()
        if env_device:
            args.device = env_device
    if args.cmd in ('scan', 'presets', 'effects') and (args.device or args.dry_run):
        parser.error(f'{args.cmd} does not take a device or --dry-run')
    if args.cmd not in ('scan', 'presets', 'effects') and not (args.device or args.dry_run):
        parser.error('specify --device ID (or MAGICAL_LED_DEVICE) or --dry-run before the command')
    if args.cmd in ('run-effect', 'upload-effect', 'store-effect'):
        if args.dry_run and (args.width is None or args.height is None):
            parser.error(f'{args.cmd} offline preview requires --width and --height')
        if not args.dry_run and (args.width is not None or args.height is not None):
            parser.error(f'live {args.cmd} reads dimensions from BLE; --width/--height are offline only')

    async def run():
        if args.cmd == 'effects':
            if args.json:
                print(json.dumps({'source': 'local library effects, not controller presets',
                                  'effects': [asdict(effect) for effect in list_effects()]}, indent=2))
            else:
                print('LIBRARY EFFECTS — visual definitions; playback and storage are separate')
                for effect in list_effects():
                    print(_format_effect_line(effect))
            return
        if args.cmd == 'run-effect':
            effect = get_effect(args.name)
            repeat = None if args.forever else args.repeat
            mapping = FrameMapping(transpose=args.transpose, flip_x=args.flip_x, flip_y=args.flip_y)
            selected = effect.resolve_delivery(args.delivery)
            if args.persist:
                if args.delivery == 'live':
                    raise ValueError('--persist requires buffered delivery')
                selected = 'buffered'
            if selected == 'buffered':
                if repeat is not None or args.pixel_delay != 0 or args.forever:
                    raise ValueError('buffered playback is autonomous; omit repeat/forever/pixel-delay options')
                if args.dry_run:
                    print(json.dumps(_upload_preview(effect, Topology(args.width, args.height), mapping,
                                                     args.direction, args.wire_speed or 10,
                                                     persistent=args.persist), indent=2))
                else:
                    async with connect(args.device, timeout=args.timeout) as strip:
                        result = await strip.play_effect(effect.name, mapping=mapping, direction=args.direction,
                                                         brightness=args.brightness, delivery='buffered',
                                                         wire_speed=args.wire_speed or 10,
                                                         persist=args.persist)
                        _playback_result(result)
                return
            if args.wire_speed is not None:
                raise ValueError('--wire-speed is only applicable to buffered playback')
            if args.dry_run:
                topology = Topology(args.width, args.height)
                width, height = mapping.input_size(topology)
                frames = effect.frames(Topology(width, height), direction=args.direction)
                prepared = prepare_frames(frames, topology, mapping)
                within = sum(sum(a != b for a, b in zip(previous, current))
                             for previous, current in zip(prepared, prepared[1:]))
                boundary = sum(a != b for a, b in zip(prepared[-1], prepared[0]))
                print(json.dumps({'source': 'library effect; offline caller-supplied dimensions',
                                  'name': effect.name, 'width': topology.width, 'height': topology.height,
                                  'step_seconds': getattr(effect, 'step_seconds', None), 'direction': args.direction,
                                  'transition': getattr(effect, 'transition', type(effect).__name__), 'delivery': selected,
                                  'frame_interval_seconds': effect.frame_interval(Topology(width, height)),
                                  'cycle_frames': len(frames), 'continuous': repeat is None,
                                  'frames': None if repeat is None else len(frames) * repeat,
                                  'pixel_writes': None if repeat is None else topology.pixel_count + within * repeat + boundary * (repeat - 1),
                                  'pixel_delay_seconds': args.pixel_delay,
                                  'timing': 'target only; progressive BLE writes may overrun',
                                  'saved_to_controller': False}, indent=2))
            else:
                if repeat is None:
                    print(f'Streaming {effect.name}; press Ctrl+C to stop (no save).', file=sys.stderr)
                async with connect(args.device, timeout=args.timeout) as strip:
                    result = await strip.play_effect(effect.name, mapping=mapping, direction=args.direction,
                                                      repeat=repeat, brightness=args.brightness,
                                                      pixel_delay=args.pixel_delay, delivery='live')
                    _playback_result(result)
            return
        if args.cmd == 'upload-effect':
            effect = get_effect(args.name)
            mapping = FrameMapping(transpose=args.transpose, flip_x=args.flip_x, flip_y=args.flip_y)
            if args.dry_run:
                print(json.dumps(_upload_preview(effect, Topology(args.width, args.height), mapping,
                                                 args.direction, args.wire_speed), indent=2))
            else:
                if not args.replace_buffer:
                    raise PermissionError('advanced upload may replace custom content; pass --replace-buffer')
                async with connect(args.device, timeout=args.timeout) as strip:
                    result = await strip.upload_effect(effect.name, mapping=mapping, direction=args.direction,
                                                       brightness=args.brightness, allow_overwrite=True,
                                                       wire_speed=args.wire_speed)
                    _playback_result(result)
            return
        if args.cmd == 'store-effect':
            effect = get_effect(args.name)
            mapping = FrameMapping(transpose=args.transpose, flip_x=args.flip_x, flip_y=args.flip_y)
            if args.dry_run:
                print(json.dumps(_upload_preview(effect, Topology(args.width, args.height), mapping,
                                                 args.direction, args.wire_speed, persistent=True), indent=2))
            else:
                if not args.overwrite:
                    raise PermissionError('saved custom content cannot be inventoried; pass --overwrite to permit replacement')
                async with connect(args.device, timeout=args.timeout) as strip:
                    result = await strip.store_effect(effect.name, overwrite=True, mapping=mapping,
                                                       direction=args.direction, wire_speed=args.wire_speed,
                                                       brightness=args.brightness)
                    _playback_result(result)
            return
        if args.cmd == 'storage-capabilities':
            if args.dry_run:
                print('read STYPE and firmware version; report known-profile capabilities; no content writes')
            else:
                async with connect(args.device, timeout=args.timeout) as strip:
                    print(json.dumps(asdict(await strip.read_storage_capabilities()), indent=2))
            return
        if args.cmd == 'presets':
            entries = catalogue(args.kind)
            if args.json:
                print(json.dumps({'source': 'Magical LED Android 1.2.0 app catalogue',
                                  'device_inventory': False,
                                  'presets': [asdict(p) for p in entries]}, indent=2))
            else:
                print('APP CATALOGUE — not a device storage listing')
                for p in entries:
                    status = f'observed: {p.observed_on}' if p.observed_on else 'hardware unverified'
                    print(f'{p.kind}\t{p.id}\t{p.name}\t{status}')
            return
        if args.cmd == 'topology':
            if args.dry_run:
                print('listen for STYPE via FFF0 notify/indicate; no lighting/query writes')
            else:
                async with connect(args.device, timeout=args.timeout) as strip:
                    topology = await strip.read_topology()
                    print(json.dumps({**asdict(topology), 'pixel_count': topology.pixel_count,
                                      'source': 'BLE STYPE + app grid profile',
                                      'mounting_orientation_from_ble': False}, indent=2))
            return
        if args.cmd == 'power-state':
            if args.dry_run:
                print(f'listen for LED power via FFF0 notify/indicate for up to {args.wait:g} seconds; no lighting/query writes')
            else:
                async with connect(args.device, timeout=args.timeout) as strip:
                    state = await strip.read_power(timeout=args.wait)
                    label = 'unknown' if state is None else 'on' if state else 'off'
                    if args.json:
                        print(json.dumps({'power': state, 'status': label, 'wait_seconds': args.wait}, indent=2))
                    else:
                        print(label)
            return
        if args.cmd == 'status':
            if args.dry_run:
                ver_frame = plaintext('VER')
                stsc_frame = plaintext('STSC')
                print(f'read  {VERSION_READ} (raw firmware version)')
                print(f'plain {ver_frame.hex()}\nwire  {encrypt(ver_frame).hex()}')
                print(f'plain {stsc_frame.hex()}\nwire  {encrypt(stsc_frame).hex()}')
                print(f'listen for STYPE, VER, STSC and any LEDON/LEDOFF for up to {args.wait:g}s each; no lighting writes')
            else:
                async with connect(args.device, timeout=args.timeout) as strip:
                    state = await strip.read_state(timeout=args.wait)
                    if args.json:
                        print(json.dumps(state.to_dict(), indent=2))
                    else:
                        print(_format_state(state))
            return
        if args.cmd == 'schedule':
            if args.dry_run:
                frame = plaintext('STSC')
                print(f'plain {frame.hex()}\nwire  {encrypt(frame).hex()}')
                print(f'listen for STSC reply for up to {args.wait:g}s')
            else:
                async with connect(args.device, timeout=args.timeout) as strip:
                    sched = await strip.read_schedule(timeout=args.wait)
                    if args.json:
                        print(json.dumps(sched.to_dict(), indent=2))
                    else:
                        print(_format_rule('on', sched.on))
                        print(_format_rule('off', sched.off))
            return
        if args.cmd == 'set-schedule':
            on_rule = (ScheduleRule(True, 0x7F if args.on_days is None else args.on_days, *args.on)
                       if args.on is not None else ScheduleRule())
            off_rule = (ScheduleRule(True, 0x7F if args.off_days is None else args.off_days, *args.off)
                        if args.off is not None else ScheduleRule())
            sched = Schedule(on=on_rule, off=off_rule)
            frames = ((clock(datetime.now()),) if args.sync_clock else ()) + (sched.to_frame(),)
            if args.dry_run:
                for i, frame in enumerate(frames):
                    if i:
                        print('wait  0.5 seconds')
                    print(f'plain {frame.hex()}\nwire  {encrypt(frame).hex()}')
            else:
                async with connect(args.device, timeout=args.timeout) as strip:
                    await strip.set_schedule(sched, sync_clock=args.sync_clock)
            return
        if args.cmd == 'sync-clock':
            frame = clock(datetime.now() if args.time is None else args.time)
            if args.dry_run:
                print(f'plain {frame.hex()}\nwire  {encrypt(frame).hex()}')
            else:
                async with connect(args.device, timeout=args.timeout) as strip:
                    await strip.send(frame)
            return
        if args.cmd == 'batch':
            ops = _compile_batch(args.steps, args.delay)
            if args.dry_run:
                for kind, value in ops:
                    if kind == 'sleep':
                        print(f'wait  {value:g} seconds')
                    else:
                        print(f'plain {value.hex()}\nwire  {encrypt(value).hex()}')
            else:
                async with connect(args.device, timeout=args.timeout) as strip:
                    for kind, value in ops:
                        if kind == 'sleep':
                            await asyncio.sleep(value)
                        else:
                            await strip.send(value)
            return
        if args.cmd == 'play':
            frames = _load_frames(args.file)
            mapping = FrameMapping(transpose=args.transpose, flip_x=args.flip_x, flip_y=args.flip_y)
            use_buffered = args.buffered or args.persist
            if use_buffered:
                if args.repeat is not None:
                    raise ValueError('buffered playback is autonomous; omit --repeat')
                if args.dry_run:
                    import hashlib
                    h, w = len(frames[0]), len(frames[0][0]) if len(frames[0]) else 0
                    topology = Topology(h, w) if args.transpose else Topology(w, h)
                    transfer = encode_animation(frames, topology, mapping=mapping, wire_speed=args.wire_speed)
                    print(json.dumps({
                        'source': 'offline custom-animation upload plan; not connected',
                        'width': topology.width, 'height': topology.height,
                        'frame_count': transfer.frame_count, 'bytes': len(transfer.payload),
                        'chunks': len(transfer.chunks), 'assumed_chunk_payload_capacity': 96,
                        'header_plain': transfer.header.hex(),
                        'payload_sha256': hashlib.sha256(transfer.payload).hexdigest(),
                        'wire_speed': args.wire_speed, 'persistent_save_requested': args.persist,
                        'save_command_hex': plaintext('SMVEW', 2).hex() if args.persist else None,
                    }, indent=2))
                else:
                    async with connect(args.device, timeout=args.timeout) as strip:
                        if args.persist:
                            result = await strip.store_animation(
                                frames, overwrite=True, mapping=mapping,
                                wire_speed=args.wire_speed, brightness=args.brightness,
                            )
                        else:
                            result = await strip.play_animation(
                                frames, mapping=mapping,
                                wire_speed=args.wire_speed, brightness=args.brightness,
                            )
                        _playback_result(result)
                return
            repeat = 1 if args.repeat is None else args.repeat
            if args.dry_run:
                # Offline dimensions come from input, never a fake device report.
                h, w = len(frames[0]), len(frames[0][0]) if len(frames[0]) else 0
                topology = Topology(h, w) if args.transpose else Topology(w, h)
                prepared = prepare_frames(frames, topology, mapping)
                within = sum(sum(a != b for a, b in zip(previous, current))
                             for previous, current in zip(prepared, prepared[1:]))
                boundary = sum(a != b for a, b in zip(prepared[-1], prepared[0]))
                writes = topology.pixel_count + within * repeat + boundary * (repeat - 1)
                print(json.dumps({'source': 'offline input dimensions; NOT read from device',
                                  'width': topology.width, 'height': topology.height,
                                  'frames': len(prepared) * repeat, 'pixel_writes': writes,
                                  'requested_fps': args.fps, 'pixel_delay_seconds': 0,
                                  'saved_to_controller': False}, indent=2))
            else:
                async with connect(args.device, timeout=args.timeout) as strip:
                    result = await strip.play_frames(frames, mapping=mapping, fps=args.fps,
                                                     repeat=repeat, brightness=args.brightness)
                    _playback_result(result)
            return
        if args.cmd == 'scan':
            devices = await scan()
            if args.json:
                print(json.dumps([{'address': d.address, 'name': d.name} for d in devices], indent=2))
            else:
                for d in devices:
                    print(f'{d.address}\t{d.name or "(unnamed)"}')
                if not devices:
                    print('No matching advertisements found.', file=sys.stderr)
            return
        if args.cmd == 'version':
            if args.dry_run:
                print(f'read  {VERSION_READ} (raw version bytes, no W1 write)')
            else:
                async with connect(args.device, timeout=args.timeout) as strip:
                    raw = await strip.read_version()
                    text = raw.rstrip(bytes(1)).decode('ascii', errors='backslashreplace')
                    if args.json:
                        print(json.dumps({'raw_hex': raw.hex(), 'text': text}, indent=2))
                    else:
                        print(f'raw   {raw.hex()}\ntext  {text}')
            return
        if args.cmd in ('on', 'off'):
            frames = (power(args.cmd == 'on'),)
        elif args.cmd == 'color':
            frames = static_color(*args.rgb, level=args.brightness)
        elif args.cmd == 'brightness':
            frames = ((brightness(args.value),) if args.color is None
                      else static_color(*args.color, level=args.value))
            if args.color is None:
                print('Note: raw brightness may disturb static color; use --color RRGGBB to reapply it.', file=sys.stderr)
        elif args.cmd == 'effect':
            frames = effect_scene(args.value, level=args.brightness, speed=args.speed)
        elif args.cmd in ('animation', 'image'):
            frames = ((animation if args.cmd == 'animation' else image)(args.value),)
        else:
            frames = (plaintext({'mode': 'MODE', 'speed': 'SPEED'}[args.cmd], args.value),)
        if args.dry_run:
            for i, frame in enumerate(frames):
                if i:
                    print('wait  0.5 seconds')
                print(f'plain {frame.hex()}\nwire  {encrypt(frame).hex()}')
        else:
            async with connect(args.device, timeout=args.timeout) as strip:
                await strip.send_sequence(frames)

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f'magical-led: {exc}', file=sys.stderr)
        return 1
    return 0
