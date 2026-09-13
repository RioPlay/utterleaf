from collections import deque
import io
import threading

import numpy as np
import pytest

import utterleaf.capture_store as capture_module
import utterleaf.obs_transcription as live
from utterleaf.capture_store import CaptureRead, CaptureReadState, CaptureStore
from utterleaf.config import Config
from utterleaf.obs_session import CapturedTrack, ObsCaptureResult
from utterleaf.transcript import Segment, Transcript


ORIGIN = 5_000_000_000
RATE = 16000


def _wait_written(store, samples):
    with store._condition:
        assert store._condition.wait_for(
            lambda: store.progress.written_source_samples >= samples, timeout=2
        )


def _store(audio):
    store = CaptureStore(RATE)
    assert store.append(np.asarray(audio, dtype=np.float32))
    _wait_written(store, len(audio))
    return store


def _track(bus, store, *, first=ORIGIN, frames=None):
    return CapturedTrack(bus, first, frames if frames is not None else len(store), 0, store)


def _result(tracks, *, clean=True, reason="OBS capture finished.", origin=ORIGIN, primary=0):
    return ObsCaptureResult(tuple(tracks), primary_bus=primary, origin_ns=origin,
                            clean_end=clean, reason=reason)


def _assert_audio_files_closed(result):
    assert result.closed
    # CaptureStore.close requests cancellation without waiting for in-flight I/O.
    # Recognition completion is not the capture writer's completion barrier.
    for track in result.tracks:
        track.store._worker.join(2)
        assert not track.store._worker.is_alive()
        assert track.store._file.closed


def _factory(recognize, observed_configs=None):
    def make(config):
        if observed_configs is not None:
            observed_configs.append(config)
        return recognize
    return make


def _one_segment(audio, config, *, cancel):
    return Transcript((Segment(0, len(audio) / RATE, "recognized"),), "en")


def test_live_windows_are_recognized_before_end_with_per_track_timestamps(monkeypatch):
    monkeypatch.setattr(capture_module, "WINDOW_SECONDS", 0.01)
    store = _store(np.linspace(-0.25, 0.25, 320, dtype=np.float32))
    calls = []
    two_calls = threading.Event()

    def recognize(audio, config, *, cancel):
        calls.append((threading.get_ident(), len(audio), config.allow_network))
        if len(calls) == 2:
            two_calls.set()
        return Transcript((Segment(0.001, 0.005, f"piece {len(calls)}"),), "en")

    coordinator = live.ObsTranscriptionCoordinator(
        Config(allow_network=True), recognizer_factory=_factory(recognize)
    )
    borrowed = _track(0, store, first=ORIGIN + 100_000_000, frames=320)
    coordinator.add_track(borrowed, origin_ns=ORIGIN, sample_rate=RATE, primary_bus=0)
    assert two_calls.wait(2), "full committed windows should be recognized before End"
    assert coordinator.snapshot().state is live.ObsTranscriptionState.RUNNING

    store.finish()
    result = _result((_track(0, store, first=ORIGIN + 100_000_000, frames=320),))
    coordinator.finish_capture(result)
    assert coordinator.wait(2)
    assert coordinator.snapshot().state is live.ObsTranscriptionState.COMPLETE
    segments = list(coordinator.iter_segments())
    assert [segment.bus for segment in segments] == [0, 0]
    assert [segment.start for segment in segments] == pytest.approx([0.101, 0.111])
    assert [segment.end for segment in segments] == pytest.approx([0.105, 0.115])
    assert calls == [(calls[0][0], 160, False), (calls[0][0], 160, False)]
    _assert_audio_files_closed(result)
    assert coordinator.close(2)


