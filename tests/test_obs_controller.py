"""Controller ownership/order tests with the actual receiver and inert peers."""

from enum import Enum
import queue
import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from utterleaf import obs_controller as module
from utterleaf.obs_control import ObsControlCancelled, ObsControlDisconnected, ObsControlError
from utterleaf.obs_control import ObsPluginStatus, StreamEvent, StreamSnapshot
from utterleaf.obs_audio_pipe import ObsAudioPipeCancelled
from utterleaf.obs_protocol import AudioFrame, EndFrame, EndReason, StartFrame
from utterleaf.obs_session import ObsCaptureSession


SESSION = b"c" * 16
ORIGIN = 9_000_000_000


def eventually(predicate, timeout=2):
    deadline = time.monotonic() + timeout
    while not predicate():
        assert time.monotonic() < deadline, "worker did not reach expected state"
        threading.Event().wait(0.002)


class Store:
    created = None

    def __init__(self, rate):
        self.sample_rate = rate
        self.error = None
        self.closed = False
        self.sealed = False
        self.samples = []
        self.created.append(self)

    def append(self, audio):
        assert not self.closed and not self.sealed
        self.samples.extend(audio.tolist())
        return True

    def finish(self):
        self.sealed = True

    def wait_ready(self, cancelled):
        assert self.sealed
        assert not cancelled()

    def close(self):
        self.closed = True


class State(Enum):
    WAITING = "waiting"
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    CANCELLED = "cancelled"
    EMPTY = "empty"


class Sink:
    def __init__(self):
        self.tracks = []
        self.result = None
        self.cancelled = False
        self.state = State.WAITING
        self.failed = False

    def add_track(self, track, **metadata):
        assert not self.cancelled
        self.tracks.append((track, metadata))

    def finish_capture(self, result):
        assert self.result is None
        self.result = result
        result.wait_ready()
        self.state = (State.EMPTY if not result.tracks else State.COMPLETE
                      if result.complete else State.INCOMPLETE)

    def cancel(self):
        self.cancelled = True
        self.state = State.CANCELLED
        if self.result is not None:
            self.result.close()

    def snapshot(self):
        return SimpleNamespace(state=self.state, message="Recognition fixture state")

    def wait(self, timeout=None):
        return True


class Lease:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class Control:
    def __init__(self):
        self.calls = []
        self.events = queue.Queue()
        self.status = StreamSnapshot(False, False, 0, False)
        self.closed = False
        self.cancelled = lambda: False
        self.lease = Lease()
        self.prepare_key = None

    def connect(self, *args, **kwargs):
        self.cancelled = kwargs["cancelled"]
        self.calls.append("connect")
        return self

    def plugin_status(self):
        self.calls.append("status")
        return ObsPluginStatus(1, 1, 1, 63)

    def stream_status(self):
        self.calls.append("idle")
        return self.status

    def retain_peer_process(self):
        self.calls.append("retain")
        return self.lease

    def prepare_session(self, key, **kwargs):
        self.calls.append("prepare")
        self.prepare_key = key
        assert key == b"k" * 32
        return SESSION

    def poll_event(self, timeout):
        if self.cancelled():
            raise ObsControlCancelled("fixture cancellation")
        try:
            result = self.events.get(timeout=timeout)
        except queue.Empty:
            return None
        if isinstance(result, BaseException):
            raise result
        return result

    def started(self, revision=1):
        self.events.put(StreamEvent(True, "OBS_WEBSOCKET_OUTPUT_STARTED", revision))

    def close(self):
        self.closed = True


class Pipe:
    def __init__(self):
        self.batches = queue.Queue()
        self.closed = False
        self.read_started = threading.Event()
        self.disarm_requested = threading.Event()
        self.disarm_count = 0
        self.cancelled = lambda: False
        self.lease = None

    def connect(self, session, lease, **kwargs):
        assert session == SESSION
        self.lease, self.cancelled = lease, kwargs["cancelled"]
        return self

    def arm(self, **kwargs):
        self.mask = kwargs["additional_mix_mask"]

    def read_frames(self):
        self.read_started.set()
        while not self.closed and not self.cancelled():
            try:
                return self.batches.get(timeout=0.005)
            except queue.Empty:
                continue
        raise ObsAudioPipeCancelled("fixture cancellation")

    def request_disarm(self):
        if not self.disarm_requested.is_set():
            self.disarm_count += 1
            self.disarm_requested.set()
        return not self.closed

    def close(self):
        self.closed = True
        if self.lease is not None:
            self.lease.close()


