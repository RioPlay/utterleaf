"""Opt-in loopback WebSocket transport for OBS control.

Importing this module performs no I/O. Authentication and session policy belong
to the controller; this adapter only provides a bounded local transport.
"""

from __future__ import annotations

from collections.abc import Callable
import errno
import logging
import math
import select
import socket
import threading
import time
from typing import TypeVar

from websockets.sync.client import ClientConnection, connect as _websocket_connect

from utterleaf import windows_peer_identity


MAX_MESSAGE_BYTES = 65536
MAX_QUEUE = 4
OBS_SUBPROTOCOL = "obswebsocket.json"
CONNECT_TIMEOUT_SECONDS = 5.0
SEND_TIMEOUT_SECONDS = 2.0
CLOSE_TIMEOUT_SECONDS = 1.0
CANCEL_POLL_SECONDS = 0.05
PEER_CHECK_SECONDS = 0.5

_LOGGER = logging.Logger("utterleaf.obs_websocket.disabled")
_LOGGER.disabled = True
_LOGGER.propagate = False
_LOGGER.addHandler(logging.NullHandler())

_T = TypeVar("_T")
_CONNECT_PENDING = {
    errno.EINPROGRESS,
    errno.EWOULDBLOCK,
    errno.EALREADY,
    errno.EINTR,
    getattr(errno, "WSAEINPROGRESS", 10036),
    getattr(errno, "WSAEWOULDBLOCK", 10035),
    getattr(errno, "WSAEALREADY", 10037),
    getattr(errno, "WSAEINTR", 10004),
}


class ObsWebSocketError(RuntimeError):
    """The local OBS control transport failed without exposing peer data."""


class ObsWebSocketTimeout(ObsWebSocketError):
    """A bounded local transport operation timed out."""


class ObsWebSocketCancelled(ObsWebSocketError):
    """The caller cancelled the local transport operation."""


def _cancel_requested(cancelled: Callable[[], bool]) -> bool:
    try:
        return bool(cancelled())
    except Exception:
        raise ObsWebSocketError("OBS control transport failed") from None


def _validate_endpoint(host: object, port: object, cancelled: object) -> None:
    if type(host) is not str or host not in {"127.0.0.1", "::1"}:
        raise ObsWebSocketError("OBS control endpoint is invalid")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ObsWebSocketError("OBS control endpoint is invalid")
    if not callable(cancelled):
        raise ObsWebSocketError("OBS control cancellation is invalid")


def _close_socket(sock: socket.socket) -> None:
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except Exception:
        pass
    try:
        sock.close()
    except Exception:
        pass


def _connect_socket(
    host: str, port: int, cancelled: Callable[[], bool], deadline: float
) -> socket.socket:
    family = socket.AF_INET if host == "127.0.0.1" else socket.AF_INET6
    address = (host, port) if family == socket.AF_INET else (host, port, 0, 0)
    sock: socket.socket | None = None
    try:
        sock = socket.socket(family, socket.SOCK_STREAM)
        sock.setblocking(False)
        result = sock.connect_ex(address)
        if result not in (0, *tuple(_CONNECT_PENDING)):
            raise ObsWebSocketError("OBS control connection failed")
        while result != 0:
            if _cancel_requested(cancelled):
                raise ObsWebSocketCancelled("OBS control connection cancelled")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ObsWebSocketTimeout("OBS control connection timed out")
            _, writable, exceptional = select.select(
                [], [sock], [sock], min(CANCEL_POLL_SECONDS, remaining)
            )
            if not writable and not exceptional:
                continue
            result = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
            if result != 0:
                raise ObsWebSocketError("OBS control connection failed")
        if _cancel_requested(cancelled):
            raise ObsWebSocketCancelled("OBS control connection cancelled")
        sock.setblocking(True)
        return sock
    except ObsWebSocketError:
        if sock is not None:
            _close_socket(sock)
        raise
    except BaseException as exc:
        if sock is not None:
            _close_socket(sock)
        if isinstance(exc, Exception):
            raise ObsWebSocketError("OBS control connection failed") from None
        raise


