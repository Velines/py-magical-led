"""Bleak adapter. A Strip borrows a connected client and never disconnects it."""
import asyncio
import math
from datetime import datetime
from time import monotonic
from itertools import count as cycles
from contextlib import AsyncExitStack, asynccontextmanager

from .protocol import BULK, COMMAND, LIVE, SERVICE, VERSION_READ, decrypt, encrypt
from . import protocol
from .frames import Topology, FrameMapping, PlaybackResult, parse_topology, prepare_frames
from .effects import get_effect
from .buffered import (encode_animation, AnimationUploadResult, AnimationTransferError,
                       StorageCapabilities, PersistentStoreResult, StorageUnsupportedError)
from .state import (DeviceState, Schedule, VersionInfo,
                    parse_schedule, parse_version_notification)


def _seconds(value, name, *, positive=False):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0 or (positive and value == 0)):
        raise ValueError(f'{name} must be a finite {"positive" if positive else "nonnegative"} number')
    return value


def _bleak():
    try:
        from bleak import BleakClient, BleakScanner
    except ImportError as exc:
        raise RuntimeError("install live BLE support: python -m pip install '.[ble]'") from exc
    return BleakClient, BleakScanner


def matches(manufacturer_data: dict[int, bytes]) -> bool:
    return manufacturer_data.get(0x5254, b'').startswith(b'\x00\x56')


async def scan(timeout: float = 5):
    """Return compatible advertised devices, not all nearby Bluetooth devices."""
    _, scanner = _bleak()
    observations = await scanner.discover(timeout=timeout, return_adv=True)
    return [dev for dev, adv in observations.values() if matches(adv.manufacturer_data)]