@pytest.fixture
def setup_session():
    Store.created = []
    control, pipe, sink = Control(), Pipe(), Sink()
    controller = module.ObsSessionController(
        sink, control_factory=control.connect, pipe_factory=pipe.connect,
        receiver_factory=lambda *a, **kw: ObsCaptureSession(*a, **kw, store_factory=Store))
    yield controller, control, pipe, sink
    controller.cancel()
    assert controller.wait(2), "controller leaked a worker"
    if sink.result is not None:
        sink.result.close()


def arm(setup, mask=0):
    controller, control, pipe, sink = setup
    assert controller.connect("127.0.0.1", 4455, "test-password", expected_executable="fixture.exe")
    eventually(lambda: controller.snapshot().state == "ready")
    assert controller.arm(b"k" * 32, additional_mix_mask=mask)
    assert not controller.arm(b"k" * 32)
    assert pipe.read_started.wait(2)
    return controller, control, pipe, sink


def start_frame(primary=0, mask=1):
    return StartFrame(SESSION, 16000, primary, mask, ORIGIN)


def audio(sequence=0, bus=0, offset=0):
    pcm = np.array([[0.2, 0.4]] * 16, dtype="<f4").tobytes()
    return AudioFrame(SESSION, bus, sequence, ORIGIN + offset + sequence * 1_000_000, 16, pcm)


def test_connect_is_inert_and_never_prepares_or_opens_stores(setup_session):
    controller, control, pipe, sink = setup_session
    assert controller.snapshot().state == "disabled"
    assert controller.connect("127.0.0.1", 4455, "test-password", expected_executable="fixture.exe")
    eventually(lambda: controller.snapshot().state == "ready")
    assert control.calls == ["connect", "status", "idle"]
    assert not Store.created and not pipe.read_started.is_set()
    assert not controller.connect("127.0.0.1", 4455, "again", expected_executable="fixture.exe")


@pytest.mark.parametrize("audio_first", [True, False])
def test_channel_orderings_preserve_entire_start_audio_end_batch(setup_session, audio_first):
    controller, control, pipe, sink = arm(setup_session)
    batch = [start_frame(), audio(), EndFrame(SESSION, EndReason.STREAM_STOPPED, ((0, 0),))]
    if audio_first:
        pipe.batches.put(batch)
        assert controller.wait(2)
        control.started()
    else:
        control.started()
        pipe.batches.put(batch)
    assert controller.wait(2)
    assert controller.snapshot().state == "complete"
    assert control.calls.index("retain") < control.calls.index("prepare")
    assert control.prepare_key == b"\0" * 32
    assert len(sink.tracks) == 1
    assert sink.result.complete and sink.result.tracks[0].received_frames == 16
    assert not sink.result.tracks[0].store.closed  # ownership was transferred
    assert control.closed and pipe.closed and control.lease.closed


def test_indefinite_armed_wait_can_disarm_without_control_event(setup_session):
    controller, control, pipe, sink = arm(setup_session)
    assert controller.disarm()
    assert controller.disarm()
    assert pipe.disarm_count == 1
    pipe.batches.put([EndFrame(SESSION, EndReason.DISARMED, ())])
    assert controller.wait(2)
    assert controller.snapshot().state == "empty"
    assert not Store.created and not sink.result.complete
    assert not controller.disarm()


