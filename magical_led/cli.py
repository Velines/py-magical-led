"""CLI global options precede the subcommand. Dry-run never opens the radio."""
import argparse
import asyncio
import re
import sys
import json
from pathlib import Path
from dataclasses import asdict

from . import brightness, connect, encrypt, plaintext, power, scan
from . import animation, catalogue, effect_scene, image, static_color
from .protocol import VERSION_READ
from .frames import Topology, FrameMapping, prepare_frames
from .effects import get_effect, list_effects
from .buffered import encode_animation, AnimationUploadResult, PersistentStoreResult


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
    target.add_argument('--device', metavar='ID', help='address or CoreBluetooth UUID')
    target.add_argument('--dry-run', action='store_true', help='print plaintext and on-wire hex')
    parser.add_argument('--timeout', type=_finite, default=20, help='BLE discovery/connection timeout in seconds (default: 20)')
    sub = parser.add_subparsers(dest='cmd', required=True)
    sub.add_parser('scan', help='list devices with matching manufacturer data')
    listing = sub.add_parser('presets', help='offline app catalogue, NOT device storage inventory')
    listing.add_argument('kind', nargs='?', default='all', choices=['all', 'effects', 'animations', 'images'])
    listing.add_argument('--json', action='store_true', help='machine-readable catalogue with observation provenance')
    library = sub.add_parser('effects', help='list library-made effects, separate from controller presets')
    library.add_argument('--json', action='store_true')
    runner = sub.add_parser('run-effect', help='play a named visual effect without persistent storage')
    runner.add_argument('name', help='e.g. "XMAS 01"')
    repetitions = runner.add_mutually_exclusive_group()
    repetitions.add_argument('--repeat', type=_positive, default=None, help='stop after this many complete cycles (default: continuous)')
    repetitions.add_argument('--forever', action='store_true', help='stream until Ctrl+C (already the default)')
    runner.add_argument('--brightness', type=_octet)
    runner.add_argument('--direction', choices=['right', 'left'], default='right')
    runner.add_argument('--pixel-delay', type=_gap, default=0, help='extra seconds between pixel writes; default 0 targets two-second steps')
    runner.add_argument('--delivery', choices=['auto', 'live', 'buffered'], default='auto', help='playback delivery only; never a persistent save')
    runner.add_argument('--wire-speed', type=int, choices=range(1, 11), help='buffered effects only; raw controller speed, default 10')
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
    sub.add_parser('version', help='read raw firmware version from the selected device')
    sub.add_parser('topology', help='listen for BLE grid report; mounting is not sensed')
    playback = sub.add_parser('play', help='play JSON RGB frames live; no upload or save')
    playback.add_argument('file', help='JSON object with a frames array')
    playback.add_argument('--fps', type=_finite, default=1, help='requested ceiling; BLE may be slower')
    playback.add_argument('--repeat', type=_positive, default=1)
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
    if args.cmd in ('scan', 'presets', 'effects') and (args.device or args.dry_run):
        parser.error(f'{args.cmd} does not take a device or --dry-run')
    if args.cmd not in ('scan', 'presets', 'effects') and not (args.device or args.dry_run):
        parser.error('specify --device ID or --dry-run before the command')
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
                    colors = ', '.join('#' + ''.join(f'{c:02X}' for c in rgb) for rgb in effect.colors)
                    print(f'{effect.name}\t{colors}\t{effect.strips_per_band} strips/color\t{effect.step_seconds:g} s target/step\t{effect.transition}')
            return
        if args.cmd == 'run-effect':
            effect = get_effect(args.name)
            repeat = None if args.forever else args.repeat
            mapping = FrameMapping(transpose=args.transpose, flip_x=args.flip_x, flip_y=args.flip_y)
            selected = effect.resolve_delivery(args.delivery)
            if selected == 'buffered':
                if repeat is not None or args.pixel_delay != 0 or args.forever:
                    raise ValueError('buffered playback is autonomous; omit repeat/forever/pixel-delay options')
                if args.dry_run:
                    print(json.dumps(_upload_preview(effect, Topology(args.width, args.height), mapping,
                                                     args.direction, args.wire_speed or 10), indent=2))
                else:
                    async with connect(args.device, timeout=args.timeout) as strip:
                        result = await strip.play_effect(effect.name, mapping=mapping, direction=args.direction,
                                                         brightness=args.brightness, delivery='buffered',
                                                         wire_speed=args.wire_speed or 10)
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
                                  'step_seconds': effect.step_seconds, 'direction': args.direction,
                                  'transition': effect.transition, 'delivery': selected,
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
        if args.cmd == 'play':
            frames = _load_frames(args.file)
            mapping = FrameMapping(transpose=args.transpose, flip_x=args.flip_x, flip_y=args.flip_y)
            if args.dry_run:
                # Offline dimensions come from input, never a fake device report.
                h, w = len(frames[0]), len(frames[0][0]) if len(frames[0]) else 0
                topology = Topology(h, w) if args.transpose else Topology(w, h)
                prepared = prepare_frames(frames, topology, mapping)
                within = sum(sum(a != b for a, b in zip(previous, current))
                             for previous, current in zip(prepared, prepared[1:]))
                boundary = sum(a != b for a, b in zip(prepared[-1], prepared[0]))
                writes = topology.pixel_count + within * args.repeat + boundary * (args.repeat - 1)
                print(json.dumps({'source': 'offline input dimensions; NOT read from device',
                                  'width': topology.width, 'height': topology.height,
                                  'frames': len(prepared) * args.repeat, 'pixel_writes': writes,
                                  'requested_fps': args.fps, 'pixel_delay_seconds': 0.01,
                                  'saved_to_controller': False}, indent=2))
            else:
                async with connect(args.device, timeout=args.timeout) as strip:
                    result = await strip.play_frames(frames, mapping=mapping, fps=args.fps,
                                                     repeat=args.repeat, brightness=args.brightness)
                    _playback_result(result)
            return
        if args.cmd == 'scan':
            devices = await scan()
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
                    print(f'raw   {raw.hex()}\ntext  {raw.rstrip(bytes(1)).decode("ascii", errors="backslashreplace")}')
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
