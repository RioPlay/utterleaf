"""Routing-history ownership tests for live OBS transcription."""

from __future__ import annotations

import io
import threading

import numpy as np
import pytest

from utterleaf.capture_store import CaptureStore
from utterleaf.config import Config
from utterleaf.obs_mix import BusLabel, MixSnapshot, SourceAssignment
from utterleaf.obs_protocol import RoutingFrame
from utterleaf.obs_routing_store import ObsRoutingStore, ObsRoutingStoreError
from utterleaf.obs_session import CapturedTrack, ObsCaptureResult, ObsSessionError
from utterleaf.obs_transcription import (
    ObsTranscriptionCoordinator,
    ObsTranscriptionError,
    ObsTranscriptionState,
)
from utterleaf.transcript import Segment, Transcript, TranscriptionCancelled


ORIGIN = 4_000_000_000
RATE = 16_000
SESSION = b"routing-session!"


def routing(revision=1):
    return RoutingFrame(
        SESSION,
        revision,
        ORIGIN + revision,
        ((0, revision - 1),),
        MixSnapshot(
            0,
            1,
            (SourceAssignment(revision.to_bytes(16, "big"), "Input", 1),),
            (BusLabel(0, "Stream"),),
        ),
    )


def history(*frames, journal=None):
    journal = journal or io.BytesIO()
    store = ObsRoutingStore(journal_factory=lambda: journal)
    for frame in frames:
        assert store.append(frame)
    store.finish()
    return store, journal


def coordinator():
    def factory(_config):
        def recognize(audio, _snapshot, *, cancel):
            return Transcript((Segment(0, len(audio) / RATE, "recognized"),), "en")

        return recognize

    return ObsTranscriptionCoordinator(
        Config(), recognizer_factory=factory, journal_factory=io.BytesIO
    )


def capture_result(*, routing_history=None):
    audio = CaptureStore(RATE)
    assert audio.append(np.ones(160, dtype=np.float32))
    audio.finish()
    track = CapturedTrack(0, ORIGIN, 160, 0, audio)
    result = ObsCaptureResult(
        (track,),
        primary_bus=0,
        origin_ns=ORIGIN,
        clean_end=True,
        reason="OBS capture finished.",
        routing_history=routing_history,
    )
    return track, result


def complete_with_history(*frames, journal=None):
    routing_store, journal = history(*frames, journal=journal)
    owner = coordinator()
    owner.attach_routing_history(routing_store)
    track, result = capture_result(routing_history=routing_store)
    owner.add_track(track, origin_ns=ORIGIN, sample_rate=RATE, primary_bus=0)
    owner.finish_capture(result)
    assert owner.wait(2)
    return owner, result, routing_store, journal


def test_history_transfers_once_and_survives_audio_result_close_for_export():
    frame = routing()
    owner, result, routing_store, journal = complete_with_history(frame)

    assert result.closed
    assert owner.snapshot().state is ObsTranscriptionState.COMPLETE
    assert tuple(owner.iter_routing_observations()) == (frame,)
    assert not journal.closed
    with pytest.raises(ObsSessionError, match="not transferable"):
        result.take_routing_history()

    assert owner.close(2)
    assert routing_store.wait_closed(0)
    assert journal.closed


def test_version1_result_has_no_routing_history_or_fabricated_observations():
    owner = coordinator()
    track, result = capture_result()
    owner.add_track(track, origin_ns=ORIGIN, sample_rate=RATE, primary_bus=0)
    owner.finish_capture(result)

    assert owner.wait(2)
    assert owner.snapshot().state is ObsTranscriptionState.COMPLETE
    assert tuple(owner.iter_routing_observations()) == ()
    assert owner.close(2)


def test_result_history_must_match_the_borrowed_live_store_before_transfer():
    borrowed, _ = history(routing())
    different, _ = history(routing())
    owner = coordinator()
    owner.attach_routing_history(borrowed)
    track, result = capture_result(routing_history=different)
    owner.add_track(track, origin_ns=ORIGIN, sample_rate=RATE, primary_bus=0)

    with pytest.raises(ObsTranscriptionError, match="changed its routing history"):
        owner.finish_capture(result)
    assert result.take_routing_history() is different

    result.close()
    different.close()
    assert different.wait_closed(2)
    owner.cancel()
    assert not owner.wait(0.05)
    borrowed.close()
    assert owner.wait(2)
    assert owner.close(2)