def test_active_control_loss_keeps_verified_pipe_and_preserves_tail(setup_session):
    controller, control, pipe, sink = arm(setup_session)
    control.started()
    pipe.batches.put([start_frame(), audio()])
    eventually(lambda: controller.snapshot().state == "active")
    control.events.put(ObsControlDisconnected("connection closed"))
    eventually(lambda: controller.snapshot().control_degraded)
    assert not pipe.closed and not sink.cancelled
    assert controller.disarm()
    pipe.batches.put([audio(1), EndFrame(SESSION, EndReason.DISARMED, ((0, 1),))])
    assert controller.wait(2)
    assert sink.result.complete and sink.result.tracks[0].received_frames == 32
    assert controller.snapshot().control_degraded


@pytest.mark.parametrize("failure", [ObsControlError("untrusted secret payload"),
                                     ObsControlDisconnected("connection closed")])
def test_pre_start_control_failure_stops_without_accepting_audio(setup_session, failure):
    controller, control, pipe, sink = arm(setup_session)
    control.events.put(failure)
    assert controller.wait(2)
    pipe.batches.put([start_frame(), audio()])
    assert not Store.created and not sink.tracks
    assert not sink.result.complete
    assert not controller.snapshot().control_degraded
    assert "secret payload" not in repr(controller.snapshot())


def test_active_identity_or_protocol_failure_is_incomplete_not_degraded(setup_session):
    controller, control, pipe, sink = arm(setup_session)
    control.started()
    pipe.batches.put([start_frame(), audio()])
    eventually(lambda: controller.snapshot().state == "active")
    control.events.put(ObsControlError("identity mismatch"))
    assert controller.wait(2)
    assert controller.snapshot().state == "incomplete"
    assert not controller.snapshot().control_degraded
    assert sink.result.tracks[0].received_frames == 16


def test_cancel_discards_live_borrowed_stores_and_never_rearms(setup_session):
    controller, control, pipe, sink = arm(setup_session)
    control.started()
    pipe.batches.put([start_frame(), audio()])
    eventually(lambda: controller.snapshot().state == "active")
    controller.cancel()
    assert controller.wait(2)
    assert controller.snapshot().state == "cancelled"
    assert all(store.closed for store in Store.created)
    assert not controller.arm(b"k" * 32)
    assert not controller.connect("127.0.0.1", 4455, "again", expected_executable="fixture.exe")


def test_mixed_and_additional_bus_first_offsets_reach_recognition(setup_session):
    controller, control, pipe, sink = arm(setup_session, mask=1 << 2)
    control.started()
    pipe.batches.put([start_frame(mask=5), audio(), audio(bus=2, offset=20_000_000),
                      EndFrame(SESSION, EndReason.STREAM_STOPPED, ((0, 0), (2, 0)))])
    assert controller.wait(2)
    assert [track.bus for track, _ in sink.tracks] == [0, 2]
    assert sink.tracks[1][0].first_timestamp_ns == ORIGIN + 20_000_000
    assert all(meta == {"origin_ns": ORIGIN, "sample_rate": 16000, "primary_bus": 0}
               for _, meta in sink.tracks)


def test_old_websocket_lifecycle_queued_during_arm_cannot_authorize_or_stop_epoch(setup_session):
    controller, control, pipe, sink = setup_session
    original_arm = pipe.arm
    def old_lifecycle_during_arm(**kwargs):
        control.events.put(StreamEvent(False, "OBS_WEBSOCKET_OUTPUT_STARTING", 1))
        control.started(revision=2)
        control.events.put(StreamEvent(True, "OBS_WEBSOCKET_OUTPUT_STOPPING", 3))
        control.events.put(StreamEvent(False, "OBS_WEBSOCKET_OUTPUT_STOPPED", 4))
        original_arm(**kwargs)
    pipe.arm = old_lifecycle_during_arm
    arm(setup_session)
    eventually(lambda: control.events.empty())
    assert controller.snapshot().state == "armed"
    assert not Store.created
    pipe.batches.put([start_frame(), audio()])
    eventually(lambda: controller.snapshot().state == "active")
    control.started(revision=5)
    control.events.put(StreamEvent(False, "OBS_WEBSOCKET_OUTPUT_STOPPED", 6))
    eventually(lambda: control.events.empty())
    assert controller.snapshot().state == "active" and not pipe.closed
    pipe.batches.put([audio(1), EndFrame(SESSION, EndReason.STREAM_STOPPED, ((0, 1),))])
    assert controller.wait(2)
    assert sink.result.complete and sink.result.tracks[0].received_frames == 32


