"""Consent, ordering, ownership and real bounded storage for OBS reception."""

import numpy as np
import pytest

from utterleaf.audio_batching import audio_windows
from utterleaf.capture_store import CaptureStore
from utterleaf.obs_protocol import AudioFrame, EndFrame, EndReason, GapFrame, StartFrame
from utterleaf.obs_session import ObsCaptureSession, ObsSessionError
from utterleaf.transcript import TranscriptionCancelled


SESSION = b"synthetic-obs-id"
ORIGIN = 5_000_000_000


class Store:
    def __init__(self, rate):
        self.rate = rate
        self.blocks = []
        self.error = None
        self.closed = False
        self.sealed = False
        self.refuse = False
        self.raise_on_append = False

    def append(self, block):
        if self.raise_on_append:
            raise OSError("synthetic failure")
        if self.refuse:
            return False
        self.blocks.append(block.copy())
        return True

    def finish(self):
        self.sealed = True

    def wait_ready(self, cancelled):
        assert self.sealed
        if cancelled():
            raise TranscriptionCancelled("synthetic cancellation")

    def close(self):
        self.closed = True


def armed(buses=(0,), primary=0, factory=Store):
    return ObsCaptureSession(SESSION, primary, buses, stream_active=False, store_factory=factory)


def start(receiver, *, rate=48000, origin=ORIGIN):
    receiver.notify_stream_started(SESSION)
    receiver.accept(StartFrame(SESSION, rate, receiver.primary_bus,
                               sum(1 << bus for bus in receiver.buses), origin))


def audio(bus=0, seq=0, timestamp=ORIGIN, frames=4800, left=0.2, right=0.4):
    pcm = np.empty((frames, 2), dtype="<f4")
    pcm[:, 0], pcm[:, 1] = left, right
    return AudioFrame(SESSION, bus, seq, timestamp, frames, pcm.tobytes())


def test_manual_arm_and_post_arm_stream_event_are_both_required():
    opened = []
    receiver = armed(factory=lambda rate: opened.append(rate))
    assert receiver.state == "armed"
    assert opened == []
    with pytest.raises(ObsSessionError, match="explicitly armed"):
        receiver.accept(StartFrame(SESSION, 48000, 0, 1, ORIGIN))
    assert opened == []
    assert receiver.state == "incomplete"
    with pytest.raises(ObsSessionError):
        receiver.notify_stream_started(SESSION)
    receiver.close()


@pytest.mark.parametrize("active", [True, None, 0, "false"])
def test_unknown_or_already_active_obs_cannot_be_armed(active):
    with pytest.raises(ObsSessionError):
        ObsCaptureSession(SESSION, 0, (0,), stream_active=active,
                          store_factory=lambda rate: pytest.fail("Unarmed storage"))


@pytest.mark.parametrize("buses,primary", [((1, 0), 0), ((0, 0), 0), ((6,), 6),
                                         ((), 0), ((False,), 0), ((0,), True),
                                         ([0], 0), ((1,), 0)])
def test_bus_selection_is_explicit_and_validated(buses, primary):
    with pytest.raises(ValueError):
        armed(buses, primary)


def test_audio_before_start_is_not_stored():
    receiver = armed(factory=lambda rate: pytest.fail("Premature storage"))
    receiver.notify_stream_started(SESSION)
    with pytest.raises(ObsSessionError):
        receiver.accept(audio())
    receiver.close()


def test_automatic_primary_uses_actual_start_mix_without_guessing_track_one():
    receiver = ObsCaptureSession(SESSION, stream_active=False, store_factory=Store)
    assert receiver.primary_bus is None
    assert receiver.buses == ()
    receiver.notify_stream_started(SESSION)
    receiver.accept(StartFrame(SESSION, 48000, 4, 1 << 4, ORIGIN))
    try:
        assert receiver.primary_bus == 4
        assert receiver.buses == (4,)
        receiver.accept(audio(bus=4))
        receiver.accept(EndFrame(SESSION, EndReason.STREAM_STOPPED, ((4, 0),)))
        result = receiver.take_result()
        try:
            result.wait_ready()
            assert result.complete
            assert result.primary_bus == 4
        finally:
            result.close()
    finally:
        receiver.close()


