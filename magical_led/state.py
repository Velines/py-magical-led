"""Clock, schedule, version and combined controller-state models and parsers.

Wire formats follow docs/protocol.md and docs/current-state-readback.md.
Fields not reported by the controller remain None; defaults are never fabricated.
"""
from dataclasses import dataclass
from typing import Iterable

from .frames import Topology
from .protocol import plaintext

WEEKDAYS = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')
_DAY_INDEX = {name: i for i, name in enumerate(WEEKDAYS)}
_DAY_ALIASES = {
    'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
    'friday': 4, 'saturday': 5, 'sunday': 6,
}
_GROUP_MASKS = {
    'none': 0,
    'all': 0x7F,
    'daily': 0x7F,
    'everyday': 0x7F,
    'weekdays': 0x1F,
    'weekends': 0x60,
}


def weekday_mask(days: int | str | Iterable[str | int]) -> int:
    """Convert a bitmask (0..127), day-name string or iterable to a 7-bit mask.

    Bit 0 is Monday through bit 6 Sunday, matching BleProtocol.convertWeekByte
    and WeekAdapter in Magical LED 1.2.0.
    """
    if isinstance(days, bool):
        raise ValueError('days cannot be a boolean')
    if isinstance(days, int):
        if not 0 <= days <= 127:
            raise ValueError('weekday bitmask must be an integer 0..127')
        return days
    if isinstance(days, str):
        tokens = [part.strip().lower() for part in days.replace(';', ',').split(',') if part.strip()]
        if not tokens:
            raise ValueError('days string must not be empty; use "none" for no days')
        items: Iterable[str | int] = tokens
    else:
        items = days
    mask = 0
    for item in items:
        if isinstance(item, bool):
            raise ValueError('weekday entry cannot be a boolean')
        if isinstance(item, int):
            if not 1 <= item <= 7:
                raise ValueError('numeric weekday must be 1 (Mon) through 7 (Sun)')
            mask |= 1 << (item - 1)
        elif isinstance(item, str):
            key = item.strip().lower()
            if key in _GROUP_MASKS:
                mask |= _GROUP_MASKS[key]
            elif key in _DAY_INDEX:
                mask |= 1 << _DAY_INDEX[key]
            elif key in _DAY_ALIASES:
                mask |= 1 << _DAY_ALIASES[key]
            else:
                raise ValueError(f'unknown weekday: {item!r}')
        else:
            raise ValueError(f'unsupported weekday entry: {item!r}')
    return mask


def mask_to_weekdays(mask: int) -> tuple[str, ...]:
    """Decode a 7-bit Mon..Sun mask into canonical 3-letter weekday names."""
    if type(mask) is not int or not 0 <= mask <= 127:
        raise ValueError('weekday bitmask must be an integer 0..127')
    return tuple(name for i, name in enumerate(WEEKDAYS) if mask & (1 << i))


@dataclass(frozen=True)
class ScheduleRule:
    """One half (on or off) of the controller's weekly timer schedule."""
    enabled: bool = False
    days: int = 0
    hour: int = 0
    minute: int = 0

    def __post_init__(self):
        if type(self.enabled) is not bool:
            raise ValueError('enabled must be a boolean')
        if type(self.days) is not int or not 0 <= self.days <= 127:
            raise ValueError('days must be a 7-bit integer mask (0..127)')
        if type(self.hour) is not int or not 0 <= self.hour <= 23:
            raise ValueError('hour must be an integer 0..23')
        if type(self.minute) is not int or not 0 <= self.minute <= 59:
            raise ValueError('minute must be an integer 0..59')

    @property
    def weekdays(self) -> tuple[str, ...]:
        return mask_to_weekdays(self.days)

    @property
    def time(self) -> str:
        return f'{self.hour:02d}:{self.minute:02d}'

    def to_dict(self) -> dict:
        return {
            'enabled': self.enabled,
            'days_mask': self.days,
            'weekdays': list(self.weekdays),
            'hour': self.hour,
            'minute': self.minute,
            'time': self.time,
        }


@dataclass(frozen=True)
class Schedule:
    """Controller on/off weekly schedule (STSC reply / SCHD command)."""
    on: ScheduleRule = ScheduleRule()
    off: ScheduleRule = ScheduleRule()

    def __post_init__(self):
        if not isinstance(self.on, ScheduleRule) or not isinstance(self.off, ScheduleRule):
            raise ValueError('on and off must be ScheduleRule instances')

    def to_frame(self) -> bytes:
        return plaintext(
            'SCHD',
            int(self.on.enabled), self.on.days, self.on.hour, self.on.minute,
            int(self.off.enabled), self.off.days, self.off.hour, self.off.minute,
        )

    def to_dict(self) -> dict:
        return {'on': self.on.to_dict(), 'off': self.off.to_dict()}


def schedule(on: ScheduleRule = ScheduleRule(), off: ScheduleRule = ScheduleRule()) -> bytes:
    """Build one 16-byte SCHD plaintext block for the given on/off rules."""
    return Schedule(on=on, off=off).to_frame()


def parse_schedule(frame: bytes) -> Schedule | None:
    """Parse one decrypted STSC or SCHD notification; ignore SCHDOK and others."""
    if not isinstance(frame, bytes) or len(frame) < 13:
        return None
    token = frame[1:5]
    if token not in (b'STSC', b'SCHD'):
        return None
    if token == b'SCHD' and frame[5:7] == b'OK':
        return None
    on_enabled, on_days, on_hour, on_minute = bool(frame[5]), frame[6], frame[7], frame[8]
    off_enabled, off_days, off_hour, off_minute = bool(frame[9]), frame[10], frame[11], frame[12]
    if on_days > 127 or off_days > 127:
        raise ValueError(f'schedule day mask has reserved high bit set: on={on_days:#x}, off={off_days:#x}')
    return Schedule(
        on=ScheduleRule(on_enabled, on_days, on_hour, on_minute),
        off=ScheduleRule(off_enabled, off_days, off_hour, off_minute),
    )


@dataclass(frozen=True)
class VersionInfo:
    """Raw version octets from an encrypted VER reply (not a semantic version)."""
    spi: int
    ota: int

    def __post_init__(self):
        if any(type(v) is not int or not 0 <= v <= 255 for v in (self.spi, self.ota)):
            raise ValueError('version octets must be integers 0..255')

    def to_dict(self) -> dict:
        return {'spi': self.spi, 'ota': self.ota}


def parse_version_notification(frame: bytes) -> VersionInfo | None:
    """Parse one decrypted VER notification; ignore unrelated packets."""
    if not isinstance(frame, bytes) or len(frame) <= 8 or frame[1:4] != b'VER':
        return None
    return VersionInfo(spi=frame[4], ota=frame[5])


@dataclass(frozen=True)
class DeviceState:
    """Read-only snapshot of observed controller fields; unavailable fields are None."""
    firmware_raw_hex: str | None = None
    firmware: str | None = None
    version_info: VersionInfo | None = None
    topology: Topology | None = None
    schedule: Schedule | None = None
    power: bool | None = None
    read_at: str | None = None
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            'read_at': self.read_at,
            'firmware': self.firmware,
            'firmware_raw_hex': self.firmware_raw_hex,
            'version_info': None if self.version_info is None else self.version_info.to_dict(),
            'topology': None if self.topology is None else {
                'width': self.topology.width,
                'height': self.topology.height,
                'pixel_count': self.topology.pixel_count,
                'reported_type': self.topology.reported_type,
            },
            'schedule': None if self.schedule is None else self.schedule.to_dict(),
            'power': self.power,
            'errors': list(self.errors),
        }