def test_stream_start_race_before_prepare_does_not_consume_key(setup_session):
    controller, control, pipe, sink = setup_session
    controller.connect("127.0.0.1", 4455, "test-password", expected_executable="fixture.exe")
    eventually(lambda: controller.snapshot().state == "ready")
    control.status = StreamSnapshot(True, False, 1, False)
    assert controller.arm(b"k" * 32)
    assert controller.wait(2)
    assert "prepare" not in control.calls and "retain" not in control.calls
    assert not Store.created and not pipe.read_started.is_set()


def test_connection_worker_start_failure_cancels_sink_and_finishes(setup_session, monkeypatch):
    controller, control, pipe, sink = setup_session
    def fail_start(self):
        raise RuntimeError("thread allocation failed")
    monkeypatch.setattr(threading.Thread, "start", fail_start)
    assert not controller.connect("127.0.0.1", 4455, "test-password", expected_executable="fixture.exe")
    assert sink.cancelled and controller.wait(0)
    assert controller.snapshot().state == "error"


@pytest.mark.parametrize("degraded", [False, True])
def test_recognition_failure_stops_capture_even_without_further_pcm(setup_session, degraded):
    controller, control, pipe, sink = arm(setup_session)
    control.started()
    pipe.batches.put([start_frame(), audio()])
    eventually(lambda: controller.snapshot().state == "active")
    if degraded:
        control.events.put(ObsControlDisconnected("connection closed"))
        eventually(lambda: controller.snapshot().control_degraded)
    sink.failed = True
    assert controller.wait(2)
    assert pipe.closed and not sink.result.complete
    assert controller.snapshot().state != "active"


def test_cancel_wins_between_native_arm_and_controller_publication(setup_session):
    controller, control, pipe, sink = setup_session
    original_arm = pipe.arm
    def cancel_during_arm(**kwargs):
        original_arm(**kwargs)
        controller.cancel()
    pipe.arm = cancel_during_arm
    assert controller.connect("127.0.0.1", 4455, "test-password", expected_executable="fixture.exe")
    eventually(lambda: controller.snapshot().state == "ready")
    assert controller.arm(b"k" * 32)
    assert controller.wait(2)
    assert controller.snapshot().state == "cancelled"
    assert pipe.closed and control.lease.closed
    assert not Store.created


def test_cancel_wins_during_track_registration(setup_session):
    controller, control, pipe, sink = arm(setup_session)
    original_add = sink.add_track
    def cancel_during_add(*args, **kwargs):
        original_add(*args, **kwargs)
        controller.cancel()
    sink.add_track = cancel_during_add
    control.started()
    pipe.batches.put([start_frame(), audio()])
    assert controller.wait(2)
    assert controller.snapshot().state == "cancelled"
    assert all(store.closed for store in Store.created)


def test_control_close_failure_cannot_strand_wait_or_key_cleanup(setup_session):
    controller, control, pipe, sink = setup_session
    def fail_close():
        raise RuntimeError("private remote detail")
    control.close = fail_close
    control.events.put(ObsControlError("connection failure"))
    assert controller.connect("127.0.0.1", 4455, "test-password", expected_executable="fixture.exe")
    assert controller.wait(2)
    assert sink.cancelled and controller._key is None
    assert controller.snapshot().state == "error"
    assert "private remote detail" not in repr(controller.snapshot())