@pytest.mark.parametrize("primary", [2, 5])
def test_automatic_primary_deduplicates_only_requested_additional_buses(primary):
    receiver = ObsCaptureSession(SESSION, buses=(2, 4), stream_active=False, store_factory=Store)
    receiver.notify_stream_started(SESSION)
    mask = (1 << 2) | (1 << 4) | (1 << primary)
    receiver.accept(StartFrame(SESSION, 48000, primary, mask, ORIGIN))
    try:
        assert receiver.buses == tuple(sorted({2, 4, primary}))
        assert receiver.primary_bus == primary
    finally:
        receiver.close()


@pytest.mark.parametrize("mask", [1 << 4, (1 << 4) | (1 << 2) | (1 << 1)])
def test_automatic_primary_refuses_missing_requested_or_unsolicited_extra_bus(mask):
    receiver = ObsCaptureSession(SESSION, buses=(2,), stream_active=False,
                                 store_factory=lambda rate: pytest.fail("Wrong mix storage"))
    receiver.notify_stream_started(SESSION)
    with pytest.raises(ObsSessionError, match="different audio mix"):
        receiver.accept(StartFrame(SESSION, 48000, 4, mask, ORIGIN))
    receiver.close()


def test_stale_session_and_duplicate_start_do_not_open_storage_twice():
    receiver = armed()
    with pytest.raises(ObsSessionError, match="stale"):
        receiver.notify_stream_started(b"different-session")
    assert receiver.state == "incomplete"
    receiver.close()
    receiver = armed()
    start(receiver)
    stores = [item.store for item in receiver._tracks.values()]
    with pytest.raises(ObsSessionError):
        receiver.accept(StartFrame(SESSION, 48000, 0, 1, ORIGIN))
    assert all(store.sealed for store in stores)
    receiver.close()
    assert all(store.closed for store in stores)


def test_mismatched_start_mix_never_opens_files():
    receiver = armed(factory=lambda rate: pytest.fail("Wrong mix storage"))
    receiver.notify_stream_started(SESSION)
    with pytest.raises(ObsSessionError, match="different audio mix"):
        receiver.accept(StartFrame(SESSION, 48000, 1, 2, ORIGIN))
    receiver.close()


def test_primary_and_additional_buses_retain_independent_offsets_and_samples():
    receiver = armed((2, 3), 2, CaptureStore)
    result = None
    start(receiver)
    try:
        for seq in range(3):
            receiver.accept(audio(2, seq, ORIGIN + seq * 100_000_000, left=0.2, right=0.4))
        for seq in range(2):
            receiver.accept(audio(3, seq, ORIGIN + (seq + 1) * 100_000_000, left=-0.2, right=-0.4))
        receiver.accept(EndFrame(SESSION, EndReason.STREAM_STOPPED, ((2, 2), (3, 1))))
        result = receiver.take_result()
        assert not result.complete  # Writer completion must still be checked.
        result.wait_ready()
        assert result.complete
        assert result.primary_bus == 2
        assert result.origin_ns == ORIGIN
        assert [track.first_timestamp_ns - result.origin_ns for track in result.tracks] == [0, 100_000_000]
        assert [track.received_frames for track in result.tracks] == [14400, 9600]
        for track, expected_count, expected_level in zip(result.tracks, (4800, 3200), (0.3, -0.3)):
            chunks = list(audio_windows(track.store.chunks()))
            assert sum(len(chunk) for chunk in chunks) == expected_count
            assert all(np.allclose(chunk, expected_level, atol=1e-6) for chunk in chunks)
        receiver.close()
        assert all(not track.store._file.closed for track in result.tracks)
    finally:
        receiver.close()
        if result is not None:
            result.close()
            assert all(track.store._file.closed for track in result.tracks)