def _interruptible(
    operation: Callable[[], _T],
    abort: Callable[[], None],
    cancelled: Callable[[], bool],
    timeout: float,
) -> _T:
    """Run blocking library I/O while an owned watchdog can close its socket."""
    try:
        if _cancel_requested(cancelled):
            abort()
            raise ObsWebSocketCancelled("OBS control operation cancelled")
    except BaseException:
        try:
            abort()
        except Exception:
            pass
        raise
    stop = threading.Event()
    outcome: list[str] = []

    def watchdog() -> None:
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                outcome.append("timeout")
                break
            if stop.wait(min(CANCEL_POLL_SECONDS, remaining)):
                return
            try:
                if cancelled():
                    outcome.append("cancelled")
                    break
            except Exception:
                outcome.append("error")
                break
        try:
            abort()
        except Exception:
            pass

    thread = threading.Thread(target=watchdog, name="utterleaf-obs-io-watchdog")
    try:
        thread.start()
    except BaseException as exc:
        try:
            abort()
        except Exception:
            pass
        if isinstance(exc, Exception):
            raise ObsWebSocketError("OBS control transport failed") from None
        raise
    try:
        try:
            result = operation()
        except BaseException as exc:
            try:
                abort()
            except Exception:
                pass
            if not isinstance(exc, Exception):
                raise
            if outcome and outcome[0] == "cancelled":
                raise ObsWebSocketCancelled("OBS control operation cancelled") from None
            if outcome and outcome[0] == "timeout":
                raise ObsWebSocketTimeout("OBS control operation timed out") from None
            raise ObsWebSocketError("OBS control transport failed") from None
        if outcome:
            if outcome[0] == "cancelled":
                raise ObsWebSocketCancelled("OBS control operation cancelled")
            if outcome[0] == "timeout":
                raise ObsWebSocketTimeout("OBS control operation timed out")
            raise ObsWebSocketError("OBS control transport failed")
        return result
    finally:
        stop.set()
        thread.join()


class ObsWebSocketTransport:
    """One explicitly opened WebSocket connection with bounded operations."""

    def __init__(
        self, connection: ClientConnection, cancelled: Callable[[], bool], *, expected, peer
    ) -> None:
        self._connection = connection
        self._cancelled = cancelled
        self._state_lock = threading.Lock()
        self._identity_lock = threading.Lock()
        self._closed = False
        self._expected = expected
        self._peer = peer

    def __enter__(self) -> ObsWebSocketTransport:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def _is_closed(self) -> bool:
        with self._state_lock:
            return self._closed

    def _mark_closed(self) -> bool:
        with self._state_lock:
            if self._closed:
                return False
            self._closed = True
            return True

    def _abort(self) -> None:
        if self._mark_closed():
            try:
                self._connection.close_socket()
            except Exception:
                pass
            finally:
                self._close_identity()

    def _close_identity(self) -> None:
        # Serialize with native verification so a handle cannot close during a
        # query. Detach once when watchdog and owner both reach cleanup.
        with self._identity_lock:
            peer, expected = self._peer, self._expected
            self._peer = self._expected = None
        try:
            if peer is not None:
                peer.close()
        finally:
            if expected is not None:
                expected.close()

    def verify_peer(self, *, deadline: float | None = None) -> None:
        """Revalidate the pinned Windows peer before any credential/request use.

        Native query calls are synchronous. The short deadline bounds polling
        and checks between calls, not an in-flight Windows kernel operation.
        """
        if self._is_closed():
            raise ObsWebSocketError("OBS control transport is closed")
        try:
            limit = time.monotonic() + PEER_CHECK_SECONDS
            if deadline is not None:
                limit = min(limit, deadline)
            with self._identity_lock:
                if self._is_closed() or self._peer is None or self._expected is None:
                    raise ObsWebSocketError("OBS peer identity is unavailable")
                self._peer.revalidate(cancelled=self._cancelled, deadline=limit)
        except BaseException as exc:
            self._abort()
            if isinstance(exc, windows_peer_identity.PeerIdentityCancelled):
                raise ObsWebSocketCancelled("OBS peer verification cancelled") from None
            if isinstance(exc, Exception):
                raise ObsWebSocketError("OBS peer identity could not be verified") from None
            raise

    def send(self, text: str) -> None:
        if self._is_closed():
            raise ObsWebSocketError("OBS control transport is closed")
        if type(text) is not str or len(text) > MAX_MESSAGE_BYTES:
            raise ObsWebSocketError("OBS control message is invalid")
        try:
            encoded_size = len(text.encode("utf-8"))
        except UnicodeError:
            raise ObsWebSocketError("OBS control message is invalid") from None
        if encoded_size > MAX_MESSAGE_BYTES:
            raise ObsWebSocketError("OBS control message is invalid")
        self.verify_peer()
        try:
            _interruptible(
                lambda: self._connection.send(text),
                self._abort,
                self._cancelled,
                SEND_TIMEOUT_SECONDS,
            )
        except ObsWebSocketError:
            self._abort()
            raise

    def retain_peer_process(self) -> windows_peer_identity.VerifiedProcessLease:
        """Return a caller-owned process lease while control identity is valid."""
        try:
            with self._identity_lock:
                if self._is_closed() or self._peer is None or self._expected is None:
                    raise ObsWebSocketError("OBS peer identity is unavailable")
                return self._peer.retain_process(
                    cancelled=self._cancelled,
                    deadline=time.monotonic() + PEER_CHECK_SECONDS,
                )
        except BaseException as exc:
            self._abort()
            if isinstance(exc, windows_peer_identity.PeerIdentityCancelled):
                raise ObsWebSocketCancelled("OBS peer verification cancelled") from None
            if isinstance(exc, Exception):
                raise ObsWebSocketError("OBS peer identity could not be retained") from None
            raise

    def receive(self, timeout: float) -> str:
        if self._is_closed():
            raise ObsWebSocketError("OBS control transport is closed")
        if type(timeout) not in (int, float) or isinstance(timeout, bool):
            raise ObsWebSocketError("OBS control timeout is invalid")
        timeout = float(timeout)
        if not math.isfinite(timeout) or timeout <= 0:
            raise ObsWebSocketError("OBS control timeout is invalid")
        deadline = time.monotonic() + timeout
        self.verify_peer(deadline=deadline)
        while True:
            try:
                cancel_requested = _cancel_requested(self._cancelled)
            except ObsWebSocketError:
                self._abort()
                raise
            if cancel_requested:
                self._abort()
                raise ObsWebSocketCancelled("OBS control receive cancelled")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ObsWebSocketTimeout("OBS control receive timed out")
            try:
                message = self._connection.recv(
                    timeout=min(CANCEL_POLL_SECONDS, remaining)
                )
            except TimeoutError:
                continue
            except BaseException as exc:
                self._abort()
                if isinstance(exc, Exception):
                    raise ObsWebSocketError("OBS control transport failed") from None
                raise
            if type(message) is not str:
                self._abort()
                raise ObsWebSocketError("OBS control message is invalid")
            if (
                len(message) > MAX_MESSAGE_BYTES
                or len(message.encode("utf-8")) > MAX_MESSAGE_BYTES
            ):
                self._abort()
                raise ObsWebSocketError("OBS control message is invalid")
            return message

    def close(self) -> None:
        with self._state_lock:
            if self._closed:
                return
            self._closed = True
        try:
            _interruptible(
                self._connection.close,
                self._connection.close_socket,
                lambda: False,
                CLOSE_TIMEOUT_SECONDS,
            )
        except ObsWebSocketError:
            pass
        finally:
            try:
                self._connection.close_socket()
            except Exception:
                pass
            finally:
                self._close_identity()


