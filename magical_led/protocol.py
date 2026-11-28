"""Immutable application values; wire order, units and sources in docs/protocol.md."""
from collections.abc import Iterator
from datetime import datetime

from ._block import block
from .catalogue import preset_id

SERVICE = '0000fff0-0000-1000-8000-00805f9b34fb'
COMMAND = 'd44bc439-abfd-45a2-b575-925416129600'
NOTIFY = 'd44bc439-abfd-45a2-b575-925416129601'  # SDK default; discover actual properties
VERSION_READ = 'd44bc439-abfd-45a2-b575-925416129602'
BULK = 'd44bc439-abfd-45a2-b575-92541612960a'
LIVE = 'd44bc439-abfd-45a2-b575-92541612960b'

# Only W1 tokens observed in padded command builders. STYPE is a short builder.
_ARITY = {t: 0 for t in 'LEDON LEDOFF LIGHTON LIGHTOFF EVERT STOPR VER STSC STIN DATCP MANCP PLACP LEDFIRST LEDSECOND'.split()}
_ARITY.update({t: 1 for t in 'LIGHT SPEED EFFE MODE IMAG ANIM PLAY BACK INVER MIC SMVEW'.split()})
_ARITY.update(COLO=3, TIME=4, CALL=2, SCHD=8, DATS=3, MANY=4)


def plaintext(token: str, *fields: int) -> bytes:
    """Build a 16-byte W1 block using *wire-order* octets; no value wrapping.

    Prefer color() for RGB input. STIN's length byte is an app literal.
    """
    # trace: SWR-001-AC1
    if token not in _ARITY or len(fields) != _ARITY[token]:
        raise ValueError(f'unknown command or incorrect argument count: {token!r}')
    if any(type(x) is not int or not 0 <= x <= 255 for x in fields):
        raise ValueError('fields must be integer octets (0..255)')
    payload = token.encode('ascii') + bytes(fields)
    n = 6 if token == 'STIN' else len(payload)
    return (bytes([n]) + payload).ljust(16, b'\0')


def power(on: bool) -> bytes:
    if not isinstance(on, bool):
        raise ValueError('on must be a boolean')
    return plaintext('LEDON' if on else 'LEDOFF')


def parse_power_notification(frame: bytes) -> bool | None:
    """Interpret a decrypted notification using the Android app's power parser."""
    if len(frame) > 8:
        token = frame[1:6]
        if token == b'LEDON':
            return True
        if token == b'LEDOF':  # The app does not check the second F.
            return False
    return None


def color(red: int, green: int, blue: int) -> bytes:
    """RGB arguments; the device actually receives GRB."""
    return plaintext('COLO', green, red, blue)


def brightness(level: int) -> bytes:
    """Raw app level; zero is substituted with one (not power-off)."""
    return plaintext('LIGHT', 1 if type(level) is int and level == 0 else level)


def effect(preset: int) -> bytes:
    """App effect 1..5, or 0 to disable the effect on the tested firmware."""
    return plaintext('EFFE', preset_id(preset, 5, minimum=0))


def animation(preset: int) -> bytes:
    """Select an app-listed animation, without uploading or saving content."""
    return plaintext('ANIM', preset_id(preset, 25))


def image(preset: int) -> bytes:
    """Select an app-listed image; hardware playback is not yet verified."""
    return plaintext('IMAG', preset_id(preset, 25))


def static_color(red: int, green: int, blue: int, *, level: int | None = None) -> tuple[bytes, ...]:
    """Plan [LIGHT,] EFFE 0, COLO, in the hardware-tested order.

    color() remains a single raw COLO frame for callers controlling mode directly.
    """
    rgb = color(red, green, blue)
    return (() if level is None else (brightness(level),)) + (effect(0), rgb)


def effect_scene(preset: int, *, level: int | None = None,
                 speed: int | None = None) -> tuple[bytes, ...]:
    """Apply optional settings before reselecting an effect; no cached state."""
    frames = (() if level is None else (brightness(level),))
    frames += (() if speed is None else (plaintext('SPEED', speed),))
    return frames + (effect(preset),)


def clock(local: datetime) -> bytes:
    """Encode the supplied wall clock; caller chooses the intended timezone."""
    return plaintext('TIME', local.isoweekday(), local.hour, local.minute, local.second)


def encrypt(frame: bytes) -> bytes:
    return block(frame)


def decrypt(value: bytes) -> bytes:
    """Return the full decrypted block, including unknown tokens and padding."""
    return block(value, inverse=True)


def indexed_chunks(data: bytes, capacity: int = 18) -> Iterator[bytes]:
    """Unencrypted W2 text/DIY chunks; caller owns ACK sequencing and MTU choice.

    Refuse streams that depend on unverified sequence-number rollover.
    """
    if capacity not in (18, 96, 98) or not isinstance(data, bytes):
        raise ValueError('expected bytes and an app payload capacity of 18, 96 or 98')
    if len(data) > 256 * capacity:
        raise ValueError('transfer would wrap frame index')
    for i in range(0, len(data), capacity):
        part = data[i:i + capacity]
        yield bytes((1 + len(part), i // capacity)) + part.ljust(capacity, b'\0')


def image_chunks(data: bytes) -> Iterator[bytes]:
    """Encrypted W2 image frames, given already model-serialized bitmap bytes."""
    for i in range(0, len(data), 15):
        part = data[i:i + 15]
        yield encrypt(bytes([len(part)]) + part.ljust(15, b'\0'))


def pixel(coord1: int, coord2: int, red: int, green: int, blue: int) -> bytes:
    """Plain W3 point-edit block. Coordinates are in the controller's orientation."""
    fields = (coord1, coord2, green, red, blue)
    if any(type(x) is not int or not 0 <= x <= 255 for x in fields):
        raise ValueError('coordinates and color components must be integer octets')
    return bytes((5, *fields)).ljust(16, b'\0')
