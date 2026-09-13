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
HANDSHAKE_BYTES = _RECORD.size


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

    def __repr__(self) -> str:
        return "ObsAudioPipe()"

    def __enter__(self) -> ObsAudioPipe:
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def read_frames(self, *, deadline: float) -> list[obs_protocol.Frame]:
        """Read one bounded chunk; fragmentation may yield no complete frame.

        Consent, stream-start ordering and storage remain ObsCaptureSession's
        responsibility. An End frame closes this connection; it must be last.
        Timeout, malformed data or identity loss are terminal, never complete.
        """
        try:
            with self._io_lock:
                if self._closed.is_set():
                    raise ObsAudioPipeCancelled("OBS audio connection closed")
                _verify(self._pipe, self._peer, self._cancelled, deadline)
                data = self._pipe.read(obs_protocol.MAX_FEED_BYTES, deadline=deadline)
                _verify(self._pipe, self._peer, self._cancelled, deadline)
                if self._closed.is_set():
                    raise ObsAudioPipeCancelled("OBS audio connection closed")
                if type(data) is not bytes or not 0 < len(data) <= obs_protocol.MAX_FEED_BYTES:
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
                        ended = True
            if ended:
                self.close()
            return frames
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
