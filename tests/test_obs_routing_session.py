"""Routing observations obey session authority without changing PCM continuity."""

from dataclasses import replace
import struct

import pytest

from utterleaf.obs_mix import BusLabel, MixSnapshot, SourceAssignment
from utterleaf.obs_protocol import AudioFrame, EndFrame, EndReason, RoutingFrame, StartFrame
from utterleaf.obs_session import ObsCaptureSession, ObsSessionError


SESSION = b"0123456789abcdef"
ORIGIN = 5_000_000_000


class AudioStore:
    def __init__(self, rate):
        self.error = None
        self.closed = False
        self.finished = False
        self.samples = 0

    def append(self, samples):
        self.samples += len(samples)
        return True

    def finish(self):
        self.finished = True

    def wait_ready(self, cancelled):
        assert self.finished
        assert not cancelled()

    def close(self):
        self.closed = True


class History:
    def __init__(self):
        self.error = None
        self.records = []
        self.finished = False
        self.closed = False
        self.reject = False
        self.ready_calls = 0
        self.cleanup_ready = True

    def append(self, frame):
        if self.reject:
            return False
        self.records.append(frame)
        return True

    def finish(self):
        self.finished = True

    def wait_ready(self, cancelled):
        self.ready_calls += 1
        assert self.finished
        if self.error:
            raise self.error

    def close(self):
        self.closed = True

    def wait_closed(self, timeout=None):
        return self.closed and self.cleanup_ready


def observation(revision=1, *, observed=10, positions=((0, 0), (2, 0)), name="Guest"):
    return RoutingFrame(
        SESSION, revision, observed, positions,
        MixSnapshot(0, 5, (SourceAssignment(bytes(16), name, 5),),
                    (BusLabel(0, "Stream"), BusLabel(2, "Guest bus"))),
    )


def audio(bus=0, sequence=0, timestamp=ORIGIN):
    return AudioFrame(SESSION, bus, sequence, timestamp, 480,
                      struct.pack("<ff", 0.2, -0.1) * 480)


def started(*, version=2, factory=History):
    receiver = ObsCaptureSession(SESSION, buses=(2,), stream_active=False,
                                 store_factory=AudioStore, protocol_version=version,
                                 routing_factory=factory)
    receiver.notify_stream_started(SESSION)
    receiver.accept(StartFrame(SESSION, 48000, 0, 5, ORIGIN))
    return receiver


def test_routing_preserves_continuous_audio_and_prior_immutable_observations():
    receiver = started()
    first = observation()
    second = observation(2, observed=11, positions=((0, 1), (2, 1)), name="Renamed guest")
    receiver.accept(first)
    receiver.accept(audio())
    receiver.accept(audio(2))
    receiver.accept(second)
    receiver.accept(audio(0, 1, ORIGIN + 10_000_000))
    receiver.accept(audio(2, 1, ORIGIN + 10_000_000))
    receiver.accept(EndFrame(SESSION, EndReason.STREAM_STOPPED, ((0, 1), (2, 1))))
    result = receiver.take_result()
    receiver.close()
    result.wait_ready()
    assert result.complete
    assert [track.received_frames for track in result.tracks] == [960, 960]
    assert result.routing_history.records == [first, second]
    assert first.snapshot.sources[0].name == "Guest"
    assert not result.routing_history.closed
    result.close()
    assert result.wait_closed(0)


@pytest.mark.parametrize("frame", [
    audio(),
    EndFrame(SESSION, EndReason.DISARMED, ((0, None), (2, None))),
])
def test_v2_requires_initial_observation_before_audio_or_nonempty_end(frame):
    receiver = started(factory=lambda: pytest.fail("No history without valid Routing"))
    with pytest.raises(ObsSessionError, match="initial mix observation"):
        receiver.accept(frame)
    result = receiver.take_result()
    assert all(track.received_frames == 0 for track in result.tracks)
    result.close()
    receiver.close()


def test_pre_start_disarm_creates_neither_audio_nor_history():
    fail = lambda *args: pytest.fail("No stores before Start")
    receiver = ObsCaptureSession(SESSION, buses=(2,), stream_active=False,
                                 protocol_version=2, store_factory=fail, routing_factory=fail)
    receiver.accept(EndFrame(SESSION, EndReason.DISARMED, ()))
    result = receiver.take_result()
    result.wait_ready()
    assert result.empty
    assert result.routing_history is None
    result.close()
    receiver.close()


