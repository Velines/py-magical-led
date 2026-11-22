"""Magical LED 1.2.0 lighting control. No Bluetooth imports at package import."""
from .client import Strip, connect, scan
from .protocol import brightness, clock, color, decrypt, encrypt, plaintext, power
from .protocol import animation, effect, effect_scene, image, static_color
from .catalogue import Preset, catalogue
from .frames import Topology, FrameMapping, PlaybackResult, parse_topology, prepare_frames
from .effects import (
    StaticEffect,
    StripedEffect,
    XMAS_01,
    XMAS_02,
    XMAS_01_STATIC,
    XMAS_02_STATIC,
    get_effect,
    list_effects,
)
from .buffered import encode_animation, AnimationTransfer, AnimationUploadResult, AnimationTransferError
from .buffered import StorageCapabilities, PersistentStoreResult, StorageUnsupportedError

__all__ = ['Strip', 'brightness', 'clock', 'color', 'connect', 'decrypt', 'encrypt',
           'plaintext', 'power', 'scan', 'animation', 'effect', 'effect_scene',
           'image', 'static_color', 'Preset', 'catalogue', 'Topology', 'FrameMapping',
           'PlaybackResult', 'parse_topology', 'prepare_frames', 'StripedEffect',
           'StaticEffect', 'XMAS_01', 'XMAS_02', 'XMAS_01_STATIC', 'XMAS_02_STATIC',
           'get_effect', 'list_effects',
           'encode_animation', 'AnimationTransfer', 'AnimationUploadResult', 'AnimationTransferError',
           'StorageCapabilities', 'PersistentStoreResult', 'StorageUnsupportedError']