@pytest.mark.parametrize("bad_sequence", [0, 2])
def test_duplicate_or_missing_audio_stops_before_storing_bad_block(bad_sequence):
    receiver = armed()
    start(receiver)
    receiver.accept(audio())
    with pytest.raises(ObsSessionError, match="order changed"):
        receiver.accept(audio(seq=bad_sequence, timestamp=ORIGIN + 100_000_000))
    result = receiver.take_result()
    try:
        result.wait_ready()
        assert not result.complete
        assert len(result.tracks[0].store.blocks) == 1
        assert result.tracks[0].received_frames == 4800
        with pytest.raises(ObsSessionError):
            receiver.accept(audio(seq=1, timestamp=ORIGIN + 100_000_000))
    finally:
        result.close()


@pytest.mark.parametrize("offset", [-100_000_000, 100_030_000, 200_000_000])
def test_timestamp_reversal_or_gap_never_gets_concatenated(offset):
    receiver = armed()
    start(receiver)
    receiver.accept(audio())
    with pytest.raises(ObsSessionError):
        receiver.accept(audio(seq=1, timestamp=ORIGIN + offset))
    result = receiver.take_result()
    try:
        result.wait_ready()
        assert not result.complete
        assert len(result.tracks[0].store.blocks) == 1
    finally:
        result.close()


def test_fractional_44100_clock_uses_cumulative_frames_without_rounding_drift():
    receiver = armed()
    start(receiver, rate=44100)
    try:
        for seq in range(40):
            stamp = ORIGIN + (seq * 1024 * 1_000_000_000) // 44100
            receiver.accept(audio(seq=seq, timestamp=stamp, frames=1024))
        receiver.accept(EndFrame(SESSION, EndReason.DISARMED, ((0, 39),)))
        result = receiver.take_result()
        try:
            result.wait_ready()
            assert result.complete
            assert result.tracks[0].received_frames == 40960
        finally:
            result.close()
    finally:
        receiver.close()


@pytest.mark.parametrize("rate,second_offset", [(16000, 0), (16000, 125000),
                                                (48000, 0), (48000, 41666)])
def test_one_frame_overlap_or_gap_is_not_mistaken_for_clock_rounding(rate, second_offset):
    receiver = armed()
    start(receiver, rate=rate)
    receiver.accept(audio(frames=1))
    try:
        with pytest.raises(ObsSessionError, match="timing changed"):
            receiver.accept(audio(seq=1, frames=1, timestamp=ORIGIN + second_offset))
        assert len(receiver._tracks[0].store.blocks) == 1
        assert receiver.state == "incomplete"
    finally:
        receiver.close()