def test_six_tracks_share_one_round_robin_recognition_worker(monkeypatch):
    monkeypatch.setattr(capture_module, "WINDOW_SECONDS", 0.01)
    stores = [_store(np.full(160, bus / 10, np.float32)) for bus in range(6)]
    calls = []
    active = 0
    peak = 0

    def recognize(audio, config, *, cancel):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        calls.append((threading.get_ident(), round(float(audio[0]), 1)))
        active -= 1
        return Transcript((Segment(0, 0.005, "track"),), "en")

    coordinator = live.ObsTranscriptionCoordinator(
        Config(), recognizer_factory=_factory(recognize)
    )
    for bus, store in enumerate(stores):
        coordinator.add_track(_track(bus, store), origin_ns=ORIGIN,
                              sample_rate=RATE, primary_bus=0)
    for store in stores:
        store.finish()
    result = _result(tuple(_track(bus, store) for bus, store in enumerate(stores)))
    coordinator.finish_capture(result)
    assert coordinator.wait(3)
    assert peak == 1
    assert len({thread for thread, _level in calls}) == 1
    assert sorted(level for _thread, level in calls) == [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
    snapshot = coordinator.snapshot()
    assert snapshot.track_count == snapshot.completed_tracks == 6
    assert snapshot.state is live.ObsTranscriptionState.COMPLETE
    _assert_audio_files_closed(result)
    coordinator.close(2)


def test_partial_tail_waits_for_finish_and_model_factory_is_lazy(monkeypatch):
    monkeypatch.setattr(capture_module, "WINDOW_SECONDS", 0.01)
    store = _store(np.ones(80, np.float32))
    loaded = threading.Event()
    recognized = threading.Event()

    def make(config):
        loaded.set()

        def recognize(audio, cfg, *, cancel):
            assert len(audio) == 80
            recognized.set()
            return Transcript((), "en")
        return recognize

    coordinator = live.ObsTranscriptionCoordinator(Config(), recognizer_factory=make)
    coordinator.add_track(_track(0, store), origin_ns=ORIGIN,
                          sample_rate=RATE, primary_bus=0)
    assert not loaded.wait(0.15)
    store.finish()
    result = _result((_track(0, store),))
    coordinator.finish_capture(result)
    assert recognized.wait(2)
    assert coordinator.wait(2)
    assert coordinator.snapshot().state is live.ObsTranscriptionState.COMPLETE
    assert list(coordinator.iter_segments()) == []
    coordinator.close(2)


def test_valid_disarm_before_audio_is_empty_and_loads_no_model():
    loaded = threading.Event()
    coordinator = live.ObsTranscriptionCoordinator(
        Config(), recognizer_factory=lambda cfg: loaded.set()
    )
    result = _result((), clean=True,
                     reason="OBS transcription disarmed before audio began.",
                     origin=None, primary=None)
    coordinator.finish_capture(result)
    assert coordinator.wait(2)
    snapshot = coordinator.snapshot()
    assert snapshot.state is live.ObsTranscriptionState.EMPTY
    assert snapshot.track_count == snapshot.completed_tracks == 0
    assert snapshot.preview == ""
    assert not snapshot.incomplete
    assert not loaded.is_set()
    assert result.closed
    coordinator.close(2)


class _ScriptedStore:
    def __init__(self, outcomes, *, error=None):
        self.sample_rate = RATE
        self.outcomes = deque(outcomes)
        self.error = error
        self.closed = False

    def __len__(self):
        return sum(item.source_samples for item in self.outcomes)

    def read_window(self, offset, cancelled):
        assert not cancelled()
        if self.outcomes:
            item = self.outcomes.popleft()
            assert item.source_offset == offset
            return item
        return CaptureRead(CaptureReadState.FAILED, offset, error=self.error)

    def wait_ready(self, cancelled):
        assert not cancelled()

    def close(self):
        self.closed = True


def test_failed_store_publishes_prefix_then_finishes_incomplete():
    error = "Temporary audio storage failed. Only the stored portion can be recovered."
    store = _ScriptedStore([
        CaptureRead(CaptureReadState.READY, 0, 160, np.ones(160, np.float32)),
        CaptureRead(CaptureReadState.FAILED, 160, error=error),
    ], error=error)
    coordinator = live.ObsTranscriptionCoordinator(
        Config(), recognizer_factory=_factory(_one_segment), journal_factory=io.BytesIO
    )
    coordinator.add_track(_track(0, store, frames=160), origin_ns=ORIGIN,
                          sample_rate=RATE, primary_bus=0)
    result = _result((_track(0, store, frames=160),))
    coordinator.finish_capture(result)
    assert coordinator.wait(2)
    snapshot = coordinator.snapshot()
    assert snapshot.state is live.ObsTranscriptionState.INCOMPLETE
    assert snapshot.incomplete
    assert "storage" in snapshot.message.lower()
    assert coordinator.failed
    assert [segment.text for segment in coordinator.iter_segments()] == ["recognized"]
    assert store.closed and result.closed
    coordinator.close(2)


def test_abnormal_capture_end_is_incomplete_after_all_audio_is_drained(monkeypatch):
    monkeypatch.setattr(capture_module, "WINDOW_SECONDS", 0.01)
    store = _store(np.ones(160, np.float32))
    store.finish()
    coordinator = live.ObsTranscriptionCoordinator(
        Config(), recognizer_factory=_factory(_one_segment)
    )
    coordinator.add_track(_track(0, store), origin_ns=ORIGIN,
                          sample_rate=RATE, primary_bus=0)
    result = _result((_track(0, store),), clean=False,
                     reason="OBS capture was interrupted. Only the prefix can be recovered.")
    coordinator.finish_capture(result)
    assert coordinator.wait(2)
    snapshot = coordinator.snapshot()
    assert snapshot.state is live.ObsTranscriptionState.INCOMPLETE
    assert snapshot.incomplete
    assert "interrupted" in snapshot.message
    assert len(list(coordinator.iter_segments())) == 1
    coordinator.close(2)


def test_default_recognizer_honors_saved_device_and_enforces_limits(monkeypatch):
    monkeypatch.setattr(capture_module, "WINDOW_SECONDS", 0.01)
    from utterleaf import transcribe

    store = _store(np.ones(160, np.float32))
    store.finish()
    engine = transcribe.CTranslateEngine(None)
    calls = []

    def recognize(audio, config, *, cancel, **limits):
        calls.append((len(audio), config.allow_network, cancel, limits))
        return Transcript((Segment(0, 0.005, "local"),), "en")

    monkeypatch.setattr(engine, "transcribe_segments", recognize)

    def load(config, accelerator=None):
        assert config.allow_network is False
        assert accelerator is None
        return engine

    monkeypatch.setattr(transcribe, "load_model", load)
    coordinator = live.ObsTranscriptionCoordinator(Config(allow_network=True))
    coordinator.add_track(_track(0, store), origin_ns=ORIGIN,
                          sample_rate=RATE, primary_bus=0)
    result = _result((_track(0, store),))
    coordinator.finish_capture(result)
    assert coordinator.wait(2)
    assert [(count, offline) for count, offline, _cancel, _limits in calls] == [(160, False)]
    assert calls[0][2] is coordinator._cancel
    assert calls[0][3] == {
        "max_segments": live.MAX_SEGMENTS_PER_WINDOW,
        "max_segment_text_bytes": live.MAX_SEGMENT_TEXT_BYTES,
        "max_total_text_bytes": live.MAX_WINDOW_TEXT_BYTES,
    }
    assert [segment.text for segment in coordinator.iter_segments()] == ["local"]
    coordinator.close(2)


def test_saved_non_segmented_engine_fails_without_silent_device_override(monkeypatch):
    monkeypatch.setattr(capture_module, "WINDOW_SECONDS", 0.01)
    from utterleaf import transcribe

    store = _store(np.ones(160, np.float32))
    store.finish()
    choices = []

    def load(config, accelerator=None):
        choices.append(accelerator)
        return transcribe.OpenVinoEngine(None)

    monkeypatch.setattr(transcribe, "load_model", load)
    coordinator = live.ObsTranscriptionCoordinator(Config(device="npu"))
    coordinator.add_track(_track(0, store), origin_ns=ORIGIN,
                          sample_rate=RATE, primary_bus=0)
    result = _result((_track(0, store),))
    coordinator.finish_capture(result)
    assert coordinator.wait(2)
    assert choices == [None]
    assert coordinator.failed
    assert coordinator.snapshot().state is live.ObsTranscriptionState.FAILED
    _assert_audio_files_closed(result)
    coordinator.close(2)


def test_cancel_before_transfer_suppresses_ignored_late_model_result(monkeypatch):
    monkeypatch.setattr(capture_module, "WINDOW_SECONDS", 0.01)
    store = _store(np.ones(160, np.float32))
    started = threading.Event()
    release = threading.Event()

    def recognize(audio, config, *, cancel):
        started.set()
        assert release.wait(2)
        return Transcript((Segment(0, 0.005, "must not publish"),), "en")

    coordinator = live.ObsTranscriptionCoordinator(
        Config(), recognizer_factory=_factory(recognize), journal_factory=io.BytesIO
    )
    coordinator.add_track(_track(0, store), origin_ns=ORIGIN,
                          sample_rate=RATE, primary_bus=0)
    assert started.wait(2)
    coordinator.cancel()
    assert not coordinator.wait(0.05)
    release.set()
    assert coordinator.wait(2)
    assert coordinator.snapshot().state is live.ObsTranscriptionState.CANCELLED
    assert coordinator.snapshot().preview == ""
    assert list(coordinator.iter_segments()) == []
    assert not store._file.closed, "borrowed store ownership did not transfer"
    coordinator.close(2)
    store.close()


def test_cancel_during_journal_write_rolls_back_and_closes_owned_result(monkeypatch):
    monkeypatch.setattr(capture_module, "WINDOW_SECONDS", 0.01)
    store = _store(np.ones(160, np.float32))
    store.finish()
    write_started = threading.Event()
    release_write = threading.Event()

    class BlockingJournal(io.BytesIO):
        def write(self, data):
            write_started.set()
            assert release_write.wait(2)
            return super().write(data)

    journal = BlockingJournal()
    coordinator = live.ObsTranscriptionCoordinator(
        Config(), recognizer_factory=_factory(_one_segment),
        journal_factory=lambda: journal,
    )
    coordinator.add_track(_track(0, store), origin_ns=ORIGIN,
                          sample_rate=RATE, primary_bus=0)
    result = _result((_track(0, store),))
    coordinator.finish_capture(result)
    assert write_started.wait(2)
    coordinator.cancel()
    release_write.set()
    assert coordinator.wait(2)
    assert coordinator.snapshot().state is live.ObsTranscriptionState.CANCELLED
    assert list(coordinator.iter_segments()) == []
    _assert_audio_files_closed(result)
    assert coordinator.close(2) and journal.closed


def test_journal_write_failure_is_failed_and_result_is_closed(monkeypatch):
    monkeypatch.setattr(capture_module, "WINDOW_SECONDS", 0.01)
    store = _store(np.ones(160, np.float32))
    store.finish()

    class FailedJournal(io.BytesIO):
        def write(self, data):
            raise OSError("disk full")

    coordinator = live.ObsTranscriptionCoordinator(
        Config(), recognizer_factory=_factory(_one_segment),
        journal_factory=FailedJournal,
    )
    coordinator.add_track(_track(0, store), origin_ns=ORIGIN,
                          sample_rate=RATE, primary_bus=0)
    result = _result((_track(0, store),))
    coordinator.finish_capture(result)
    assert coordinator.wait(2)
    snapshot = coordinator.snapshot()
    assert snapshot.state is live.ObsTranscriptionState.FAILED
    assert snapshot.preview == ""
    assert coordinator.failed
    _assert_audio_files_closed(result)
    coordinator.close(2)


@pytest.mark.parametrize("bad_result", [
    Transcript(tuple(Segment(0, 0.001, str(index))
                     for index in range(live.MAX_SEGMENTS_PER_WINDOW + 1))),
    Transcript((Segment(0, 0.001, "x" * (live.MAX_SEGMENT_TEXT_BYTES + 1)),)),
    Transcript((Segment(0.02, 0.03, "outside"),)),
])
def test_oversized_or_out_of_window_model_output_fails_closed(monkeypatch, bad_result):
    monkeypatch.setattr(capture_module, "WINDOW_SECONDS", 0.01)
    store = _store(np.ones(160, np.float32))
    store.finish()
    recognize = lambda audio, config, cancel: bad_result
    coordinator = live.ObsTranscriptionCoordinator(
        Config(), recognizer_factory=_factory(recognize), journal_factory=io.BytesIO
    )
    coordinator.add_track(_track(0, store), origin_ns=ORIGIN,
                          sample_rate=RATE, primary_bus=0)
    result = _result((_track(0, store),))
    coordinator.finish_capture(result)
    assert coordinator.wait(2)
    assert coordinator.snapshot().state is live.ObsTranscriptionState.FAILED
    assert list(coordinator.iter_segments()) == []
    assert result.closed
    coordinator.close(2)


def test_arbitrary_model_generator_is_rejected_without_consumption(monkeypatch):
    monkeypatch.setattr(capture_module, "WINDOW_SECONDS", 0.01)
    store = _store(np.ones(160, np.float32))
    store.finish()
    consumed = threading.Event()

    def output():
        consumed.set()
        yield Segment(0, 0.001, "unbounded")

    coordinator = live.ObsTranscriptionCoordinator(
        Config(), recognizer_factory=_factory(lambda audio, config, cancel: output()),
        journal_factory=io.BytesIO,
    )
    coordinator.add_track(_track(0, store), origin_ns=ORIGIN,
                          sample_rate=RATE, primary_bus=0)
    result = _result((_track(0, store),))
    coordinator.finish_capture(result)
    assert coordinator.wait(2)
    assert coordinator.snapshot().state is live.ObsTranscriptionState.FAILED
    assert not consumed.is_set()
    assert result.closed
    coordinator.close(2)


def test_preview_is_bounded_but_journal_keeps_valid_segments(monkeypatch):
    monkeypatch.setattr(capture_module, "WINDOW_SECONDS", 0.01)
    store = _store(np.ones(320, np.float32))
    store.finish()
    calls = 0

    def recognize(audio, config, *, cancel):
        nonlocal calls
        calls += 1
        return Transcript((Segment(0, 0.005, str(calls) * 3000),), "en")

    journal = io.BytesIO()
    coordinator = live.ObsTranscriptionCoordinator(
        Config(), recognizer_factory=_factory(recognize), journal_factory=lambda: journal
    )
    coordinator.add_track(_track(0, store, frames=320), origin_ns=ORIGIN,
                          sample_rate=RATE, primary_bus=0)
    result = _result((_track(0, store, frames=320),))
    coordinator.finish_capture(result)
    assert coordinator.wait(2)
    snapshot = coordinator.snapshot()
    assert len(snapshot.preview) == live.PREVIEW_CHARS
    assert snapshot.preview.endswith("2" * 3000)
    segments = list(coordinator.iter_segments())
    assert [len(segment.text) for segment in segments] == [3000, 3000]
    assert coordinator.close(2)
    assert journal.closed
    with pytest.raises(live.ObsTranscriptionError, match="closed"):
        list(coordinator.iter_segments())


def test_cancel_after_completion_discards_readable_journal_and_preview(monkeypatch):
    monkeypatch.setattr(capture_module, "WINDOW_SECONDS", 0.01)
    store = _store(np.ones(160, np.float32))
    store.finish()
    journal = io.BytesIO()
    coordinator = live.ObsTranscriptionCoordinator(
        Config(), recognizer_factory=_factory(_one_segment), journal_factory=lambda: journal
    )
    coordinator.add_track(_track(0, store), origin_ns=ORIGIN,
                          sample_rate=RATE, primary_bus=0)
    result = _result((_track(0, store),))
    coordinator.finish_capture(result)
    assert coordinator.wait(2)
    assert list(coordinator.iter_segments())

    coordinator.cancel()
    snapshot = coordinator.snapshot()
    assert snapshot.state is live.ObsTranscriptionState.CANCELLED
    assert snapshot.preview == ""
    assert list(coordinator.iter_segments()) == []
    assert coordinator.close(2)
    assert journal.closed


def test_cancel_defers_journal_deletion_until_active_reader_releases(monkeypatch):
    monkeypatch.setattr(capture_module, "WINDOW_SECONDS", 0.01)
    store = _store(np.ones(320, np.float32))
    store.finish()
    journal = io.BytesIO()
    coordinator = live.ObsTranscriptionCoordinator(
        Config(), recognizer_factory=_factory(_one_segment), journal_factory=lambda: journal
    )
    coordinator.add_track(_track(0, store, frames=320), origin_ns=ORIGIN,
                          sample_rate=RATE, primary_bus=0)
    result = _result((_track(0, store, frames=320),))
    coordinator.finish_capture(result)
    assert coordinator.wait(2)

    segments = coordinator.iter_segments()
    assert next(segments).text == "recognized"
    coordinator.cancel()
    assert not journal.closed
    assert not coordinator.wait(0.05)
    segments.close()
    assert coordinator.wait(2)
    assert coordinator.snapshot().state is live.ObsTranscriptionState.CANCELLED
    assert coordinator.close(2)
    assert journal.closed


def test_cancel_never_waits_for_blocking_journal_close(monkeypatch):
    monkeypatch.setattr(capture_module, "WINDOW_SECONDS", 0.01)
    store = _store(np.ones(160, np.float32))
    store.finish()
    close_started = threading.Event()
    release_close = threading.Event()

    class SlowCloseJournal(io.BytesIO):
        def close(self):
            close_started.set()
            assert release_close.wait(2)
            super().close()

    journal = SlowCloseJournal()
    coordinator = live.ObsTranscriptionCoordinator(
        Config(), recognizer_factory=_factory(_one_segment), journal_factory=lambda: journal
    )
    coordinator.add_track(_track(0, store), origin_ns=ORIGIN,
                          sample_rate=RATE, primary_bus=0)
    result = _result((_track(0, store),))
    coordinator.finish_capture(result)
    assert coordinator.wait(2)
    assert list(coordinator.iter_segments())

    cancel_returned = threading.Event()
    caller = threading.Thread(target=lambda: (coordinator.cancel(), cancel_returned.set()))
    caller.start()
    try:
        assert close_started.wait(2)
        assert cancel_returned.wait(0.5), "cancel waited for journal.close"
        assert not journal.closed
        assert not coordinator.wait(0.05)
    finally:
        release_close.set()
        caller.join(2)
    assert coordinator.wait(2)
    assert coordinator.close(2)
    assert journal.closed


def test_journal_close_failure_finishes_wait_and_stays_visibly_failed(monkeypatch):
    monkeypatch.setattr(capture_module, "WINDOW_SECONDS", 0.01)
    store = _store(np.ones(160, np.float32))
    store.finish()

    class FailedCloseJournal(io.BytesIO):
        def __init__(self):
            super().__init__()
            self.close_attempts = 0

        def close(self):
            self.close_attempts += 1
            raise OSError("private close detail")

    journal = FailedCloseJournal()
    coordinator = live.ObsTranscriptionCoordinator(
        Config(), recognizer_factory=_factory(_one_segment), journal_factory=lambda: journal
    )
    coordinator.add_track(_track(0, store), origin_ns=ORIGIN,
                          sample_rate=RATE, primary_bus=0)
    result = _result((_track(0, store),))
    coordinator.finish_capture(result)
    assert coordinator.wait(2)
    assert list(coordinator.iter_segments())

    coordinator.cancel()
    assert coordinator.wait(2), "failed cleanup is terminal, not an endless wait"
    snapshot = coordinator.snapshot()
    assert snapshot.state is live.ObsTranscriptionState.FAILED
    assert snapshot.message == "Private OBS transcript cleanup failed."
    assert "private close detail" not in snapshot.message
    assert snapshot.preview == ""
    assert coordinator.failed
    assert list(coordinator.iter_segments()) == []
    coordinator.cancel()
    assert coordinator.snapshot() == snapshot
    with pytest.raises(live.ObsTranscriptionError, match="could not be deleted") as failure:
        coordinator.close(2)
    assert "private close detail" not in str(failure.value)
    assert journal.close_attempts == 1
    io.BytesIO.close(journal)


def test_cleanup_thread_start_failure_is_terminal_sanitized_and_does_no_io(monkeypatch):
    monkeypatch.setattr(capture_module, "WINDOW_SECONDS", 0.01)
    store = _store(np.ones(160, np.float32))
    store.finish()
    journal = io.BytesIO()
    coordinator = live.ObsTranscriptionCoordinator(
        Config(), recognizer_factory=_factory(_one_segment), journal_factory=lambda: journal
    )
    coordinator.add_track(_track(0, store), origin_ns=ORIGIN,
                          sample_rate=RATE, primary_bus=0)
    result = _result((_track(0, store),))
    coordinator.finish_capture(result)
    assert coordinator.wait(2)
    assert list(coordinator.iter_segments())

    class FailedCleanupThread:
        def __init__(self, **kwargs):
            pass

        def start(self):
            raise RuntimeError("private thread detail")

    monkeypatch.setattr(live.threading, "Thread", FailedCleanupThread)
    coordinator.cancel()
    assert coordinator.wait(2)
    snapshot = coordinator.snapshot()
    assert snapshot.state is live.ObsTranscriptionState.FAILED
    assert snapshot.message == "Private OBS transcript cleanup failed."
    assert "private thread detail" not in snapshot.message
    assert snapshot.preview == ""
    assert coordinator.failed
    assert not journal.closed, "cancel performed journal I/O after cleanup start failed"
    assert list(coordinator.iter_segments()) == []
    coordinator.cancel()
    assert coordinator.snapshot() == snapshot
    with pytest.raises(live.ObsTranscriptionError, match="could not be deleted") as failure:
        coordinator.close(2)
    assert "private thread detail" not in str(failure.value)
    assert not journal.closed
    io.BytesIO.close(journal)


def test_finish_validation_does_not_take_mismatched_store(monkeypatch):
    monkeypatch.setattr(capture_module, "WINDOW_SECONDS", 0.01)
    registered = _store(np.ones(160, np.float32))
    different = _store(np.ones(160, np.float32))
    coordinator = live.ObsTranscriptionCoordinator(
        Config(), recognizer_factory=_factory(_one_segment)
    )
    coordinator.add_track(_track(0, registered), origin_ns=ORIGIN,
                          sample_rate=RATE, primary_bus=0)
    result = _result((_track(0, different),))
    with pytest.raises(live.ObsTranscriptionError, match="changed"):
        coordinator.finish_capture(result)
    assert not result.closed and not different._file.closed
    coordinator.cancel()
    assert coordinator.wait(2)
    registered.close()
    result.close()
    coordinator.close(2)


@pytest.mark.parametrize("field,value", [
    ("bus", 6),
    ("first", None),
    ("first", ORIGIN - 1),
    ("frames", 0),
])
def test_invalid_live_track_metadata_is_refused_without_ownership(field, value):
    store = _store(np.ones(1, np.float32))
    values = {"bus": 0, "first": ORIGIN, "frames": 1}
    values[field] = value
    coordinator = live.ObsTranscriptionCoordinator(Config(), recognizer_factory=_factory(_one_segment))
    track = _track(values["bus"], store, first=values["first"], frames=values["frames"])
    with pytest.raises(ValueError):
        coordinator.add_track(track, origin_ns=ORIGIN, sample_rate=RATE, primary_bus=0)
    coordinator.cancel()
    assert coordinator.wait(2)
    assert not store._file.closed
    store.close()
    coordinator.close(2)