@pytest.mark.parametrize("field,value", [
    ("session_id", b"fedcba9876543210"), ("revision", 2),
    ("positions", ((0, 1), (2, 0))),
    ("snapshot", MixSnapshot(2, 5, (), (BusLabel(0, "A"), BusLabel(2, "B")))),
    ("snapshot", MixSnapshot(0, 1, (), (BusLabel(0, "A"),))),
])
def test_invalid_initial_observation_never_creates_history(field, value):
    receiver = started(factory=lambda: pytest.fail("Invalid observation opened history"))
    kwargs = {field: value}
    if field == "snapshot" and value.bus_mask == 1:
        kwargs["positions"] = ((0, 0),)
    with pytest.raises(ObsSessionError):
        receiver.accept(replace(observation(), **kwargs))
    assert receiver.current_routing is None
    assert receiver.routing_history is None
    receiver.close()


@pytest.mark.parametrize("changes", [
    {"revision": 1}, {"revision": 3}, {"observed_at_ns": 9},
    {"positions": ((0, 0), (2, 0))}, {"positions": ((0, 2), (2, 0))},
    {"session_id": b"fedcba9876543210"},
])
def test_bad_update_retains_only_previous_observation_and_audio(changes):
    receiver = started()
    first = observation()
    receiver.accept(first)
    receiver.accept(audio())
    history = receiver.routing_history
    update = observation(2, observed=11, positions=((0, 1), (2, 0)))
    with pytest.raises(ObsSessionError):
        receiver.accept(replace(update, **changes))
    assert history.records == [first]
    assert receiver.current_routing is first
    assert receiver.state == "incomplete"
    result = receiver.take_result()
    assert result.tracks[0].received_frames == 480
    result.close()
    receiver.close()


def test_equal_observation_clock_is_allowed_and_no_sample_effective_time_is_guessed():
    receiver = started()
    receiver.accept(observation(observed=0))
    receiver.accept(audio())
    receiver.accept(observation(2, observed=0, positions=((0, 1), (2, 0))))
    receiver.accept(audio(0, 1, ORIGIN + 10_000_000))
    assert len(receiver.routing_history.records) == 2
    receiver.close()


def test_v1_refuses_routing_and_does_not_open_metadata_storage():
    receiver = started(version=1, factory=lambda: pytest.fail("v1 metadata storage"))
    with pytest.raises(ObsSessionError):
        receiver.accept(observation())
    receiver.close()


def test_metadata_failure_never_commits_the_rejected_revision():
    receiver = started()
    first = observation()
    receiver.accept(first)
    history = receiver.routing_history
    history.reject = True
    with pytest.raises(ObsSessionError, match="could not keep up"):
        receiver.accept(observation(2, observed=11))
    assert receiver.current_routing is first
    assert history.records == [first]
    assert history.finished
    receiver.close()


def test_factory_failure_is_generic_and_does_not_chain_private_exception():
    def fail():
        raise OSError("private location")
    receiver = started(factory=fail)
    with pytest.raises(ObsSessionError) as caught:
        receiver.accept(observation())
    assert "private" not in str(caught.value)
    assert caught.value.__suppress_context__
    receiver.close()


def test_late_history_failure_prevents_complete_result_and_more_audio():
    receiver = started()
    receiver.accept(observation())
    receiver.routing_history.error = OSError("private storage failure")
    with pytest.raises(ObsSessionError, match="history could not be preserved"):
        receiver.accept(audio())
    result = receiver.take_result()
    assert not result.complete
    assert "private" not in result.reason
    result.close()
    receiver.close()


def test_history_transfer_survives_audio_close_and_cannot_repeat():
    receiver = started()
    receiver.accept(observation())
    receiver.accept(audio())
    receiver.accept(audio(2))
    receiver.accept(EndFrame(SESSION, EndReason.DISARMED, ((0, 0), (2, 0))))
    result = receiver.take_result()
    history = result.take_routing_history()
    result.wait_ready()
    assert history.ready_calls == 1
    assert result.complete
    with pytest.raises(ObsSessionError):
        result.take_routing_history()
    result.close()
    receiver.close()
    assert all(track.store.closed for track in result.tracks)
    assert not history.closed
    history.close()
    assert history.wait_closed(0)


def test_cancel_clears_current_metadata_but_waits_for_storage_cleanup():
    receiver = started()
    receiver.accept(observation())
    history = receiver.routing_history
    history.cleanup_ready = False
    receiver.cancel()
    assert receiver.current_routing is None
    assert receiver.state == "cancelled"
    assert not receiver.wait_closed(0)
    history.cleanup_ready = True
    assert receiver.wait_closed(0)


@pytest.mark.parametrize("version", [True, 0, 3, "2", 2.0])
def test_receiver_requires_exact_supported_protocol_version(version):
    with pytest.raises(ValueError):
        started(version=version)
