"""Versioned controller integration with real private routing ownership."""

import io
import threading
from dataclasses import replace

import pytest

from test_obs_controller import Control, Pipe, SESSION, ORIGIN, arm, audio, eventually, start_frame
from utterleaf import capture_store
from utterleaf.config import Config
from utterleaf.obs_control import ObsPluginStatus
from utterleaf.obs_controller import ObsSessionController
from utterleaf.obs_mix import BusLabel, MixSnapshot, SourceAssignment
from utterleaf.obs_protocol import EndFrame, EndReason, RoutingFrame
from utterleaf.obs_routing_store import ObsRoutingStore
from utterleaf.obs_session import ObsCaptureSession
from utterleaf.obs_transcription import ObsTranscriptionCoordinator, ObsTranscriptionError
from utterleaf.transcript import Segment, Transcript


def observation(revision=1):
    return RoutingFrame(
        SESSION, revision, ORIGIN + revision, ((0, revision - 1),),
        MixSnapshot(0, 1, (SourceAssignment(b"s" * 16, f"Private input {revision}", 1),),
                    (BusLabel(0, "Stream"),)),
    )


@pytest.fixture
def session(monkeypatch):
    monkeypatch.setattr(capture_store, "WINDOW_SECONDS", 0.001)
    control, pipe = Control(), Pipe()
    control.plugin_status = lambda: ObsPluginStatus(1, 1, 2, 63)
    histories = []
    journals = []
    recognized = threading.Event()

    def recognize(samples, config, *, cancel):
        assert config.allow_network is False
        recognized.set()
        return Transcript((Segment(0, len(samples) / 16000, "local text"),), "en")

    owner = ObsTranscriptionCoordinator(Config(), recognizer_factory=lambda cfg: recognize,
                                         journal_factory=io.BytesIO)
    journal_factory = io.BytesIO

    def history_factory():
        journal = journal_factory()
        history = ObsRoutingStore(journal_factory=lambda: journal)
        journals.append(journal)
        histories.append(history)
        return history

    def receiver(*args, **kwargs):
        assert kwargs["protocol_version"] == 2
        return ObsCaptureSession(*args, **kwargs, routing_factory=history_factory)

    def connect_pipe(*args, **kwargs):
        assert kwargs["protocol_version"] == 2
        return pipe.connect(*args, **kwargs)

    controller = ObsSessionController(owner, control_factory=control.connect,
                                       pipe_factory=connect_pipe, receiver_factory=receiver)

    def set_journal_factory(factory):
        nonlocal journal_factory
        journal_factory = factory

    yield controller, control, pipe, owner, histories, journals, recognized, set_journal_factory
    controller.cancel()
    assert controller.wait(3), "controller or routing owner did not finish cleanup"
    if any(history.cleanup_failed for history in histories):
        with pytest.raises(ObsTranscriptionError):
            owner.close(3)
    else:
        assert owner.close(3)
    for journal in journals:
        io.BytesIO.close(journal)


def test_routing_updates_flow_through_live_controller_without_audio_gaps(session):
    controller, control, pipe, owner, histories, journals, recognized, _ = session
    arm((controller, control, pipe, owner))
    first, second = observation(), observation(2)
    pipe.batches.put([start_frame(), first, audio()])
    assert recognized.wait(2), "recognition must start before capture ends"
    assert controller.snapshot().routing == first
    assert "Private input" not in repr(controller.snapshot())
    pipe.batches.put([second, audio(1), EndFrame(SESSION, EndReason.STREAM_STOPPED, ((0, 1),))])
    assert controller.wait(3)
    assert controller.snapshot().state == "complete"
    assert controller.snapshot().routing == second
    assert tuple(owner.iter_routing_observations()) == (first, second)
    assert [segment.start for segment in owner.iter_segments()] == pytest.approx([0, 0.001])
    assert len(histories) == 1 and not journals[0].closed
    controller.cancel()
    assert controller.snapshot().routing is None
    assert controller.wait(3) and journals[0].closed
    assert tuple(owner.iter_routing_observations()) == ()


@pytest.mark.parametrize("bad", [None, "revision", "position", "identity"])
def test_unverified_routing_is_never_published_or_transcribed(session, bad):
    controller, control, pipe, owner, histories, _, recognized, _ = session
    arm((controller, control, pipe, owner))
    frame = observation()
    if bad == "revision":
        frame = replace(frame, revision=2)
    elif bad == "position":
        frame = replace(frame, positions=((0, 1),))
    elif bad == "identity":
        frame = replace(frame, session_id=b"x" * 16)
    pipe.batches.put([start_frame(), *([] if bad is None else [frame]), audio()])
    assert controller.wait(3)
    assert controller.snapshot().state == "incomplete"
    assert controller.snapshot().routing is None
    assert not histories and not recognized.is_set()
    assert not tuple(owner.iter_routing_observations())


@pytest.mark.parametrize("after_end", [False, True])
@pytest.mark.parametrize("close_error", [False, True])
def test_cancel_waits_for_history_close_and_reports_late_failure(session, after_end, close_error):
    controller, control, pipe, owner, histories, _, recognized, set_factory = session
    closing, release = threading.Event(), threading.Event()

    class SlowClose(io.BytesIO):
        def close(self):
            closing.set()
            assert release.wait(3), "test did not release history cleanup"
            if close_error:
                raise OSError("private routing path must not escape")
            super().close()

    set_factory(SlowClose)
    try:
        arm((controller, control, pipe, owner))
        pipe.batches.put([start_frame(), observation(), audio()])
        assert recognized.wait(2)
        if after_end:
            pipe.batches.put([EndFrame(SESSION, EndReason.STREAM_STOPPED, ((0, 0),))])
            assert controller.wait(3)
            assert controller.snapshot().state == "complete"
        controller.cancel()
        assert closing.wait(2)
        assert not controller.wait(0)
        assert controller.snapshot().state == "cancelling"
        assert controller.snapshot().routing is None
    finally:
        release.set()
    assert controller.wait(3)
    assert histories[0].wait_closed(0)
    assert controller.snapshot().state == ("error" if close_error else "cancelled")
    assert "private routing path" not in repr(controller.snapshot())


def test_history_write_failure_interrupts_waiting_pipe(session):
    controller, control, pipe, owner, histories, _, _, set_factory = session
    release = threading.Event()

    class FailedWrite(io.BytesIO):
        def write(self, value):
            assert release.wait(3)
            raise OSError("private routing path")

    set_factory(FailedWrite)
    try:
        arm((controller, control, pipe, owner))
        pipe.batches.put([start_frame(), observation()])
        eventually(lambda: controller.snapshot().routing is not None)
        release.set()
        assert controller.wait(3), "borrowed history failure must interrupt an idle pipe read"
        assert owner.failed and controller.snapshot().state == "error"
        assert "private routing path" not in repr(controller.snapshot())
        assert histories[0].failed
    finally:
        release.set()


@pytest.mark.parametrize("version", [None, True, 0, 3, "2"])
def test_unknown_audio_version_never_becomes_armable(session, version):
    controller, control, pipe, owner, histories, *_ = session
    control.plugin_status = lambda: ObsPluginStatus(1, 1, version, 63)
    assert controller.connect("127.0.0.1", 4455, "test", expected_executable="fixture.exe")
    assert controller.wait(3)
    assert controller.snapshot().state == "error"
    assert not controller.arm(b"k" * 32)
    assert not pipe.read_started.is_set() and not histories