def test_single_frame_fractional_clock_rounding_remains_valid():
    receiver = armed()
    start(receiver)
    try:
        for seq in range(12):
            receiver.accept(audio(seq=seq, frames=1, timestamp=ORIGIN + seq * 1_000_000_000 // 48000))
        assert receiver.state == "active"
        assert receiver._tracks[0].frames == 12
    finally:
        receiver.close()


def test_explicit_gap_stops_all_buses_with_visible_incomplete_result():
    receiver = armed((0, 2))
    start(receiver)
    receiver.accept(audio())
    with pytest.raises(ObsSessionError, match="audio was lost"):
        receiver.accept(GapFrame(SESSION, 2, 0, 3, ORIGIN))
    result = receiver.take_result()
    try:
        result.wait_ready()
        assert not result.complete
        assert all(track.store.sealed for track in result.tracks)
        assert "prefix" in result.reason
    finally:
        result.close()


@pytest.mark.parametrize("last", [((0, None),), ((0, 1),), ((1, 0),)])
def test_end_must_account_for_exact_selected_bus_sequences(last):
    receiver = armed()
    start(receiver)
    receiver.accept(audio())
    with pytest.raises(ObsSessionError, match="all declared audio"):
        receiver.accept(EndFrame(SESSION, EndReason.STREAM_STOPPED, last))
    receiver.close()


@pytest.mark.parametrize("reason", [EndReason.OBS_EXIT, EndReason.SOURCE_CHANGED, EndReason.TRANSPORT_ERROR])
def test_abnormal_terminal_reason_is_recovery_only(reason):
    receiver = armed()
    start(receiver)
    receiver.accept(audio())
    receiver.accept(EndFrame(SESSION, reason, ((0, 0),)))
    result = receiver.take_result()
    try:
        result.wait_ready()
        assert not result.complete
        assert "interrupted" in result.reason
    finally:
        result.close()


def test_empty_track_is_never_a_complete_capture():
    receiver = armed()
    start(receiver)
    receiver.accept(EndFrame(SESSION, EndReason.STREAM_STOPPED, ((0, None),)))
    result = receiver.take_result()
    try:
        result.wait_ready()
        assert not result.complete
        assert "no audio" in result.reason
    finally:
        result.close()


def test_startup_failure_closes_previously_created_track_stores():
    stores = []
    def factory(rate):
        if stores:
            raise OSError("synthetic startup failure")
        store = Store(rate)
        stores.append(store)
        return store
    receiver = armed((0, 2), factory=factory)
    with pytest.raises(ObsSessionError, match="could not start"):
        start(receiver)
    assert len(stores) == 1 and stores[0].closed
    assert receiver.state == "incomplete"
    receiver.close()


@pytest.mark.parametrize("failure", ["refuse", "raise_on_append", "error"])
def test_storage_failure_stops_without_claiming_complete(failure):
    receiver = armed()
    start(receiver)
    store = receiver._tracks[0].store
    setattr(store, failure, "synthetic error" if failure == "error" else True)
    with pytest.raises(ObsSessionError, match="storage"):
        receiver.accept(audio())
    assert store.blocks == []
    result = receiver.take_result()
    try:
        result.wait_ready()
        assert not result.complete
    finally:
        result.close()


def test_late_writer_error_invalidates_clean_end_after_drain():
    receiver = armed()
    start(receiver)
    receiver.accept(audio())
    receiver.accept(EndFrame(SESSION, EndReason.STREAM_STOPPED, ((0, 0),)))
    result = receiver.take_result()
    try:
        def drain_then_fail(cancelled):
            result.tracks[0].store.error = "synthetic writer failure"
        result.tracks[0].store.wait_ready = drain_then_fail
        result.wait_ready()
        assert not result.complete
        assert "storage failed" in result.reason
    finally:
        result.close()


def test_cancel_during_result_drain_closes_every_track():
    receiver = armed((0, 2))
    start(receiver)
    receiver.accept(EndFrame(SESSION, EndReason.DISARMED, ((0, None), (2, None))))
    result = receiver.take_result()
    with pytest.raises(TranscriptionCancelled):
        result.wait_ready(lambda: True)
    assert result.closed
    assert all(track.store.closed for track in result.tracks)


def test_cancel_discards_and_never_rearms_on_stale_events():
    receiver = armed()
    start(receiver)
    store = receiver._tracks[0].store
    receiver.cancel()
    assert store.closed
    assert receiver.state == "cancelled"
    with pytest.raises(ObsSessionError):
        receiver.notify_stream_started(SESSION)
    with pytest.raises(ObsSessionError):
        receiver.accept(audio())
    with pytest.raises(ObsSessionError):
        receiver.take_result()


def test_missing_terminal_frame_is_incomplete_and_result_transfers_once():
    receiver = armed()
    start(receiver)
    receiver.accept(audio())
    with pytest.raises(ObsSessionError):
        receiver.connection_lost()
    result = receiver.take_result()
    try:
        result.wait_ready()
        assert not result.complete
        with pytest.raises(ObsSessionError):
            receiver.take_result()
    finally:
        result.close()


def test_finite_large_stereo_does_not_overflow_during_downmix():
    receiver = armed()
    start(receiver)
    try:
        maximum = np.finfo(np.float32).max
        receiver.accept(audio(left=maximum, right=maximum))
        mixed = receiver._tracks[0].store.blocks[0]
        assert np.isfinite(mixed).all()
        assert np.all(mixed == maximum)
    finally:
        receiver.close()
