"""Explicit, read-only OBS WebSocket control connection.

This channel answers OBS's password challenge and reads stream lifecycle state.
It does not authenticate the audio pipe, arm a receiver, capture audio, or change
OBS settings. A status snapshot/event is never permission to start recording.
Use one serialized worker; close on every exit. No reconnect or persistence.
"""

from __future__ import annotations

import base64
from collections import deque
from dataclasses import dataclass
import hashlib
import json
import math
import secrets
import time
from typing import Callable

from utterleaf import obs_websocket

MAX_MESSAGE = 65_536
MAX_PENDING_EVENTS = 32
REQUEST_TIMEOUT = 5.0
OUTPUTS_SUBSCRIPTION = 1 << 6
GENERAL_SUBSCRIPTION = 1
EVENT_SUBSCRIPTIONS = GENERAL_SUBSCRIPTION | OUTPUTS_SUBSCRIPTION
_READ_REQUESTS = frozenset({"GetVersion", "GetStreamStatus"})
_OUTPUT_STATES = frozenset({
    "OBS_WEBSOCKET_OUTPUT_STARTING", "OBS_WEBSOCKET_OUTPUT_STARTED",
    "OBS_WEBSOCKET_OUTPUT_STOPPING", "OBS_WEBSOCKET_OUTPUT_STOPPED",
    "OBS_WEBSOCKET_OUTPUT_RECONNECTING", "OBS_WEBSOCKET_OUTPUT_RECONNECTED",
})


class ObsControlError(RuntimeError):
    """A control operation failed; messages exclude remote payloads and secrets."""


class ObsControlCancelled(ObsControlError):
    """The caller cancelled this connection."""


@dataclass(frozen=True)
class ObsVersion:
    studio: str
    websocket: str


@dataclass(frozen=True)
class StreamEvent:
    active: bool
    state: str
    revision: int


@dataclass(frozen=True)
class StreamSnapshot:
    active: bool
    reconnecting: bool
    event_revision: int
    events_pending: bool


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(_value):
    raise ValueError("Non-finite JSON number")


def _finite_float(value):
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("Non-finite JSON number")
    return result


def _message(raw: str) -> tuple[int, dict]:
    if type(raw) is not str or len(raw) > MAX_MESSAGE:
        raise ObsControlError("Invalid OBS control message")
    try:
        if len(raw.encode("utf-8")) > MAX_MESSAGE:
            raise ValueError()
        message = json.loads(raw, object_pairs_hook=_object, parse_constant=_reject_constant,
                             parse_float=_finite_float)
        if (type(message) is not dict or type(message.get("op")) is not int
                or type(message.get("d")) is not dict):
            raise ValueError()
    except (ValueError, TypeError, RecursionError):
        raise ObsControlError("Invalid OBS control message") from None
    return message["op"], message["d"]


def _version(value) -> str:
    if (type(value) is not str or not 1 <= len(value) <= 64
            or any(char not in "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.-+" for char in value)):
        raise ObsControlError("Invalid OBS version response")
    return value


def _challenge(value) -> str:
    try:
        if type(value) is not str or len(value) != 44:
            raise ValueError()
        decoded = base64.b64decode(value, validate=True)
        if len(decoded) != 32 or base64.b64encode(decoded).decode("ascii") != value:
            raise ValueError()
    except (ValueError, TypeError):
        raise ObsControlError("Invalid OBS authentication challenge") from None
    return value


def _authentication(password: str, salt, challenge) -> str:
    salt, challenge = _challenge(salt), _challenge(challenge)
    secret = base64.b64encode(hashlib.sha256((password + salt).encode("utf-8")).digest())
    return base64.b64encode(hashlib.sha256(secret + challenge.encode("ascii")).digest()).decode("ascii")


