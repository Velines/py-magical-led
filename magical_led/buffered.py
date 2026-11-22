"""Experimental controller-side custom animation format from app 1.2.0.

Payload = frames, then columns, then rows, each pixel GRB. Upload can replace
existing custom content. No slot/readback/persistence guarantee is implied.
"""
from dataclasses import dataclass
from collections.abc import Sized

from .frames import Topology, FrameMapping, prepare_frames
from .protocol import plaintext, indexed_chunks


class AnimationTransferError(RuntimeError):
    """Transfer did not complete; custom content may already be partly replaced."""


class StorageUnsupportedError(RuntimeError):
    """No verified safe storage/playback capability for this controller profile."""


@dataclass(frozen=True)
class AnimationTransfer:
    frame_count: int
    wire_speed: int
    payload: bytes
    header: bytes
    chunks: tuple[bytes, ...]


def encode_animation(frames, topology: Topology, *, mapping: FrameMapping = FrameMapping(),
                     wire_speed: int = 10, chunk_capacity: int = 96) -> AnimationTransfer:
    """Validate and encode completely before ANY transfer write.

    Raw speed 1..10 comes from the app; it is not milliseconds or seconds.
    Index rollover, >65535-byte payloads and >255 frames are refused.
    """
    # trace: SWR-007-AC1
    if type(wire_speed) is not int or not 1 <= wire_speed <= 10:
        raise ValueError('wire_speed must be an integer 1..10; time mapping is unverified')
    if type(chunk_capacity) is not int or chunk_capacity not in (18, 96):
        raise ValueError('custom-animation payload capacity must be 18 or 96')
    if not isinstance(topology, Topology):
        raise ValueError('expected a Topology')
    if isinstance(frames, Sized) and (len(frames) > 255 or len(frames) * topology.pixel_count * 3 > 65535):
        raise ValueError('animation exceeds 255 frames or 65535 payload bytes')
    normalized = prepare_frames(frames, topology, mapping)
    size = len(normalized) * topology.pixel_count * 3
    if len(normalized) > 255 or size > 65535:
        raise ValueError('animation exceeds 255 frames or 65535 payload bytes')
    payload = bytearray()
    for frame in normalized:
        for x in range(topology.width):
            for y in range(topology.height):
                red, green, blue = frame[y * topology.width + x]
                payload.extend((green, red, blue))
    payload = bytes(payload)
    chunks = tuple(indexed_chunks(payload, capacity=chunk_capacity))
    header = plaintext('MANY', len(normalized), wire_speed, size >> 8, size & 255)
    return AnimationTransfer(len(normalized), wire_speed, payload, header, chunks)


@dataclass(frozen=True)
class AnimationUploadResult:
    """MANCPOK acknowledged; autonomous playback/persistence need observation."""
    frame_count: int
    bytes_sent: int
    chunks_sent: int
    wire_speed: int
    elapsed_seconds: float
    reported_type: str | None
    completion_reply_hex: str
    power_cycle_persistence: str = 'unverified'


@dataclass(frozen=True)
class StorageCapabilities:
    """Verified library support, not a discovery of unknown firmware features."""
    controller_type: str | None
    firmware: str
    width: int
    height: int
    temporary_buffer_verified: bool
    persistent_save_verified: bool
    startup_speed_retained: bool | None


@dataclass(frozen=True)
class PersistentStoreResult:
    """Save write completed using a power-cycle-tested profile, not fresh readback."""
    upload: AnimationUploadResult
    save_command_hex: str
    elapsed_seconds: float
    startup_speed_retained: bool | None
    power_cycle_checked_by_operation: bool = False
