"""Explicit, single-use Windows OBS audio connection; no capture on import.

This client binds a pipe to the process retained from authenticated control before
exchanging a fresh secret. The future OBS plugin must separately enforce its DACL,
client identity and one-use handshake. Authentication does not arm the receiver.
"""

from __future__ import annotations

import hmac
import math
import secrets
import struct
import threading
import time
from typing import Callable

from utterleaf import obs_protocol, windows_peer_identity, windows_pipe


_MAGIC = b"ULAH"
_VERSION = 1
_HELLO = 1
_ACK = 2
_HEADER = struct.Struct("<4sBBH16s")
_RECORD = struct.Struct("<4sBBH16s32s")
_ACK_DOMAIN = b"Utterleaf OBS audio server ack v1\0"
_ARM_MAGIC = b"ULAC"
_ARM_RECORD = struct.Struct("<4sBBH16sBBH")
HANDSHAKE_BYTES = _RECORD.size
_AUDIO_TIMEOUT = 5.0
_DISARM_TIMEOUT = 7.0  # Allow the native five-second tail/receipt budget.
_POLL_SECONDS = 0.05


class ObsAudioPipeError(RuntimeError):
    """The single-use audio connection failed; do not silently reconnect."""


class ObsAudioPipeCancelled(ObsAudioPipeError):
    """The caller cancelled or closed the audio connection."""


def _check(cancelled: Callable[[], bool], deadline: float) -> None:
    if not callable(cancelled) or type(deadline) not in (int, float):
        raise ObsAudioPipeError("Invalid OBS audio operation")
    if not math.isfinite(deadline):
        raise ObsAudioPipeError("Invalid OBS audio operation")
    try:
        if cancelled():
            raise ObsAudioPipeCancelled("OBS audio connection cancelled")
    except ObsAudioPipeCancelled:
        raise
    except Exception:
        raise ObsAudioPipeError("OBS audio cancellation check failed") from None
    if time.monotonic() >= deadline:
        raise ObsAudioPipeError("OBS audio operation timed out")


def _failure(exc: BaseException) -> None:
    if isinstance(exc, (ObsAudioPipeCancelled, windows_pipe.WindowsPipeCancelled,
                        windows_peer_identity.PeerIdentityCancelled)):
        raise ObsAudioPipeCancelled("OBS audio connection cancelled") from None
    if isinstance(exc, Exception):
        raise ObsAudioPipeError("OBS audio connection could not be verified or continued") from None
    raise exc


def _verify(pipe, peer, cancelled, deadline) -> None:
    _check(cancelled, deadline)
    peer.verify_pid(pipe.server_pid(), cancelled=cancelled, deadline=deadline)
    _check(cancelled, deadline)


def _read_exact(pipe, length: int, cancelled, deadline) -> bytes:
    result = bytearray()
    while len(result) < length:
        _check(cancelled, deadline)
        chunk = pipe.read(length - len(result), deadline=deadline)
        if type(chunk) is not bytes or not 0 < len(chunk) <= length - len(result):
            raise ObsAudioPipeError("Invalid OBS audio handshake")
        result.extend(chunk)
    return bytes(result)