class ObsControl:
    """A single authenticated control connection, without audio privileges.

    Create with ``connect``. Caller-supplied credentials live only for handshake;
    Python strings cannot be securely erased. Never log a traceback with locals.
    The returned version is protocol compatibility evidence, not plugin readiness.
    """

    def __init__(self, transport, cancelled: Callable[[], bool]):
        self._transport = transport
        self._cancelled = cancelled
        self._events: deque[StreamEvent] = deque()
        self._revision = 0
        self._request_id = 0
        self._request_prefix = secrets.token_hex(16)
        self._identified = False
        self.closed = False
        self.version: ObsVersion | None = None

    @classmethod
    def connect(cls, host: str, port: int, password: str, *, expected_executable: str,
                cancelled: Callable[[], bool]):
        # Check the credential before opening even a local socket. Do not retain
        # it on the connection object or expose it in repr/exception messages.
        if type(password) is not str or not 1 <= len(password) <= 1024:
            raise ObsControlError("Enter the OBS WebSocket password")
        try:
            password.encode("utf-8")
        except UnicodeError:
            raise ObsControlError("Invalid OBS WebSocket password") from None
        connection = None
        transport = None
        try:
            transport = obs_websocket.connect(host, port, expected_executable=expected_executable,
                                              cancelled=cancelled)
            connection = cls(transport, cancelled)
            connection._identify(password)
            connection._read_version()
            return connection
        except BaseException as exc:
            if connection is not None:
                connection.close()
            elif transport is not None:
                transport.close()
            if isinstance(exc, obs_websocket.ObsWebSocketCancelled):
                raise ObsControlCancelled("OBS connection cancelled") from None
            if isinstance(exc, obs_websocket.ObsWebSocketError):
                raise ObsControlError("Could not connect to authenticated local OBS") from None
            if isinstance(exc, Exception) and not isinstance(exc, ObsControlError):
                raise ObsControlError("Could not connect to authenticated local OBS") from None
            raise
        finally:
            password = ""

    def _check(self) -> None:
        if self._cancelled():
            self.close()
            raise ObsControlCancelled("OBS connection cancelled")
        if self.closed:
            raise ObsControlError("OBS control connection is closed")

    def retain_peer_process(self):
        """Retain an independently owned authenticated audio-process lease.

        The caller owns the returned lease. This neither arms nor captures audio.
        """
        self._check()
        if not self._identified or self.version is None:
            raise ObsControlError("OBS control authentication is incomplete")
        lease = None
        try:
            lease = self._transport.retain_peer_process()
            self._check()
            return lease
        except BaseException as exc:
            if lease is not None:
                lease.close()
            self._failed(exc)

    def _receive(self, deadline: float) -> tuple[int, dict]:
        while True:
            self._check()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError()
            try:
                raw = self._transport.receive(min(0.1, remaining))
                self._check()
                return _message(raw)
            except obs_websocket.ObsWebSocketTimeout:
                continue

    def _send(self, opcode: int, data: dict) -> None:
        self._check()
        self._transport.send(json.dumps({"op": opcode, "d": data}, separators=(",", ":")))
        self._check()

    def _identify(self, password: str) -> None:
        deadline = time.monotonic() + REQUEST_TIMEOUT
        try:
            opcode, hello = self._receive(deadline)
            if opcode != 0 or type(hello.get("rpcVersion")) is not int or hello["rpcVersion"] != 1:
                raise ObsControlError("Unsupported OBS WebSocket protocol")
            auth = hello.get("authentication")
            if type(auth) is not dict:
                raise ObsControlError("Enable password authentication in OBS WebSocket settings")
            # The OS-backed peer lease predates HTTP upgrade. Revalidate after
            # reading Hello, immediately before deriving/sending its proof.
            self._transport.verify_peer()
            if time.monotonic() >= deadline:
                raise TimeoutError()
            response = _authentication(password, auth.get("salt"), auth.get("challenge"))
            self._send(1, {"rpcVersion": 1, "authentication": response,
                           "eventSubscriptions": EVENT_SUBSCRIPTIONS})
            # OBS sends responses/events through workers. A lifecycle event can
            # precede Identified after Identify. Quarantine bounded events here;
            # none is returned until identification and version checks succeed.
            while True:
                opcode, identified = self._receive(deadline)
                if opcode != 5:
                    break
                self._event(identified)
            if (opcode != 2 or type(identified.get("negotiatedRpcVersion")) is not int
                    or identified["negotiatedRpcVersion"] != 1):
                raise ObsControlError("OBS authentication or protocol negotiation failed")
            self._identified = True
        except TimeoutError:
            raise ObsControlError("OBS authentication timed out") from None

    def _event(self, data: dict) -> None:
        if (type(data.get("eventIntent")) is not int
                or data["eventIntent"] not in {GENERAL_SUBSCRIPTION, OUTPUTS_SUBSCRIPTION}
                or type(data.get("eventType")) is not str):
            raise ObsControlError("Unexpected OBS event subscription")
        if data["eventType"] == "ExitStarted":
            if data["eventIntent"] != GENERAL_SUBSCRIPTION:
                raise ObsControlError("Unexpected OBS event subscription")
            raise ObsControlError("OBS is shutting down")
        # Outputs also includes recording paths/replay status. Ignore these in
        # place; never store, expose, log, or use them as capture triggers.
        if data["eventType"] != "StreamStateChanged":
            return
        if data["eventIntent"] != OUTPUTS_SUBSCRIPTION:
            raise ObsControlError("Unexpected OBS event subscription")
        event = data.get("eventData")
        if (type(event) is not dict or type(event.get("outputActive")) is not bool
                or type(event.get("outputState")) is not str or event["outputState"] not in _OUTPUT_STATES):
            raise ObsControlError("Invalid OBS stream event")
        if len(self._events) >= MAX_PENDING_EVENTS:
            raise ObsControlError("OBS stream events could not be processed in time")
        self._revision += 1
        self._events.append(StreamEvent(event["outputActive"], event["outputState"], self._revision))

    def _request(self, name: str) -> dict:
        try:
            self._check()
            if not self._identified or name not in _READ_REQUESTS:
                raise ObsControlError("Unsupported OBS control request")
            self._request_id += 1
            request_id = f"{self._request_prefix}-{self._request_id}"
            self._send(6, {"requestType": name, "requestId": request_id})
            deadline = time.monotonic() + REQUEST_TIMEOUT
            while True:
                opcode, data = self._receive(deadline)
                if opcode == 5:
                    self._event(data)
                    continue
                if (opcode != 7 or data.get("requestId") != request_id or data.get("requestType") != name):
                    raise ObsControlError("OBS response did not match the pending request")
                status = data.get("requestStatus")
                if (type(status) is not dict or status.get("result") is not True
                        or type(status.get("code")) is not int or status["code"] != 100
                        or type(data.get("responseData")) is not dict):
                    raise ObsControlError("OBS could not provide the requested status")
                return data["responseData"]
        except BaseException as exc:
            self._failed(exc)

    def _read_version(self) -> None:
        data = self._request("GetVersion")
        requests = data.get("availableRequests")
        if (type(data.get("rpcVersion")) is not int or data["rpcVersion"] != 1
                or type(requests) is not list or len(requests) > 1024
                or any(type(item) is not str or len(item) > 128 for item in requests)
                or not _READ_REQUESTS.issubset(requests)):
            raise ObsControlError("OBS does not support the required status requests")
        websocket_version = _version(data.get("obsWebSocketVersion"))
        if not websocket_version.startswith("5."):
            raise ObsControlError("Unsupported OBS WebSocket version")
        self.version = ObsVersion(_version(data.get("obsVersion")), websocket_version)

    def stream_status(self) -> StreamSnapshot:
        """Read status without arming. Pending events make idle snapshots stale.

        A future native bridge must atomically refuse arming if streaming began
        after this response. WebSocket ordering alone cannot close that race.
        """
        try:
            data = self._request("GetStreamStatus")
            if type(data.get("outputActive")) is not bool or type(data.get("outputReconnecting")) is not bool:
                raise ObsControlError("Invalid OBS stream status")
            return StreamSnapshot(data["outputActive"], data["outputReconnecting"], self._revision, bool(self._events))
        except BaseException as exc:
            self._failed(exc)

    def poll_event(self, timeout: float = 0.1) -> StreamEvent | None:
        """Return one stream event, preserving arrival order; never auto-capture."""
        if type(timeout) not in (float, int) or not 0 < timeout <= REQUEST_TIMEOUT:
            raise ValueError("Invalid OBS event timeout")
        try:
            self._check()
            deadline = time.monotonic() + timeout
            while not self._events:
                opcode, data = self._receive(deadline)
                if opcode != 5:
                    raise ObsControlError("Unexpected OBS control response")
                self._event(data)
            return self._events.popleft()
        except TimeoutError:
            return None
        except BaseException as exc:
            self._failed(exc)

    def _failed(self, exc: BaseException):
        self.close()
        if isinstance(exc, (ObsControlCancelled, obs_websocket.ObsWebSocketCancelled)):
            raise ObsControlCancelled("OBS connection cancelled") from None
        if isinstance(exc, ObsControlError):
            raise exc from None
        if isinstance(exc, TimeoutError):
            raise ObsControlError("OBS status request timed out") from None
        if isinstance(exc, Exception):
            raise ObsControlError("OBS control connection ended unexpectedly") from None
        raise exc

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self._identified = False
        self._events.clear()
        self._transport.close()

    def __enter__(self):
        self._check()
        return self

    def __exit__(self, *_args):
        self.close()
