"""Explicit OBS session ownership; no connection or capture on construction.

The control worker and the single pipe/receiver worker are independent. UI methods
only publish intent. The transcription sink registers borrowed live stores, then
owns the final capture result after a successful finish_capture call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import threading
import time
from typing import Protocol

from utterleaf import obs_audio_pipe, obs_control
from utterleaf.obs_protocol import AudioFrame, EndFrame, StartFrame
from utterleaf.obs_session import ObsCaptureSession, ObsSessionError


STOP_TIMEOUT = 7.0
POLL_SECONDS = 0.05


class TranscriptionSink(Protocol):
    @property
    def failed(self) -> bool: ...
    def add_track(self, track, *, origin_ns: int, sample_rate: int,
                  primary_bus: int) -> None: ...
    def finish_capture(self, result) -> None: ...
    def cancel(self) -> None: ...
    def wait(self, timeout: float | None = None) -> bool: ...
    def snapshot(self): ...


@dataclass(frozen=True)
class ObsControllerSnapshot:
    state: str
    message: str
    control_degraded: bool = False
    primary_bus: int | None = None
    buses: tuple[int, ...] = ()
    captured_seconds: float = 0.0


@dataclass
class _ConnectionRequest:
    host: str
    port: int
    password: str = field(repr=False)
    expected_executable: str = field(repr=False)


class _Cancelled(Exception):
    pass


class _SessionFailure(Exception):
    pass


class ObsSessionController:
    """One explicit connection and at most one manually armed capture.

    Reconnection requires a fresh controller and deliberate user action. Call
    cancel/close without blocking the UI; wait is for a cleanup worker or tests.
    The caller owns the transcription sink and closes its transcript journal.
    """

    def __init__(self, transcription: TranscriptionSink, *,
                 control_factory=obs_control.ObsControl.connect,
                 pipe_factory=obs_audio_pipe.connect,
                 receiver_factory=ObsCaptureSession):
        self._sink = transcription
        self._control_factory = control_factory
        self._pipe_factory = pipe_factory
        self._receiver_factory = receiver_factory
        self._condition = threading.Condition()
        self._abort = threading.Event()
        self._fatal = threading.Event()
        self._control_done = threading.Event()
        self._audio_done = threading.Event()
        self._audio_ended = threading.Event()
        self._control_done.set()
        self._audio_done.set()
        self._state = "disabled"
        self._message = "OBS transcription is off."
        self._used = False
        self._armed = False
        self._audio_started = False
        self._active = False
        self._degraded = False
        self._disarm = False
        self._stop_deadline: float | None = None
        self._failure = ""
        self._key: bytearray | None = None
        self._mask = 0
        self._primary: int | None = None
        self._buses: tuple[int, ...] = ()
        self._seconds = 0.0
        self._pipe = None

    def snapshot(self) -> ObsControllerSnapshot:
        with self._condition:
            state, message = self._state, self._message
            degraded, primary, buses, seconds = (
                self._degraded, self._primary, self._buses, self._seconds)
        if state == "finalizing":
            recognition = self._sink.snapshot()
            terminal = recognition.state.value
            if terminal in {"complete", "incomplete", "empty", "failed", "cancelled"}:
                state = "error" if terminal == "failed" else terminal
                message = recognition.message
        if state == "cancelling" and self.wait(0):
            recognition = self._sink.snapshot()
            if recognition.state.value == "failed":
                state, message = "error", recognition.message
            else:
                state, message = "cancelled", "OBS transcription discarded."
        return ObsControllerSnapshot(state, message, degraded, primary, buses, seconds)

    def connect(self, host: str, port: int, password: str, *,
                expected_executable: str) -> bool:
        with self._condition:
            if self._used or self._abort.is_set():
                return False
            self._used = True
            self._state, self._message = "connecting", "Connecting to local OBS…"
            self._control_done.clear()
            self._audio_done.clear()
        request = _ConnectionRequest(host, port, password, expected_executable)
        try:
            threading.Thread(target=self._control_worker, args=(request,),
                             name="utterleaf-obs-control", daemon=True).start()
        except BaseException:
            request.password = ""
            self._sink.cancel()
            self._publish("error", "Could not start the OBS connection worker.")
            self._control_done.set()
            self._audio_done.set()
            return False
        return True

    def arm(self, key: bytes | bytearray, *, additional_mix_mask: int = 0) -> bool:
        if (type(key) not in (bytes, bytearray) or len(key) != 32 or not any(key)
                or type(additional_mix_mask) is not int or not 0 <= additional_mix_mask <= 63):
            raise ValueError("Invalid local OBS pairing or mix selection")
        with self._condition:
            if self._state != "ready" or self._key is not None or self._abort.is_set():
                return False
            self._key, self._mask = bytearray(key), additional_mix_mask
            self._state, self._message = "preparing", "Preparing the selected OBS mixes…"
            self._condition.notify_all()
            return True

    def disarm(self) -> bool:
        with self._condition:
            if not self._armed or self._audio_ended.is_set() or self._audio_done.is_set():
                return False
            if self._abort.is_set() or self._fatal.is_set():
                return False
            self._disarm = True
            if self._stop_deadline is None:
                self._stop_deadline = time.monotonic() + STOP_TIMEOUT
            self._state, self._message = "stopping", "Stopping transcription; OBS keeps streaming…"
            pipe = self._pipe
            self._condition.notify_all()
        # request_disarm is a lock-only intent API, never a native write.
        return pipe.request_disarm() if pipe is not None else False

    def cancel(self) -> None:
        self._abort.set()
        with self._condition:
            self._state, self._message = "cancelling", "Discarding OBS transcription…"
            self._condition.notify_all()
        self._sink.cancel()

    close = cancel

    def wait(self, timeout: float | None = None) -> bool:
        deadline = None if timeout is None else time.monotonic() + max(0.0, timeout)
        remaining = lambda: None if deadline is None else max(0.0, deadline - time.monotonic())
        return (self._control_done.wait(remaining()) and self._audio_done.wait(remaining())
                and self._sink.wait(remaining()))

    def _publish(self, state: str, message: str) -> None:
        with self._condition:
            if not self._abort.is_set():
                self._state, self._message = state, message
            self._condition.notify_all()

    def _check(self) -> None:
        if self._abort.is_set():
            raise _Cancelled()
        if self._audio_cancelled():
            raise _SessionFailure()

    def _audio_cancelled(self) -> bool:
        if self._abort.is_set() or self._fatal.is_set():
            return True
        # This is a lock-free signal, including while a pipe read is waiting and
        # the control worker has already exited after ordinary disconnection.
        if self._sink.failed:
            self._fail("Local transcription failed. Capture stopped; its prefix is incomplete.")
            return True
        return False

    def _fail(self, message: str) -> None:
        with self._condition:
            if not self._failure:
                self._failure = message
            self._fatal.set()
            self._condition.notify_all()

    def _idle_snapshot(self, control, *, publish: bool) -> bool:
        status = control.stream_status()
        idle = not status.active and not status.reconnecting and not status.events_pending
        if publish:
            self._publish("ready" if idle else "busy", "Ready. Arm for the next OBS stream."
                          if idle else "Wait for OBS streaming to stop before arming.")
        return idle

    def _control_worker(self, request: _ConnectionRequest) -> None:
        control = None
        try:
            try:
                control = self._control_factory(
                    request.host, request.port, request.password,
                    expected_executable=request.expected_executable,
                    cancelled=self._abort.is_set)
            finally:
                # The Thread retains its argument object until exit, so clear the
                # credential there immediately after the handshake, not on exit.
                request.password = ""
            self._check()
            control.plugin_status()
            self._check()
            refresh_idle = not self._idle_snapshot(control, publish=True)
            while not self._audio_ended.is_set():
                self._check()
                with self._condition:
                    key, self._key = self._key, None
                if key is not None:
                    try:
                        self._perform_arm(control, key)
                    finally:
                        key[:] = b"\0" * len(key)
                if self._audio_started and self._audio_done.is_set():
                    break
                with self._condition:
                    overdue = self._stop_deadline is not None and time.monotonic() >= self._stop_deadline
                if overdue:
                    raise _SessionFailure()
                event = control.poll_event(POLL_SECONDS)
                if event is None:
                    if not self._armed and refresh_idle:
                        refresh_idle = not self._idle_snapshot(control, publish=True)
                    continue
                if not self._armed:
                    self._publish("busy", "Wait for OBS streaming to stop before arming.")
                    refresh_idle = True
                    continue
                # Standard WebSocket lifecycle events have no native session
                # identifier. A complete older lifecycle can arrive late while
                # Arm is in flight. Only this authenticated pipe's native Start
                # and End authorize/finish the current epoch. Keep receiving
                # control traffic so identity, protocol and OBS Exit failures
                # are still terminal; never rearm or time out this epoch from
                # an untagged STARTED/STOPPED event.
        except obs_control.ObsControlDisconnected:
            with self._condition:
                degraded = self._active and not self._audio_cancelled()
                if degraded and not self._audio_ended.is_set():
                    self._degraded = True
                    if self._state == "active":
                        self._message = "OBS controls disconnected. Audio transcription continues."
            if not degraded and not self._audio_ended.is_set():
                self._fail("OBS controls disconnected before transcription began.")
        except _Cancelled:
            pass
        except BaseException:
            if not self._abort.is_set() and not self._audio_ended.is_set():
                self._fail("OBS control could not be verified or continued. Reconnect explicitly.")
        finally:
            request.password = ""
            if control is not None:
                try:
                    control.close()
                except BaseException:
                    self._fail("The OBS control connection could not close cleanly.")
            with self._condition:
                if self._key is not None:
                    self._key[:] = b"\0" * len(self._key)
                    self._key = None
            if not self._audio_started:
                self._audio_done.set()
                self._sink.cancel()
                if self._failure:
                    self._publish("error", self._failure)
            self._control_done.set()

    def _perform_arm(self, control, key: bytearray) -> None:
        lease = pipe = None
        try:
            self._check()
            if not self._idle_snapshot(control, publish=False):
                self._fail("OBS began streaming before Arm. Reconnect while the stream is stopped.")
                raise _SessionFailure()
            lease = control.retain_peer_process()
            self._check()
            session_id = control.prepare_session(key, additional_mix_mask=self._mask)
            self._check()
            owned_lease, lease = lease, None
            pipe = self._pipe_factory(session_id, owned_lease, cancelled=self._audio_cancelled,
                                      deadline=time.monotonic() + obs_control.REQUEST_TIMEOUT)
            pipe.arm(additional_mix_mask=self._mask,
                     deadline=time.monotonic() + obs_control.REQUEST_TIMEOUT)
            self._check()
            with self._condition:
                self._check()
                self._pipe = pipe
                self._armed = True
                self._state, self._message = "armed", "Waiting for the next OBS stream to start…"
            worker = threading.Thread(target=self._audio_worker, args=(session_id, pipe, self._mask),
                                      name="utterleaf-obs-audio", daemon=True)
            worker.start()
            self._audio_started = True
            pipe = None  # The pipe worker now owns close and receiver mutation.
        finally:
            if pipe is not None:
                pipe.close()
            if lease is not None:
                lease.close()

    def _audio_worker(self, session_id: bytes, pipe, mask: int) -> None:
        receiver = result = None
        registered: set[int] = set()
        origin_ns = sample_rate = 0
        try:
            receiver = self._receiver_factory(
                session_id, buses=tuple(bus for bus in range(6) if mask & (1 << bus)),
                stream_active=False)
            while receiver.state in {"armed", "active"}:
                self._check()
                frames = pipe.read_frames()
                for frame in frames:
                    self._check()
                    if isinstance(frame, StartFrame):
                        # The verified native endpoint emits this session-bound
                        # proof only after its complete Arm reply and a later
                        # native frontend start. Untagged WebSocket events are
                        # not epoch proof and cannot authorize this transition.
                        receiver.notify_stream_started(frame.session_id)
                        origin_ns, sample_rate = frame.origin_ns, frame.sample_rate
                    receiver.accept(frame)
                    if isinstance(frame, AudioFrame):
                        tracks = receiver.live_tracks()
                        for track in tracks:
                            if track.bus not in registered:
                                self._sink.add_track(track, origin_ns=origin_ns,
                                                     sample_rate=sample_rate,
                                                     primary_bus=receiver.primary_bus)
                                registered.add(track.bus)
                        with self._condition:
                            self._check()
                            self._primary, self._buses = receiver.primary_bus, receiver.buses
                            self._active = self._primary in registered
                            self._seconds = max(self._seconds, max(
                                ((track.first_timestamp_ns - origin_ns) / 1_000_000_000
                                 + track.received_frames / sample_rate) for track in tracks))
                            if self._active and not self._disarm and self._stop_deadline is None:
                                self._state = "active"
                                self._message = ("OBS controls disconnected. Audio transcription continues."
                                                 if self._degraded else "Transcribing the OBS stream locally…")
                    if isinstance(frame, EndFrame):
                        self._audio_ended.set()
            result = receiver.take_result()
        except BaseException:
            if self._abort.is_set():
                self._sink.cancel()
            else:
                if not self._failure:
                    self._fail("OBS audio or local transcription was interrupted. Only its prefix can be recovered.")
                if receiver is not None:
                    if receiver.state in {"armed", "active"}:
                        try:
                            receiver.connection_lost()
                        except ObsSessionError:
                            pass
                    if receiver.state in {"finished", "incomplete"}:
                        result = receiver.take_result()
        finally:
            close_failed = False
            try:
                pipe.close()
            except BaseException:
                close_failed = True
                self._fail("The OBS audio connection could not close cleanly.")
            try:
                if close_failed:
                    self._sink.cancel()
                    self._publish("error", self._failure)
                elif result is not None and not self._abort.is_set():
                    self._publish("finalizing", "Finishing local transcription…")
                    self._sink.finish_capture(result)
                    result = None
                elif not self._abort.is_set():
                    self._sink.cancel()
                    self._publish("error", self._failure or "OBS capture could not start.")
            except BaseException:
                self._sink.cancel()
                self._publish("error", "OBS transcription could not finish. No complete transcript was produced.")
            finally:
                try:
                    if result is not None:
                        result.close()
                finally:
                    try:
                        if receiver is not None:
                            receiver.close()
                    finally:
                        self._audio_done.set()