class ObsAudioPipe:
    """Caller-owned authenticated pipe and independent process lease.

    One worker calls read_frames. close may run elsewhere: signal/close the native
    pipe first so any pending operation drains before decoder/identity cleanup.
    No control socket is consulted after the independently owned lease is issued.
    """

    def __init__(self, pipe, peer, session_id: bytes, cancelled: Callable[[], bool]):
        self._pipe, self._peer = pipe, peer
        self._session_id, self._cancelled = session_id, cancelled
        self._decoder = obs_protocol.FrameDecoder()
        self._io_lock = threading.Lock()
        self._closed = threading.Event()
        self._armed = False
        self._request_lock = threading.Lock()
        self._disarm_requested_at: float | None = None
        self._disarm_sent = False
        self._ending = False
        self._seen_frame = False
        self._partial_deadline: float | None = None

    def __repr__(self) -> str:
        return "ObsAudioPipe()"

    def __enter__(self) -> ObsAudioPipe:
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def request_disarm(self) -> bool:
        """Signal a manual stop without I/O or waiting for the reader.

        True means the intent was accepted, not that native capture has ended.
        Keep the one reader running until it receives End or an error. Repeated
        clicks coalesce; the worker sends at most one command. close is the
        separate hard-cancel path. A completed/closed connection returns False.
        """
        with self._request_lock:
            if self._closed.is_set() or self._ending:
                return False
            if not self._armed:
                raise ObsAudioPipeError("OBS audio session is not armed")
            if self._disarm_requested_at is None:
                self._disarm_requested_at = time.monotonic()
            return True

    def _read_ready(self, deadline: float | None) -> tuple[int, float]:
        # No pending ReadFile while idle: the sole I/O owner can service Disarm
        # between probes without a second writer or cancellation of a live read.
        if deadline is not None:
            _check(self._cancelled, deadline)
        limit = deadline
        if self._seen_frame:
            idle = time.monotonic() + _AUDIO_TIMEOUT
            limit = idle if limit is None else min(limit, idle)
        if self._partial_deadline is not None:
            limit = self._partial_deadline if limit is None else min(limit, self._partial_deadline)
        while True:
            with self._request_lock:
                requested = self._disarm_requested_at
            if requested is not None:
                stop_limit = requested + _DISARM_TIMEOUT
                limit = stop_limit if limit is None else min(limit, stop_limit)
            operation_limit = time.monotonic() + _AUDIO_TIMEOUT
            if limit is not None:
                operation_limit = min(operation_limit, limit)
            if self._closed.is_set():
                raise ObsAudioPipeCancelled("OBS audio connection closed")
            _verify(self._pipe, self._peer, self._cancelled, operation_limit)
            if requested is not None and not self._disarm_sent:
                # Latch before dispatch: a lost write result must never retry.
                self._disarm_sent = True
                record = _ARM_RECORD.pack(_ARM_MAGIC, 1, 4, 0,
                                          self._session_id, 0, 0, 0)
                self._pipe.write_all(record, deadline=operation_limit)
                _verify(self._pipe, self._peer, self._cancelled, operation_limit)
            available = self._pipe.available_bytes(deadline=operation_limit)
            if type(available) is not int or not 0 <= available <= 0xFFFFFFFF:
                raise ObsAudioPipeError("Invalid OBS audio availability")
            if available:
                return min(available, obs_protocol.MAX_FEED_BYTES), operation_limit
            # Event.wait also wakes immediately for a concurrent hard close.
            self._closed.wait(_POLL_SECONDS)

    def read_frames(self, *, deadline: float | None = None) -> list[obs_protocol.Frame]:
        """Read one bounded chunk; fragmentation may yield no complete frame.

        Consent, stream-start ordering and storage remain ObsCaptureSession's
        responsibility. A decoded End is acknowledged before closing; it must
        be last, so the server cannot discard an unread terminal packet.
        Timeout, malformed data or identity loss are terminal, never complete.
        With no caller deadline, only waiting before the first packet is
        indefinite. Partial packets, active-audio inactivity and a requested
        Disarm have finite deadlines; no limit applies to total capture length.
        """
        try:
            with self._io_lock:
                if self._closed.is_set():
                    raise ObsAudioPipeCancelled("OBS audio connection closed")
                if not self._armed:
                    raise ObsAudioPipeError("OBS audio session is not armed")
                maximum, operation_limit = self._read_ready(deadline)
                data = self._pipe.read(maximum, deadline=operation_limit)
                _verify(self._pipe, self._peer, self._cancelled, operation_limit)
                if self._closed.is_set():
                    raise ObsAudioPipeCancelled("OBS audio connection closed")
                if type(data) is not bytes or not 0 < len(data) <= maximum:
                    raise ObsAudioPipeError("Invalid OBS audio stream")
                frames = self._decoder.feed(data)
                ended = False
                for index, frame in enumerate(frames):
                    if frame.session_id != self._session_id:
                        raise ObsAudioPipeError("OBS audio session changed")
                    if isinstance(frame, obs_protocol.EndFrame):
                        if index != len(frames) - 1:
                            raise ObsAudioPipeError("OBS audio followed its end")
                        self._decoder.finish()  # Reject any trailing partial frame.
                        if not frame.last_sequences and (self._seen_frame or not self._disarm_sent):
                            raise ObsAudioPipeError("Unexpected OBS no-audio termination")
                        ended = True
                    self._seen_frame = True
                if self._decoder.has_partial_frame:
                    if frames or self._partial_deadline is None:
                        self._partial_deadline = time.monotonic() + _AUDIO_TIMEOUT
                else:
                    self._partial_deadline = None
                if ended:
                    with self._request_lock:
                        self._ending = True
                    _verify(self._pipe, self._peer, self._cancelled, operation_limit)
                    receipt = _ARM_RECORD.pack(_ARM_MAGIC, 1, 3, 0,
                                               self._session_id, 0, 0, 0)
                    self._pipe.write_all(receipt, deadline=operation_limit)
                    # The server may disconnect as soon as it reads this
                    # receipt. Its identity was checked before sending; do
                    # not require a still-connected pipe after terminal ACK.
                    # Retain our endpoint until then so its final receipt read
                    # can finish peer validation before the client closes.
                    self._pipe.wait_for_disconnect(deadline=operation_limit)
            if ended:
                self.close()
            return frames
        except BaseException as exc:
            self.close()
            _failure(exc)

    def arm(self, *, additional_mix_mask: int = 0, deadline: float) -> None:
        """Commit the one-use native Arm command before accepting ULAP frames."""
        try:
            with self._io_lock:
                if self._closed.is_set() or self._armed:
                    raise ObsAudioPipeError("OBS audio session cannot be armed")
                if (type(additional_mix_mask) is not int
                        or not 0 <= additional_mix_mask <= 63):
                    raise ObsAudioPipeError("Invalid OBS audio arm request")
                record = _ARM_RECORD.pack(_ARM_MAGIC, 1, 1, 0, self._session_id,
                                          additional_mix_mask, 0, 0)
                _verify(self._pipe, self._peer, self._cancelled, deadline)
                self._pipe.write_all(record, deadline=deadline)
                _verify(self._pipe, self._peer, self._cancelled, deadline)
                reply = _read_exact(self._pipe, _ARM_RECORD.size,
                                    self._cancelled, deadline)
                _verify(self._pipe, self._peer, self._cancelled, deadline)
                magic, version, kind, reserved, session, mask, status, trailing = _ARM_RECORD.unpack(reply)
                if (magic != _ARM_MAGIC or version != 1 or kind != 2 or reserved
                        or session != self._session_id or mask != additional_mix_mask
                        or status not in (1, 2) or trailing):
                    raise ObsAudioPipeError("Invalid OBS audio arm response")
                if status != 1:
                    raise ObsAudioPipeError("OBS audio arm was refused")
                _check(self._cancelled, deadline)
                if self._closed.is_set():
                    raise ObsAudioPipeCancelled("OBS audio connection closed")
                with self._request_lock:
                    self._armed = True
        except BaseException as exc:
            self.close()
            _failure(exc)

    def close(self) -> None:
        self._closed.set()
        try:
            self._pipe.close()
        finally:
            with self._io_lock:
                try:
                    self._decoder.finish()
                except obs_protocol.ProtocolError:
                    pass
                self._peer.close()