def test_audio_worker_start_failure_closes_pipe_lease_and_recognition(setup_session, monkeypatch):
    original_start = threading.Thread.start
    def fail_audio_start(self):
        if self.name == "utterleaf-obs-audio":
            raise RuntimeError("audio thread allocation failed")
        original_start(self)
    monkeypatch.setattr(threading.Thread, "start", fail_audio_start)
    controller, control, pipe, sink = setup_session
    controller.connect("127.0.0.1", 4455, "test-password", expected_executable="fixture.exe")
    eventually(lambda: controller.snapshot().state == "ready")
    assert controller.arm(b"k" * 32)
    assert controller.wait(2)
    assert pipe.closed and control.lease.closed and sink.cancelled
    assert control.prepare_key == b"\0" * 32


@pytest.mark.parametrize("end", ["complete", "cancel", "failure", "empty", "pre_start_failure", "cleanup_failure"])
def test_actual_controller_coordinator_and_store_lifecycle(monkeypatch, end):
    import io
    from utterleaf import capture_store
    from utterleaf.config import Config
    from utterleaf.obs_transcription import ObsTranscriptionCoordinator, ObsTranscriptionError
    from utterleaf.transcript import Segment, Transcript

    monkeypatch.setattr(capture_store, "WINDOW_SECONDS", 0.001)
    recognized = threading.Event()
    calls = []
    def recognize(samples, config, *, cancel):
        calls.append((len(samples), config.allow_network))
        recognized.set()
        if end == "failure":
            raise RuntimeError("private model detail")
        return Transcript((Segment(0, len(samples) / 16000, "local text"),), "en")
    class CloseFailure(io.BytesIO):
        def close(self):
            raise OSError("private cleanup detail")

    journal = CloseFailure() if end == "cleanup_failure" else None
    journal_options = {"journal_factory": lambda: journal} if journal is not None else {}
    sink = ObsTranscriptionCoordinator(Config(), recognizer_factory=lambda cfg: recognize,
                                       **journal_options)
    control, pipe = Control(), Pipe()
    controller = module.ObsSessionController(sink, control_factory=control.connect,
                                             pipe_factory=pipe.connect)
    try:
        arm((controller, control, pipe, sink))
        if end == "empty":
            assert controller.disarm()
            pipe.batches.put([EndFrame(SESSION, EndReason.DISARMED, ())])
        elif end == "pre_start_failure":
            control.events.put(ObsControlError("identity failure"))
        else:
            pipe.batches.put([start_frame(), audio()])
            assert recognized.wait(2), "real live store must reach recognition before End"
            if end == "cancel":
                controller.cancel()
            elif end in {"complete", "cleanup_failure"}:
                # The second committed window reaches the same async worker,
                # then the native End transfers final store ownership.
                pipe.batches.put([audio(1), EndFrame(SESSION, EndReason.STREAM_STOPPED, ((0, 1),))])
        assert controller.wait(3), "controller/coordinator lifecycle did not drain"
        state = controller.snapshot().state
        if end in {"complete", "cleanup_failure"}:
            assert state == "complete"
            segments = list(sink.iter_segments())
            assert [segment.start for segment in segments] == pytest.approx([0, 0.001])
            assert [segment.text for segment in segments] == ["local text", "local text"]
            assert calls == [(16, False), (16, False)]
            controller.cancel()
            assert controller.wait(3), "discard cleanup did not finish"
            if end == "cleanup_failure":
                assert controller.snapshot().state == "error"
                assert "cleanup failed" in controller.snapshot().message
                assert "private cleanup detail" not in controller.snapshot().message
                assert sink.snapshot().preview == ""
            else:
                assert controller.snapshot().state == "cancelled"
            assert list(sink.iter_segments()) == []
        elif end == "empty":
            assert state == "empty" and not calls
        elif end == "pre_start_failure":
            assert state == "incomplete" and not calls
        elif end == "cancel":
            assert state == "cancelled" and list(sink.iter_segments()) == []
        else:
            assert state == "error" and sink.failed
            assert "private model detail" not in sink.snapshot().message
        assert control.closed and pipe.closed and control.lease.closed
    finally:
        controller.cancel()
        assert controller.wait(3)
        if journal is not None:
            try:
                with pytest.raises(ObsTranscriptionError, match="could not be deleted"):
                    sink.close(3)
            finally:
                io.BytesIO.close(journal)
        else:
            assert sink.close(3)