class Strip:
    def __init__(self, client):
        self._client = client
        self._lock = asyncio.Lock()
        self._notify_lock = asyncio.Lock()
        self._listeners = {}
        self._notification_cleanup = None
        self._topology = None
        self._storage_caps = None
        self._service = client.services.get_service(SERVICE)
        if self._service is None:
            raise ValueError(f'control service {SERVICE} not found')
        self._command = self._characteristic(COMMAND)

    def _characteristic(self, uuid):
        char = self._service.get_characteristic(uuid)
        if char is None:
            raise ValueError(f'characteristic {uuid} missing from {SERVICE}')
        return char

    async def send(self, frame: bytes) -> None:
        """Encrypt and write one W1 block. Success means transport completion only."""
        # trace: SWR-003-AC1
        await self._write(self._command, encrypt(frame))

    async def send_sequence(self, frames, *, delay: float = 0.5) -> None:
        """Write a prevalidated W1 sequence without interleaving on this Strip.

        Default 500 ms gaps match the physical tests, not a proven minimum.
        A failed/cancelled sequence can leave partially changed device state;
        no rollback/retry or nonvolatile save is attempted.
        """
        _seconds(delay, 'delay')
        values = tuple(encrypt(frame) for frame in frames)
        async with self._lock:
            for i, value in enumerate(values):
                if i:
                    await asyncio.sleep(delay)
                await self._write_unlocked(self._command, value)

    async def set_power(self, on: bool) -> None:
        await self.send(protocol.power(on))

    async def read_power(self, timeout: float = 5) -> bool | None:
        """Wait for a fresh LED-output power report; send no W1 command.

        Return True for on, False for off, or None if no report is received
        within the deadline, including subscription setup. Never use cached
        or last-commanded state. Firmware may not report power on connect.
        """
        _seconds(timeout, 'timeout', positive=True)
        result = asyncio.get_running_loop().create_future()

        def received(_raw, frame):
            if frame is not None and not result.done():
                state = protocol.parse_power_notification(frame)
                if state is not None:
                    result.set_result(state)

        try:
            async with AsyncExitStack() as subscription:
                deadline = asyncio.timeout(timeout)
                try:
                    async with deadline:
                        await subscription.enter_async_context(self.notifications(received))
                        return await result
                except TimeoutError:
                    if not deadline.expired():
                        raise
                    return None
        finally:
            result.cancel()

    async def set_color(self, red: int, green: int, blue: int, *,
                        brightness: int | None = None, delay: float = 0.5) -> None:
        """Disable the current effect and apply RGB, optionally setting brightness first."""
        await self.send_sequence(protocol.static_color(red, green, blue, level=brightness), delay=delay)

    async def set_brightness(self, level: int, *, color: tuple[int, int, int] | None = None,
                             delay: float = 0.5) -> None:
        """Adjust raw brightness, or restore an explicitly supplied static RGB.

        Without color this sends LIGHT only, which did not preserve static
        green in physical tests. We cannot read back or infer the current RGB.
        """
        frames = ((protocol.brightness(level),) if color is None
                  else protocol.static_color(*color, level=level))
        await self.send_sequence(frames, delay=delay)

    async def set_speed(self, speed: int) -> None:
        await self.send(protocol.plaintext('SPEED', speed))

    async def set_effect(self, preset: int, *, brightness: int | None = None,
                         speed: int | None = None, delay: float = 0.5) -> None:
        """Select effect 0..5, optionally applying settings before selection."""
        await self.send_sequence(protocol.effect_scene(preset, level=brightness, speed=speed), delay=delay)

    async def select_animation(self, preset: int) -> None:
        await self.send(protocol.animation(preset))

    async def select_image(self, preset: int) -> None:
        await self.send(protocol.image(preset))

    async def sync_clock(self, local: datetime | None = None) -> None:
        """Send TIME using the supplied datetime (or current local wall clock)."""
        if local is not None and not isinstance(local, datetime):
            raise ValueError('local must be a datetime instance or None')
        await self.send(protocol.clock(datetime.now() if local is None else local))

    async def set_schedule(self, schedule: Schedule, *, sync_clock: bool = False,
                           local: datetime | None = None, delay: float = 0.5) -> None:
        """Write a weekly on/off schedule (SCHD), optionally syncing TIME first."""
        if not isinstance(schedule, Schedule):
            raise ValueError('schedule must be a Schedule instance')
        if local is not None and not isinstance(local, datetime):
            raise ValueError('local must be a datetime instance or None')
        frames = (schedule.to_frame(),)
        if sync_clock:
            frames = (protocol.clock(datetime.now() if local is None else local),) + frames
        await self.send_sequence(frames, delay=delay)

    async def _query(self, frame: bytes, parser, timeout: float):
        _seconds(timeout, 'timeout', positive=True)
        wire = encrypt(frame)
        result = asyncio.get_running_loop().create_future()

        def received(_raw, plain):
            if plain is None or result.done():
                return
            try:
                parsed = parser(plain)
            except ValueError as exc:
                result.set_exception(exc)
            else:
                if parsed is not None:
                    result.set_result(parsed)

        try:
            async with asyncio.timeout(timeout):
                async with self._lock:
                    async with self.notifications(received):
                        await self._write_unlocked(self._command, wire)
                        return await result
        finally:
            if not result.done():
                result.cancel()
            elif not result.cancelled():
                result.exception()

    async def read_version_info(self, timeout: float = 5) -> VersionInfo:
        """Query encrypted VER notification and return raw SPI/OTA version octets."""
        return await self._query(protocol.plaintext('VER'), parse_version_notification, timeout)

    async def read_schedule(self, timeout: float = 5) -> Schedule:
        """Query STSC and return the controller's configured on/off schedule."""
        return await self._query(protocol.plaintext('STSC'), parse_schedule, timeout)

    async def read_state(self, timeout: float = 3) -> DeviceState:
        """Read all controller-reported state over one connection without lighting writes.

        Performs direct GATT read of …9602, listens for STYPE and any unsolicited
        LEDON/LEDOFF power report, and sends read-only VER and STSC queries.
        Unavailable or timed-out fields remain None and are recorded in errors.
        """
        _seconds(timeout, 'timeout', positive=True)
        read_at = datetime.now().astimezone().isoformat(timespec='seconds')
        errors = []
        firmware_raw_hex = None
        firmware = None
        try:
            raw = await self.read_version()
            firmware_raw_hex = raw.hex()
            firmware = raw.rstrip(b'\0').decode('ascii', errors='backslashreplace')
        except Exception as exc:
            errors.append(f'version_read: {type(exc).__name__}: {exc}')

        loop = asyncio.get_running_loop()
        topology_fut = loop.create_future()
        version_fut = loop.create_future()
        schedule_fut = loop.create_future()
        power_state = None
        if self._topology is not None:
            topology_fut.set_result(self._topology)

        def received(_raw, plain):
            nonlocal power_state
            if plain is None:
                return
            if not topology_fut.done():
                try:
                    topo = parse_topology(plain)
                except ValueError as exc:
                    topology_fut.set_exception(exc)
                else:
                    if topo is not None:
                        topology_fut.set_result(topo)
            if not version_fut.done():
                ver = parse_version_notification(plain)
                if ver is not None:
                    version_fut.set_result(ver)
            if not schedule_fut.done():
                try:
                    sched = parse_schedule(plain)
                except ValueError as exc:
                    schedule_fut.set_exception(exc)
                else:
                    if sched is not None:
                        schedule_fut.set_result(sched)
            reported_power = protocol.parse_power_notification(plain)
            if reported_power is not None:
                power_state = reported_power

        version_info = None
        schedule_val = None
        topology_val = self._topology
        try:
            async with self._lock:
                async with self.notifications(received):
                    for label, token, fut in (('ver', 'VER', version_fut), ('schedule', 'STSC', schedule_fut)):
                        try:
                            async with asyncio.timeout(timeout):
                                await self._write_unlocked(self._command, encrypt(protocol.plaintext(token)))
                                await fut
                        except TimeoutError:
                            errors.append(f'{label}: timed out after {timeout:g}s')
                        except Exception as exc:
                            errors.append(f'{label}: {type(exc).__name__}: {exc}')
                    if not topology_fut.done():
                        try:
                            async with asyncio.timeout(timeout):
                                await topology_fut
                        except TimeoutError:
                            errors.append(f'topology: timed out after {timeout:g}s')
                        except Exception as exc:
                            errors.append(f'topology: {type(exc).__name__}: {exc}')
            if version_fut.done() and not version_fut.cancelled() and version_fut.exception() is None:
                version_info = version_fut.result()
            if schedule_fut.done() and not schedule_fut.cancelled() and schedule_fut.exception() is None:
                schedule_val = schedule_fut.result()
            if topology_fut.done() and not topology_fut.cancelled() and topology_fut.exception() is None:
                topology_val = topology_fut.result()
        finally:
            for fut in (topology_fut, version_fut, schedule_fut):
                if not fut.done():
                    fut.cancel()
                elif not fut.cancelled():
                    fut.exception()

        return DeviceState(
            firmware_raw_hex=firmware_raw_hex,
            firmware=firmware,
            version_info=version_info,
            topology=topology_val,
            schedule=schedule_val,
            power=power_state,
            read_at=read_at,
            errors=tuple(errors),
        )

    async def read_topology(self, timeout: float = 5) -> Topology:
        """Listen for STYPE (or use this connection's cached report), no W1 query.

        Deadline includes subscription. Some firmware may not announce a type;
        absence raises TimeoutError, never a fabricated default grid. Logical
        dimensions are app-profile interpreted, not physical length or mounting.
        """
        # trace: SWR-005-AC1
        _seconds(timeout, 'timeout', positive=True)
        if self._topology is not None:
            return self._topology
        result = asyncio.get_running_loop().create_future()

        def received(_raw, frame):
            if frame is None or result.done():
                return
            try:
                topology = parse_topology(frame)
            except ValueError as exc:
                result.set_exception(exc)
            else:
                if topology is not None:
                    result.set_result(topology)

        try:
            async with asyncio.timeout(timeout):
                async with self.notifications(received):
                    return await result
        finally:
            if not result.done():
                result.cancel()
            elif not result.cancelled():
                # Also retrieve errors if subscription setup failed after a reply.
                result.exception()

    async def play_frames(self, frames, *, topology: Topology | None = None,
                          mapping: FrameMapping = FrameMapping(), fps: float = 1,
                          repeat: int | None = 1, brightness: int | None = None,
                          pixel_delay: float = 0, command_delay: float = 0,
                          initial_pixel_delay: float | None = None) -> PlaybackResult:
        """Submit 2D RGB frames as an unsaved live effect; see docs/live-frames.md.

        First frame writes every native pixel; later frames write differences.
        FPS is a ceiling, not a guarantee or atomic-latch rate. All frames are
        copied/validated before lighting changes. The Strip's write lock is
        held until completion/cancellation; exceptions propagate without save,
        retries or rollback. The last/partial image remains in unsaved edit mode.
        """
        # trace: SWR-005-AC2 SWR-005-AC3
        _seconds(fps, 'fps', positive=True)
        period = 1 / fps
        if not math.isfinite(period):
            raise ValueError('fps is too small to represent a finite frame period')
        _seconds(pixel_delay, 'pixel_delay')
        first_delay = pixel_delay if initial_pixel_delay is None else _seconds(initial_pixel_delay, 'initial_pixel_delay')
        _seconds(command_delay, 'command_delay')
        if repeat is not None and (type(repeat) is not int or repeat < 1):
            raise ValueError('repeat must be a positive integer or None for continuous playback')
        # Avoid black clear/build-up: enter live mode and paint full first frame directly.
        setup = (() if brightness is None else (protocol.brightness(brightness),))
        setup += (protocol.effect(0), protocol.plaintext('SMVEW', 1))
        if topology is None:
            topology = await self.read_topology()
        prepared = prepare_frames(frames, topology, mapping)
        live = self._characteristic(LIVE)
        # Reject unsupported characteristics before the first scene-changing write.
        self._write_response(live, bytes(16))
        self._write_response(self._command, bytes(16))
        count = writes = 0
        overruns = 0
        max_write_seconds = 0.0
        previous = None
        async with self._lock:
            for frame in setup:
                await self._write_unlocked(self._command, encrypt(frame))
                await asyncio.sleep(command_delay)
            start = monotonic()
            for _ in (cycles() if repeat is None else range(repeat)):
                for frame in prepared:
                    frame_start = monotonic()
                    for i, rgb in enumerate(frame):
                        if previous is not None and rgb == previous[i]:
                            continue
                        y, x = divmod(i, topology.width)
                        await self._write_unlocked(live, encrypt(protocol.pixel(y, x, *rgb)))
                        writes += 1
                        delay = first_delay if previous is None else pixel_delay
                        if delay:
                            await asyncio.sleep(delay)
                    previous = frame
                    count += 1
                    write_seconds = monotonic() - frame_start
                    max_write_seconds = max(max_write_seconds, write_seconds)
                    overruns += write_seconds > period
                    # Slow links slip; do not burst to catch up with an old schedule.
                    await asyncio.sleep(max(0, period - write_seconds))
            return PlaybackResult(count, writes, monotonic() - start, overruns, max_write_seconds)

    async def play_effect(self, name: str, *, topology: Topology | None = None,
                          mapping: FrameMapping = FrameMapping(), direction: str = 'right',
                          repeat: int | None = None, brightness: int | None = None,
                          pixel_delay: float = 0, command_delay: float = 0,
                          delivery: str = 'auto',
                          wire_speed: int | None = None,
                          initial_pixel_delay: float | None = None,
                          persist: bool = False) -> PlaybackResult | AnimationUploadResult | PersistentStoreResult:
        """Play visual frames temporarily or persistently (persist=True).

        Auto prefers live for row wipes and buffered for cuts. Buffered play is
        allowed only on a profile whose temporary/persistent isolation was tested.
        It returns after upload and leaves the controller looping autonomously.
        Live repeat=None runs until cancelled. Pass persist=True to store the
        effect persistently in the controller's custom slot on a verified profile.
        """
        # trace: SWR-006-AC2
        if not isinstance(persist, bool):
            raise ValueError('persist must be a boolean')
        effect = get_effect(name)
        if not isinstance(mapping, FrameMapping):
            raise ValueError('expected a FrameMapping')
        if direction not in ('right', 'left'):
            raise ValueError('direction must be right or left')
        if topology is not None and not isinstance(topology, Topology):
            raise ValueError('expected a Topology')
        selected = effect.resolve_delivery(delivery)
        if persist:
            if delivery == 'live':
                raise ValueError('persistent storage requires buffered delivery')
            if repeat is not None:
                raise ValueError('buffered controller loop counts are not known; omit repeat')
            if pixel_delay != 0 or command_delay != 0 or initial_pixel_delay is not None:
                raise ValueError('live pixel/command pacing does not apply to buffered effects')
            topology, _ = await self._verified_storage_topology(topology, persistent=True)
            width, height = mapping.input_size(topology)
            return await self.store_animation(effect.frames(Topology(width, height), direction=direction),
                                              overwrite=True, topology=topology, mapping=mapping,
                                              wire_speed=10 if wire_speed is None else wire_speed,
                                              brightness=brightness)
        if selected == 'buffered':
            if repeat is not None:
                raise ValueError('buffered controller loop counts are not known; omit repeat')
            if pixel_delay != 0 or command_delay != 0 or initial_pixel_delay is not None:
                raise ValueError('live pixel/command pacing does not apply to buffered effects')
            topology, _ = await self._verified_storage_topology(topology, persistent=False)
            width, height = mapping.input_size(topology)
            return await self.play_animation(effect.frames(Topology(width, height), direction=direction),
                                               topology=topology, mapping=mapping, brightness=brightness,
                                               wire_speed=10 if wire_speed is None else wire_speed)
        if wire_speed is not None:
            raise ValueError('wire_speed applies only to buffered effects')
        if topology is None:
            topology = await self.read_topology()
        width, height = mapping.input_size(topology)
        geometry = Topology(width, height)
        frames = effect.frames(geometry, direction=direction)
        return await self.play_frames(frames, topology=topology, mapping=mapping,
                                      fps=1 / effect.frame_interval(geometry), repeat=repeat,
                                      brightness=brightness, pixel_delay=pixel_delay,
                                      command_delay=command_delay,
                                      initial_pixel_delay=pixel_delay
                                      if initial_pixel_delay is None else initial_pixel_delay)

    async def read_storage_capabilities(self) -> StorageCapabilities:
        """Read-only verified-profile support, never guessed from a command name."""
        # trace: SWR-008-AC2
        if self._storage_caps is None:
            topology = await self.read_topology()
            firmware = (await self.read_version()).rstrip(b'\0').decode('ascii', errors='backslashreplace')
            verified = (topology.reported_type == 'STYPE26X20' and firmware == 'TR2103R001-8')
            self._storage_caps = StorageCapabilities(topology.reported_type, firmware,
                topology.width, topology.height, verified, verified, False if verified else None)
        return self._storage_caps

    async def play_animation(self, frames, *, topology: Topology | None = None,
                              mapping: FrameMapping = FrameMapping(), wire_speed: int = 10,
                              brightness: int | None = None,
                              ack_timeout: float = 5, total_timeout: float = 60) -> AnimationUploadResult:
        """Play 2D RGB arrays autonomously from a verified temporary buffer.

        Same input as play_frames/store_animation; no persistent save is sent.
        Returns after MANCPOK; native loop count and time units are not generic.
        Unknown profiles or oversized sequences fail before content writes.
        """
        topology, _ = await self._verified_storage_topology(topology, persistent=False)
        return await self._transfer_animation(frames, topology=topology, mapping=mapping,
                wire_speed=wire_speed, brightness=brightness, ack_timeout=ack_timeout,
                total_timeout=total_timeout)

    async def _verified_storage_topology(self, topology, *, persistent):
        caps = await self.read_storage_capabilities()
        supported = caps.persistent_save_verified if persistent else caps.temporary_buffer_verified
        if not supported:
            raise StorageUnsupportedError('no verified persistent save or temporary-buffer isolation for this firmware/profile')
        actual = Topology(caps.width, caps.height, caps.controller_type)
        if topology is not None and (not isinstance(topology, Topology)
                                    or (topology.width, topology.height) != (actual.width, actual.height)):
            raise ValueError('provided geometry does not match the verified controller grid')
        return actual, caps

    async def store_effect(self, name: str, *, overwrite: bool = False,
                           topology: Topology | None = None, mapping: FrameMapping = FrameMapping(),
                           direction: str = 'right', wire_speed: int = 10,
                           brightness: int | None = None) -> PersistentStoreResult:
        """Persist the SAME rendered visual sequence; delegates to play_effect(persist=True)."""
        if overwrite is not True:
            raise PermissionError('cannot check the saved custom location; pass overwrite=True to permit replacement')
        return await self.play_effect(name, topology=topology, mapping=mapping, direction=direction,
                                      delivery='buffered', wire_speed=wire_speed,
                                      brightness=brightness, persist=True)

    async def store_animation(self, frames, *, overwrite: bool = False,
                              topology: Topology | None = None, mapping: FrameMapping = FrameMapping(),
                              wire_speed: int = 10, brightness: int | None = None,
                              ack_timeout: float = 5, total_timeout: float = 60) -> PersistentStoreResult:
        """Upload, then SMVEW 2 under one write lock on a verified save profile.

        Wait 1 s after MANCPOK and 6 s after the save write, matching the successful
        power-cycle experiment. No save follows a failed upload; no retry/rollback.
        """
        # trace: SWR-008-AC3
        if overwrite is not True:
            raise PermissionError('persistent replacement requires overwrite=True')
        topology, caps = await self._verified_storage_topology(topology, persistent=True)
        return await self._transfer_animation(frames, topology=topology, mapping=mapping,
                wire_speed=wire_speed, brightness=brightness, ack_timeout=ack_timeout,
                total_timeout=total_timeout, persist=True, startup_speed_retained=caps.startup_speed_retained)

    async def upload_effect(self, name: str, *, allow_overwrite: bool = False,
                            topology: Topology | None = None,
                            mapping: FrameMapping = FrameMapping(), direction: str = 'right',
                            wire_speed: int = 10, brightness: int | None = None) -> AnimationUploadResult:
        """Upload any named effect as a controller custom animation, with consent.

        Header has no slot ID; do not assume multiple collection names coexist
        on the controller. Raw speed time mapping and persistence are unverified.
        """
        if allow_overwrite is not True:
            raise PermissionError('buffered upload may overwrite custom animation; pass allow_overwrite=True')
        effect = get_effect(name)
        if not isinstance(mapping, FrameMapping):
            raise ValueError('expected FrameMapping')
        if direction not in ('right', 'left'):
            raise ValueError('direction must be right or left')
        if topology is None:
            topology = await self.read_topology()
        if not isinstance(topology, Topology):
            raise ValueError('expected Topology')
        width, height = mapping.input_size(topology)
        frames = effect.frames(Topology(width, height), direction=direction)
        return await self.upload_animation(frames, topology=topology, mapping=mapping,
                                           wire_speed=wire_speed, brightness=brightness,
                                           allow_overwrite=True)

    async def upload_animation(self, frames, *, allow_overwrite: bool = False,
                               topology: Topology | None = None,
                               mapping: FrameMapping = FrameMapping(), wire_speed: int = 10,
                               brightness: int | None = None,
                               chunk_capacity: int | None = None,
                               ack_timeout: float = 5, total_timeout: float = 60) -> AnimationUploadResult:
        """Experimental MANY/W2/MANCP transfer; may replace custom controller content.

        Subscribe before writes, stop-and-wait on each application ACK; no retry,
        guessed abort or rollback. Deadlines include writes. Cancellation/failure
        may leave a partially replaced animation. Success means MANCPOK, not a
        power-cycle persistence or frame-rate guarantee. Write lock held throughout.
        """
        # trace: SWR-007-AC2
        if allow_overwrite is not True:
            raise PermissionError('buffered upload may overwrite custom animation; pass allow_overwrite=True')
        return await self._transfer_animation(frames, topology=topology, mapping=mapping,
                wire_speed=wire_speed, brightness=brightness, chunk_capacity=chunk_capacity,
                ack_timeout=ack_timeout, total_timeout=total_timeout)

    async def _transfer_animation(self, frames, *, topology=None, mapping=FrameMapping(),
                                  wire_speed=10, brightness=None, chunk_capacity=None,
                                  ack_timeout=5, total_timeout=60, persist=False,
                                  startup_speed_retained=None):
        _seconds(ack_timeout, 'ack_timeout', positive=True)
        _seconds(total_timeout, 'total_timeout', positive=True)
        light = None if brightness is None else protocol.brightness(brightness)
        if topology is None:
            topology = await self.read_topology()
        bulk = self._characteristic(BULK)
        if chunk_capacity is None:
            # Prefer 96-byte payload chunks when the transport can carry them.
            # Fall back to 18-byte chunks for constrained write-without-response links.
            can_wwr_96 = ('write-without-response' in bulk.properties
                          and bulk.max_write_without_response_size >= 98)
            can_write_96 = 'write' in bulk.properties
            chunk_capacity = 96 if (can_wwr_96 or can_write_96) else 18
        try:
            transfer = encode_animation(frames, topology, mapping=mapping,
                                        wire_speed=wire_speed, chunk_capacity=chunk_capacity)
        except ValueError as exc:
            # If 18-byte chunks cannot represent the payload within the 1-byte frame index,
            # retry with 96-byte chunks when the characteristic supports writes.
            if chunk_capacity == 18 and 'wrap frame index' in str(exc) and 'write' in bulk.properties:
                chunk_capacity = 96
                transfer = encode_animation(frames, topology, mapping=mapping,
                                            wire_speed=wire_speed, chunk_capacity=chunk_capacity)
            else:
                raise
        self._write_response(self._command, bytes(16))
        for chunk in transfer.chunks:
            self._write_response(bulk, chunk)
        active = None
        expected = b''
        phase = 'setup'

        def received(_raw, frame):
            if frame is None or active is None or active.done():
                return
            body = frame[1:]
            if body.startswith(b'ERROR'):
                active.set_exception(AnimationTransferError(f'controller ERROR during {phase}; content may be partial'))
            elif body.startswith(expected):
                active.set_result(frame)
            elif any(body.startswith(token) for token in (b'MANYOK', b'REOK', b'MANCPOK', b'DATCPOK')):
                active.set_exception(AnimationTransferError(f'unexpected transfer reply during {phase}; no retry attempted'))

        async def exchange(char, value, token, label):
            nonlocal active, expected, phase
            phase, expected = label, token
            active = asyncio.get_running_loop().create_future()
            try:
                async with asyncio.timeout(ack_timeout):
                    await self._write_unlocked(char, value)
                    return await active
            except TimeoutError as exc:
                raise AnimationTransferError(f'timeout awaiting {token.decode()} during {phase}; content may be partial') from exc
            finally:
                if not active.done():
                    active.cancel()
                elif not active.cancelled():
                    active.exception()
                active = None

        start = monotonic()
        try:
            async with asyncio.timeout(total_timeout):
                async with self._lock:
                    async with self.notifications(received):
                        if light is not None:
                            await self._write_unlocked(self._command, encrypt(light))
                            await asyncio.sleep(0.5)
                        await exchange(self._command, encrypt(transfer.header), b'MANYOK', 'MANY')
                        for i, chunk in enumerate(transfer.chunks):
                            await exchange(bulk, chunk, b'REOK', f'chunk {i}')
                        completion = await exchange(self._command, encrypt(protocol.plaintext('MANCP')),
                                                    b'MANCPOK', 'MANCP')
                        upload_elapsed = monotonic() - start
                        if persist:
                            phase = 'persistent save'
                            await asyncio.sleep(1)
                            save_value = encrypt(protocol.plaintext('SMVEW', 2))
                            if 'write' in self._command.properties:
                                # Prefer ATT confirmation for the commit when supported.
                                await self._client.write_gatt_char(self._command, save_value, response=True)
                            else:
                                await self._write_unlocked(self._command, save_value)
                            await asyncio.sleep(6)
        except TimeoutError as exc:
            raise AnimationTransferError(f'total deadline exceeded during {phase}; content may be partial') from exc
        uploaded = AnimationUploadResult(transfer.frame_count, len(transfer.payload), len(transfer.chunks),
                                          wire_speed, upload_elapsed, topology.reported_type, completion.hex())
        if persist:
            return PersistentStoreResult(uploaded, protocol.plaintext('SMVEW', 2).hex(),
                                          monotonic() - start, startup_speed_retained)
        return uploaded

    async def exit_live(self) -> None:
        """Explicitly leave live editing without requesting save; visual result varies."""
        await self.send(protocol.plaintext('SMVEW', 0))

    async def send_live(self, frame: bytes) -> None:
        """Encrypt one W3 pixel/rhythm block; caller manages edit-mode lifecycle."""
        await self._write(self._characteristic(LIVE), encrypt(frame))

    async def send_chunk(self, wire: bytes) -> None:
        """Send one already-framed W2 value; no extra AES, fragmentation or retries.

        Input is one yield from indexed_chunks or image_chunks. The application
        owns per-device transfer state and waits for the appropriate notification.
        """
        if not isinstance(wire, bytes) or len(wire) not in (16, 20, 98, 100):
            raise ValueError('expected one complete W2 chunk')
        await self._write(self._characteristic(BULK), wire)

    async def _write(self, char, value):
        async with self._lock:
            await self._write_unlocked(char, value)

    async def _write_unlocked(self, char, value):
        response = self._write_response(char, value)
        await self._client.write_gatt_char(char, value, response=response)

    @staticmethod
    def _write_response(char, value):
        props = char.properties
        can_wwr = ('write-without-response' in props
                   and len(value) <= char.max_write_without_response_size)
        can_write = 'write' in props
        if can_wwr:
            return False
        if can_write:
            # Fall back to response writes for large chunks when supported.
            return True
        if 'write-without-response' in props:
            raise ValueError("frame exceeds this characteristic's current write limit")
        raise ValueError('characteristic is not writable')

    def _received(self, _sender, data):
        raw = bytes(data)
        frame = decrypt(raw) if len(raw) == 16 else None
        if frame is not None:
            try:
                topology = parse_topology(frame)
            except ValueError:
                topology = None
            if topology is not None:
                self._topology = topology
        for callback in tuple(self._listeners.values()):
            try:
                callback(raw, frame)
            except Exception as exc:
                asyncio.get_running_loop().call_exception_handler(
                    {'message': 'Magical LED notification callback failed', 'exception': exc})

    @asynccontextmanager
    async def notifications(self, callback):
        """Share FFF0 subscriptions; synchronous callbacks receive (raw, decrypted).

        Concurrent/nested consumers share one native subscription. Failed setup
        rolls back partial subscriptions. Last consumer unsubscribes; callback
        failures go to the event loop exception handler, not other consumers.
        """
        sources = [c for c in self._service.characteristics
                   if {'notify', 'indicate'}.intersection(c.properties)]
        if not sources:
            raise ValueError('no notification or indication characteristic in FFF0')

        token = object()
        async with self._notify_lock:
            self._listeners[token] = callback
            if self._notification_cleanup is None:
                cleanup = AsyncExitStack()
                try:
                    for char in sources:
                        await self._client.start_notify(char, self._received)
                        cleanup.push_async_callback(self._client.stop_notify, char)
                except BaseException:
                    self._listeners.pop(token)
                    await cleanup.aclose()
                    raise
                self._notification_cleanup = cleanup
        try:
            yield
        finally:
            async with self._notify_lock:
                self._listeners.pop(token)
                if not self._listeners:
                    cleanup, self._notification_cleanup = self._notification_cleanup, None
                    await cleanup.aclose()

    async def read_version(self) -> bytes:
        """Read raw version bytes from …9602 (not an encrypted VER notification)."""
        char = self._characteristic(VERSION_READ)
        if 'read' not in char.properties:
            raise ValueError('version characteristic is not readable')
        return bytes(await self._client.read_gatt_char(char))


@asynccontextmanager
async def connect(identifier: str, timeout: float = 10):
    """Own one connection by platform identifier (CoreBluetooth UUID on macOS)."""
    client, scanner = _bleak()
    device = await scanner.find_device_by_address(identifier, timeout=timeout)
    if device is None:
        raise ValueError(f'device not found: {identifier}')
    async with client(device, timeout=timeout) as connection:
        yield Strip(connection)