def connect(session_id: bytes, peer: windows_peer_identity.VerifiedProcessLease,
            *, cancelled: Callable[[], bool], deadline: float) -> ObsAudioPipe:
    """Consume an independent authenticated-control process lease on every exit.

    The pipe name is constructed from the exact 16-byte nonsecret session ID.
    Secret/ACK authentication runs once before any ULAP frames are returned.
    Python/HMAC internal copies cannot be guaranteed erased; mutable construction
    buffers are cleared best-effort and no secret is retained on the connection.
    """
    pipe = None
    secret = bytearray()
    hello = bytearray()
    try:
        _check(cancelled, deadline)
        if type(session_id) is not bytes or len(session_id) != 16:
            raise ObsAudioPipeError("Invalid OBS audio session")
        peer.verify_pid(peer.pid, cancelled=cancelled, deadline=deadline)
        pipe = windows_pipe.connect(
            "\\\\.\\pipe\\Utterleaf.OBS." + session_id.hex(),
            cancelled=cancelled, deadline=deadline,
        )
        _verify(pipe, peer, cancelled, deadline)
        header = _HEADER.pack(_MAGIC, _VERSION, _HELLO, 0, session_id)
        secret = bytearray(secrets.token_bytes(32))
        hello = bytearray(header)
        hello.extend(secret)
        _verify(pipe, peer, cancelled, deadline)  # Last check before secret dispatch.
        pipe.write_all(bytes(hello), deadline=deadline)
        reply = _read_exact(pipe, HANDSHAKE_BYTES, cancelled, deadline)
        _verify(pipe, peer, cancelled, deadline)
        magic, version, kind, reserved, returned_session, mac = _RECORD.unpack(reply)
        expected = hmac.digest(secret, _ACK_DOMAIN + header, "sha256")
        if (magic != _MAGIC or version != _VERSION or kind != _ACK or reserved
                or returned_session != session_id or not hmac.compare_digest(mac, expected)):
            raise ObsAudioPipeError("Invalid OBS audio handshake")
        _check(cancelled, deadline)
        return ObsAudioPipe(pipe, peer, session_id, cancelled)
    except BaseException as exc:
        try:
            if pipe is not None:
                pipe.close()
        finally:
            peer.close()
        _failure(exc)
    finally:
        secret[:] = b"\0" * len(secret)
        hello[:] = b"\0" * len(hello)
