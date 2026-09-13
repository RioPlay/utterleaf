"""Bounded binary framing for authenticated OBS audio transports.

This module only encodes and parses frames. A session ID identifies a negotiated
session but never authenticates a peer or transport by itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
import struct
from typing import TypeAlias

import numpy as np


MAGIC = b"ULAP"
VERSION = 1
KIND_START = 1
KIND_AUDIO = 2
KIND_GAP = 3
KIND_END = 4

MAX_FRAMES = 8192
CHANNELS = 2
FLOAT32_BYTES = 4
MAX_PCM_BYTES = MAX_FRAMES * CHANNELS * FLOAT32_BYTES
MAX_BODY_BYTES = 65573
MAX_FEED_BYTES = 65536

UINT64_MAX = 2**64 - 1
MAX_SEQUENCE = UINT64_MAX - 1
SUPPORTED_SAMPLE_RATES = frozenset({16000, 32000, 44100, 48000, 88200, 96000})

_HEADER = struct.Struct("<4sBBHI")
_START = struct.Struct("<16sIBBQ")
_AUDIO = struct.Struct("<16sBQQI")
_GAP = struct.Struct("<16sBQQQ")
_END_PREFIX = struct.Struct("<16sBB")
_END_SEQUENCE = struct.Struct("<BQ")

HEADER_BYTES = _HEADER.size
MAX_PACKET_BYTES = HEADER_BYTES + MAX_BODY_BYTES

_INVALID_FRAME = "Invalid protocol frame"
_INVALID_STREAM = "Invalid protocol stream"


class ProtocolError(ValueError):
    """A frame or byte stream violates the bounded protocol contract."""


class EndReason(IntEnum):
    STREAM_STOPPED = 1
    DISARMED = 2
    OBS_EXIT = 3
    SOURCE_CHANGED = 4
    TRANSPORT_ERROR = 5


def _integer(value: object, minimum: int, maximum: int) -> bool:
    return type(value) is int and minimum <= value <= maximum


def _session(value: object) -> bool:
    return type(value) is bytes and len(value) == 16


def _bus(value: object) -> bool:
    return _integer(value, 0, 5)


@dataclass(frozen=True)
class StartFrame:
    session_id: bytes = field(repr=False)
    sample_rate: int
    primary_bus: int
    bus_mask: int
    origin_ns: int

    def __post_init__(self) -> None:
        if (
            not _session(self.session_id)
            or type(self.sample_rate) is not int
            or self.sample_rate not in SUPPORTED_SAMPLE_RATES
            or not _bus(self.primary_bus)
            or not _integer(self.bus_mask, 1, 0x3F)
            or not self.bus_mask & (1 << self.primary_bus)
            or not _integer(self.origin_ns, 0, UINT64_MAX)
        ):
            raise ProtocolError(_INVALID_FRAME)


@dataclass(frozen=True)
class AudioFrame:
    session_id: bytes = field(repr=False)
    bus: int
    sequence: int
    timestamp_ns: int
    frames: int
    pcm: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if (
            not _session(self.session_id)
            or not _bus(self.bus)
            or not _integer(self.sequence, 0, MAX_SEQUENCE)
            or not _integer(self.timestamp_ns, 0, UINT64_MAX)
            or not _integer(self.frames, 1, MAX_FRAMES)
            or type(self.pcm) is not bytes
            or len(self.pcm) != self.frames * CHANNELS * FLOAT32_BYTES
            or len(self.pcm) > MAX_PCM_BYTES
        ):
            raise ProtocolError(_INVALID_FRAME)
        samples = np.frombuffer(self.pcm, dtype="<f4")
        if not np.isfinite(samples).all():
            raise ProtocolError(_INVALID_FRAME)


@dataclass(frozen=True)
class GapFrame:
    session_id: bytes = field(repr=False)
    bus: int
    first_sequence: int
    count: int
    timestamp_ns: int

    def __post_init__(self) -> None:
        if (
            not _session(self.session_id)
            or not _bus(self.bus)
            or not _integer(self.first_sequence, 0, MAX_SEQUENCE)
            or not _integer(self.count, 1, UINT64_MAX)
            or self.first_sequence + self.count > UINT64_MAX
            or not _integer(self.timestamp_ns, 0, UINT64_MAX)
        ):
            raise ProtocolError(_INVALID_FRAME)


@dataclass(frozen=True)
class EndFrame:
    session_id: bytes = field(repr=False)
    reason: EndReason
    last_sequences: tuple[tuple[int, int | None], ...]

    def __post_init__(self) -> None:
        if (
            not _session(self.session_id)
            or type(self.reason) is not EndReason
            or type(self.last_sequences) is not tuple
            or not 1 <= len(self.last_sequences) <= 6
        ):
            raise ProtocolError(_INVALID_FRAME)
        previous_bus = -1
        for item in self.last_sequences:
            if type(item) is not tuple or len(item) != 2:
                raise ProtocolError(_INVALID_FRAME)
            bus, sequence = item
            if (
                not _bus(bus)
                or bus <= previous_bus
                or (sequence is not None and not _integer(sequence, 0, MAX_SEQUENCE))
            ):
                raise ProtocolError(_INVALID_FRAME)
            previous_bus = bus


Frame: TypeAlias = StartFrame | AudioFrame | GapFrame | EndFrame


def encode_frame(frame: Frame) -> bytes:
    """Encode one already-validated frame without transport or authentication."""
    if type(frame) is StartFrame:
        kind = KIND_START
        body = _START.pack(
            frame.session_id, frame.sample_rate, frame.primary_bus, frame.bus_mask, frame.origin_ns
        )
    elif type(frame) is AudioFrame:
        kind = KIND_AUDIO
        body = _AUDIO.pack(
            frame.session_id, frame.bus, frame.sequence, frame.timestamp_ns, frame.frames
        ) + frame.pcm
    elif type(frame) is GapFrame:
        kind = KIND_GAP
        body = _GAP.pack(
            frame.session_id, frame.bus, frame.first_sequence, frame.count, frame.timestamp_ns
        )
    elif type(frame) is EndFrame:
        kind = KIND_END
        body = _END_PREFIX.pack(frame.session_id, int(frame.reason), len(frame.last_sequences)) + b"".join(
            _END_SEQUENCE.pack(bus, UINT64_MAX if sequence is None else sequence)
            for bus, sequence in frame.last_sequences
        )
    else:
        raise ProtocolError(_INVALID_FRAME)
    if len(body) > MAX_BODY_BYTES:
        raise ProtocolError(_INVALID_FRAME)
    return _HEADER.pack(MAGIC, VERSION, kind, 0, len(body)) + body


def _valid_body_length(kind: int, length: int) -> bool:
    if length > MAX_BODY_BYTES:
        return False
    if kind == KIND_START:
        return length == _START.size
    if kind == KIND_AUDIO:
        pcm_bytes = length - _AUDIO.size
        return CHANNELS * FLOAT32_BYTES <= pcm_bytes <= MAX_PCM_BYTES and pcm_bytes % 8 == 0
    if kind == KIND_GAP:
        return length == _GAP.size
    if kind == KIND_END:
        sequence_bytes = length - _END_PREFIX.size
        return _END_SEQUENCE.size <= sequence_bytes <= 6 * _END_SEQUENCE.size and sequence_bytes % 9 == 0
    return False


def _decode_body(kind: int, body: bytes) -> Frame:
    if kind == KIND_START:
        return StartFrame(*_START.unpack(body))
    if kind == KIND_AUDIO:
        session_id, bus, sequence, timestamp_ns, frames = _AUDIO.unpack_from(body)
        return AudioFrame(session_id, bus, sequence, timestamp_ns, frames, body[_AUDIO.size :])
    if kind == KIND_GAP:
        return GapFrame(*_GAP.unpack(body))
    if kind == KIND_END:
        session_id, reason_value, declared_count = _END_PREFIX.unpack_from(body)
        count = (len(body) - _END_PREFIX.size) // _END_SEQUENCE.size
        if declared_count != count:
            raise ProtocolError(_INVALID_FRAME)
        entries = []
        for index in range(count):
            offset = _END_PREFIX.size + index * _END_SEQUENCE.size
            bus, sequence = _END_SEQUENCE.unpack_from(body, offset)
            entries.append((bus, None if sequence == UINT64_MAX else sequence))
        try:
            reason = EndReason(reason_value)
        except ValueError as exc:
            raise ProtocolError(_INVALID_FRAME) from exc
        return EndFrame(session_id, reason, tuple(entries))
    raise ProtocolError(_INVALID_FRAME)


class FrameDecoder:
    """Incrementally parse bounded packets; any error permanently closes it."""

    def __init__(self) -> None:
        self._buffer = bytearray()
        self._closed = False

    def _fail(self, message: str = _INVALID_STREAM) -> None:
        self._buffer.clear()
        self._closed = True
        raise ProtocolError(message)

    def feed(self, data: bytes) -> list[Frame]:
        if self._closed:
            raise ProtocolError(_INVALID_STREAM)
        if type(data) is not bytes or len(data) > MAX_FEED_BYTES:
            self._fail()
        if len(self._buffer) + len(data) > MAX_PACKET_BYTES + MAX_FEED_BYTES:
            self._fail()
        self._buffer.extend(data)
        frames: list[Frame] = []
        try:
            while len(self._buffer) >= HEADER_BYTES:
                magic, version, kind, reserved, length = _HEADER.unpack_from(self._buffer)
                if magic != MAGIC or version != VERSION or reserved != 0:
                    self._fail()
                if not _valid_body_length(kind, length):
                    self._fail()
                packet_bytes = HEADER_BYTES + length
                if len(self._buffer) < packet_bytes:
                    break
                body = bytes(self._buffer[HEADER_BYTES:packet_bytes])
                del self._buffer[:packet_bytes]
                frames.append(_decode_body(kind, body))
        except ProtocolError:
            if not self._closed:
                self._buffer.clear()
                self._closed = True
            raise
        except (struct.error, ValueError, OverflowError) as exc:
            self._buffer.clear()
            self._closed = True
            raise ProtocolError(_INVALID_STREAM) from exc
        return frames

    def finish(self) -> None:
        if self._closed:
            raise ProtocolError(_INVALID_STREAM)
        if self._buffer:
            self._fail("Truncated protocol stream")
        self._closed = True


__all__ = [
    "AudioFrame",
    "CHANNELS",
    "EndFrame",
    "EndReason",
    "Frame",
    "FrameDecoder",
    "GapFrame",
    "HEADER_BYTES",
    "KIND_AUDIO",
    "KIND_END",
    "KIND_GAP",
    "KIND_START",
    "MAGIC",
    "MAX_BODY_BYTES",
    "MAX_FEED_BYTES",
    "MAX_FRAMES",
    "MAX_PACKET_BYTES",
    "MAX_PCM_BYTES",
    "MAX_SEQUENCE",
    "ProtocolError",
    "StartFrame",
    "SUPPORTED_SAMPLE_RATES",
    "UINT64_MAX",
    "VERSION",
    "encode_frame",
]