def test_cancel_does_not_close_borrowed_history_but_wait_includes_owner_cleanup():
    borrowed = ObsRoutingStore(journal_factory=io.BytesIO)
    owner = coordinator()
    owner.attach_routing_history(borrowed)

    owner.cancel()
    assert borrowed.append(routing()), "transcription closed a receiver-owned history"
    borrowed.finish()
    borrowed.wait_ready()
    assert not owner.wait(0.05)

    borrowed.close()
    assert owner.wait(2)
    assert owner.snapshot().state is ObsTranscriptionState.CANCELLED
    assert owner.close(2)


def test_cancelled_owned_history_waits_for_active_reader_release():
    owner, _, _, journal = complete_with_history(routing(1), routing(2))
    observations = owner.iter_routing_observations()
    assert next(observations).revision == 1

    owner.cancel()
    assert not owner.wait(0.05)
    assert not journal.closed
    observations.close()

    assert owner.wait(2)
    assert owner.snapshot().state is ObsTranscriptionState.CANCELLED
    assert owner.close(2)
    assert journal.closed


def test_internal_recognizer_cancellation_discards_transferred_history():
    entered = threading.Event()
    release = threading.Event()

    def factory(_config):
        def recognize(_audio, _snapshot, *, cancel):
            entered.set()
            assert release.wait(2)
            raise TranscriptionCancelled("private recognizer cancellation detail")

        return recognize

    journal = io.BytesIO()
    routing_store, _ = history(routing(), journal=journal)
    owner = ObsTranscriptionCoordinator(
        Config(), recognizer_factory=factory, journal_factory=io.BytesIO
    )
    owner.attach_routing_history(routing_store)
    track, result = capture_result(routing_history=routing_store)
    owner.add_track(track, origin_ns=ORIGIN, sample_rate=RATE, primary_bus=0)
    assert entered.wait(2)

    owner.finish_capture(result)
    release.set()

    assert owner.wait(2)
    assert routing_store.wait_closed(0)
    assert journal.closed
    snapshot = owner.snapshot()
    assert snapshot.state is ObsTranscriptionState.CANCELLED
    assert "private recognizer" not in snapshot.message
    assert owner.close(2)


def test_borrowed_storage_failure_is_a_cheap_sanitized_failure_signal():
    def failed_factory():
        raise OSError("private source name and path")

    routing_store = ObsRoutingStore(journal_factory=failed_factory)
    with pytest.raises(ObsRoutingStoreError, match="storage failed"):
        routing_store.wait_ready()
    owner = coordinator()
    owner.attach_routing_history(routing_store)

    assert owner.failed
    snapshot = owner.snapshot()
    assert snapshot.state is ObsTranscriptionState.FAILED
    assert snapshot.message == "Private OBS routing history storage failed."
    assert "private source name" not in snapshot.message

    owner.cancel()
    routing_store.close()
    assert owner.wait(2)
    assert owner.close(2)


def test_late_owned_history_cleanup_failure_overrides_complete_and_cancelled():
    class FailedClose(io.BytesIO):
        def close(self):
            raise OSError("private source cleanup detail")

    journal = FailedClose()
    owner, _, _, _ = complete_with_history(routing(), journal=journal)
    assert owner.snapshot().state is ObsTranscriptionState.COMPLETE

    owner.cancel()
    assert owner.wait(2)
    snapshot = owner.snapshot()
    assert snapshot.state is ObsTranscriptionState.FAILED
    assert snapshot.message == "Private OBS routing history cleanup failed."
    assert "private source cleanup detail" not in snapshot.message
    assert snapshot.preview == ""
    assert owner.failed
    assert tuple(owner.iter_routing_observations()) == ()
    owner.cancel()
    assert owner.snapshot() == snapshot
    with pytest.raises(ObsTranscriptionError, match="could not be discarded") as caught:
        owner.close(2)
    assert "private source cleanup detail" not in str(caught.value)
    io.BytesIO.close(journal)


def test_routing_history_cannot_be_read_before_transcription_finishes():
    routing_store, _ = history(routing())
    owner = coordinator()
    owner.attach_routing_history(routing_store)
    with pytest.raises(ObsTranscriptionError, match="Wait for OBS transcription"):
        tuple(owner.iter_routing_observations())

    owner.cancel()
    routing_store.close()
    assert owner.wait(2)
    assert owner.close(2)