def connect(
    host: str,
    port: int,
    *,
    expected_executable: str,
    cancelled: Callable[[], bool],
) -> ObsWebSocketTransport:
    """Open one direct WebSocket connection to an exact numeric loopback peer."""
    _validate_endpoint(host, port, cancelled)
    if _cancel_requested(cancelled):
        raise ObsWebSocketCancelled("OBS control connection cancelled")
    expected = peer = sock = connection = None
    transport = None
    try:
        # A configured full executable identity is mandatory. Opening it before
        # connecting holds the expected file against writes/replacement during
        # this connection; it is not a proof of historical loaded image bytes.
        expected = windows_peer_identity.open_expected_executable(expected_executable)
        deadline = time.monotonic() + CONNECT_TIMEOUT_SECONDS
        sock = _connect_socket(host, port, cancelled, deadline)
        peer = expected.verify(sock, cancelled=cancelled,
                               deadline=min(deadline, time.monotonic() + PEER_CHECK_SECONDS))
        uri = f"ws://{host}:{port}/" if host == "127.0.0.1" else f"ws://[{host}]:{port}/"
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ObsWebSocketTimeout("OBS control connection timed out")
        connection = _interruptible(
            lambda: _websocket_connect(
                uri,
                sock=sock,
                proxy=None,
                subprotocols=[OBS_SUBPROTOCOL],
                compression=None,
                max_size=MAX_MESSAGE_BYTES,
                max_queue=MAX_QUEUE,
                open_timeout=remaining,
                close_timeout=CLOSE_TIMEOUT_SECONDS,
                ping_interval=None,
                user_agent_header=None,
                logger=_LOGGER,
            ),
            lambda: _close_socket(sock),
            cancelled,
            remaining,
        )
        transport = ObsWebSocketTransport(connection, cancelled, expected=expected, peer=peer)
        if connection.subprotocol != OBS_SUBPROTOCOL:
            raise ObsWebSocketError("OBS control handshake failed")
        return transport
    except BaseException as exc:
        if transport is not None:
            transport.close()
        else:
            try:
                if connection is not None:
                    connection.close_socket()
                elif sock is not None:
                    _close_socket(sock)
            finally:
                try:
                    if peer is not None:
                        peer.close()
                finally:
                    if expected is not None:
                        expected.close()
        if isinstance(exc, windows_peer_identity.PeerIdentityCancelled):
            raise ObsWebSocketCancelled("OBS peer verification cancelled") from None
        if isinstance(exc, Exception) and not isinstance(exc, ObsWebSocketError):
            raise ObsWebSocketError("OBS peer identity could not be verified") from None
        raise


__all__ = [
    "CONNECT_TIMEOUT_SECONDS",
    "MAX_MESSAGE_BYTES",
    "MAX_QUEUE",
    "OBS_SUBPROTOCOL",
    "ObsWebSocketCancelled",
    "ObsWebSocketError",
    "ObsWebSocketTimeout",
    "ObsWebSocketTransport",
    "connect",
]
