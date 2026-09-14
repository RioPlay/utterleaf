from contextlib import closing
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
import threading

import numpy as np
import pytest

av = pytest.importorskip("av")

from utterleaf.file_media import (
    _media_clock,
    open_pyav_timeline,
    resample_timed_frames,
)
from utterleaf.transcript import TranscriptionCancelled


RATE = 16_000


def frame(rate, pts, *, value=1000, samples=None, fmt="s16"):
    samples = samples or rate // 10
    dtype = np.int32 if fmt == "s32" else np.int16
    result = av.AudioFrame.from_ndarray(
        np.full((1, samples), value, dtype=dtype), format=fmt, layout="mono"
    )
    result.sample_rate = rate
    result.time_base = Fraction(1, rate)
    result.pts = pts
    return result


@pytest.mark.parametrize("rate", [48_000, 44_100])
def test_resampler_preserves_exact_sample_count_and_flush_tail(rate):
    frames = [frame(rate, i * rate // 10, value=i + 1) for i in range(3)]
    result = list(resample_timed_frames(frames, origin=Fraction(0)))
    assert [item.start for item in result] == [
        Fraction(0), Fraction(1584, RATE), Fraction(3184, RATE), Fraction(4784, RATE)
    ]
    assert sum(item.samples.size for item in result) == 3 * RATE // 10
    assert result[-1].samples.size == 16
    assert np.max(result[0].samples) > 0


def test_negative_source_pts_normalizes_against_shared_origin():
    result = list(resample_timed_frames(
        [frame(48_000, -4800), frame(48_000, 0)], origin=Fraction(-1, 10)
    ))
    assert result[0].start == Fraction(-1, 10)
    assert result[1].start == Fraction(-1, 1000)


def test_quantized_millisecond_clock_does_not_accumulate_float_drift():
    frames = [frame(44_100, round(float(Fraction(i * 1024 * 1000, 44_100))), samples=1024)
              for i in range(100)]
    for item in frames:
        item.time_base = Fraction(1, 1000)
    result = list(resample_timed_frames(frames, origin=Fraction(0)))
    assert abs(sum(item.samples.size for item in result) - round(102_400 * RATE / 44_100)) <= 1
    expected_duration = Fraction(100 * 1024, 44_100)
    actual_end = result[-1].start + Fraction(result[-1].samples.size, RATE)
    assert abs(actual_end - expected_duration) <= Fraction(1, RATE)
    assert all(item.start == prior.start + Fraction(prior.samples.size, RATE)
               for prior, item in zip(result, result[1:]))


def test_gap_flushes_old_resampler_and_keeps_tail_before_new_run():
    first_run = [frame(48_000, 0, value=1000)]
    second_run = [frame(48_000, 9600, value=2000)]
    result = list(resample_timed_frames(first_run + second_run, origin=Fraction(0)))
    first_independent = list(resample_timed_frames(first_run, origin=Fraction(0)))
    second_independent = list(resample_timed_frames(second_run, origin=Fraction(0)))
    assert [item.start for item in result] == [
        Fraction(0), Fraction(1584, RATE), Fraction(1, 5), Fraction(1, 5) + Fraction(1584, RATE)
    ]
    assert [item.samples.size for item in result] == [1584, 16, 1584, 16]
    np.testing.assert_array_equal(
        np.concatenate([item.samples for item in result[:2]]),
        np.concatenate([item.samples for item in first_independent]),
    )
    np.testing.assert_array_equal(
        np.concatenate([item.samples for item in result[2:]]),
        np.concatenate([item.samples for item in second_independent]),
    )


@pytest.mark.parametrize("bad_frames, message", [
    ([frame(48_000, None)], "missing or invalid"),
    ([frame(48_000, 0), frame(48_000, 2400)], "overlap or move backward"),
    ([frame(48_000, 0)], "too coarse"),
    ([frame(48_000, 0), frame(48_000, 4800, fmt="s32")], "Changing audio formats"),
])
def test_invalid_timing_and_format_changes_fail(bad_frames, message):
    if message == "too coarse":
        bad_frames[0].time_base = Fraction(1, 100)
    with pytest.raises(ValueError, match=message):
        list(resample_timed_frames(bad_frames, origin=Fraction(0)))


def test_preroll_before_common_origin_fails():
    with pytest.raises(ValueError, match="before the shared file origin"):
        list(resample_timed_frames([frame(48_000, -1)], origin=Fraction(0)))


def test_exact_native_tick_gap_preserves_one_sample_offset():
    result = list(resample_timed_frames(
        [frame(16_000, 0, samples=1600), frame(16_000, 1601, samples=1600)],
        origin=Fraction(0),
    ))
    assert result[-1].start == Fraction(1601, 16_000)


def test_exact_native_tick_overlap_fails():
    with pytest.raises(ValueError, match="overlap or move backward"):
        list(resample_timed_frames(
            [frame(16_000, 0, samples=1600), frame(16_000, 1599, samples=1600)],
            origin=Fraction(0),
        ))


def test_one_tick_gap_at_44100_is_rejected_if_resampling_cannot_preserve_it():
    first = frame(44_100, 0, samples=91)
    second = frame(44_100, 92, samples=91)
    first.time_base = second.time_base = Fraction(1, 44_100)
    with pytest.raises(ValueError, match="gap is too small"):
        list(resample_timed_frames([first, second], origin=Fraction(0)))


def test_timestamp_unit_change_with_same_audio_format_fails():
    first = frame(48_000, 0)
    second = frame(48_000, 4800)
    second.time_base = Fraction(1, 44_100)
    with pytest.raises(ValueError, match="timestamp units"):
        list(resample_timed_frames([first, second], origin=Fraction(0)))


def test_consumer_resize_does_not_change_following_absolute_start():
    stream = resample_timed_frames(
        [frame(48_000, 0), frame(48_000, 4800)], origin=Fraction(0)
    )
    first = next(stream)
    first.samples.resize(1, refcheck=False)
    second = next(stream)
    assert second.start == Fraction(1584, RATE)
    stream.close()


def test_media_clock_fallback_uses_all_audio_video_starts_and_rejects_missing():
    streams = [
        SimpleNamespace(type="video", start_time=20, time_base=Fraction(1, 100)),
        SimpleNamespace(type="audio", start_time=-4800, time_base=Fraction(1, 48000)),
    ]
    origin, kind = _media_clock(SimpleNamespace(start_time=None, streams=streams))
    assert origin == Fraction(-1, 10) and kind == "all-stream-starts"
    streams[0].start_time = None
    with pytest.raises(ValueError, match="missing or invalid"):
        _media_clock(SimpleNamespace(start_time=None, streams=streams))


def _make_mkv(path: Path) -> None:
    with av.open(str(path), "w", format="matroska") as output:
        streams = [output.add_stream("flac", rate=16_000) for _ in range(2)]
        for stream in streams:
            stream.layout = "mono"
        for index, stream in enumerate(streams):
            audio = frame(16_000, index * 3200, value=index + 1, samples=1600)
            for packet in stream.encode(audio):
                output.mux(packet)
            for packet in stream.encode():
                output.mux(packet)


def test_real_matroska_tracks_share_origin_and_retain_late_track(tmp_path):
    path = tmp_path / "tracks.mkv"
    _make_mkv(path)
    with open_pyav_timeline(path, audio_track=0) as media:
        assert media.origin == 0 and media.origin_kind == "container"
        assert len(media.tracks) == 2
        assert [track.start for track in media.tracks] == [Fraction(0), Fraction(1, 5)]
        blocks = list(media.blocks)
        assert blocks and blocks[0].start == 0
    with open_pyav_timeline(path, audio_track=1) as media:
        second_blocks = list(media.blocks)
        assert second_blocks and second_blocks[0].start == Fraction(1, 5)
    path.rename(tmp_path / "closed.mkv")


def test_open_timeline_detects_source_mutation(tmp_path):
    path = tmp_path / "mutable.mkv"
    _make_mkv(path)
    with pytest.raises(RuntimeError, match="changed"):
        with open_pyav_timeline(path) as media:
            next(media.blocks)
            path.write_bytes(path.read_bytes() + b"x")
            next(media.blocks)


def test_early_close_releases_input_for_rename(tmp_path):
    path = tmp_path / "early-close.mkv"
    _make_mkv(path)
    with open_pyav_timeline(path) as media:
        media.blocks.close()
    path.rename(tmp_path / "renamed.mkv")


def test_cancellation_is_checked_before_and_after_first_yield():
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(TranscriptionCancelled):
        list(resample_timed_frames([frame(48_000, 0)], origin=Fraction(0), cancel=cancel))
    cancel.clear()
    stream = resample_timed_frames([frame(48_000, 0), frame(48_000, 4800)], origin=Fraction(0), cancel=cancel)
    next(stream)
    cancel.set()
    with pytest.raises(TranscriptionCancelled):
        next(stream)


def test_real_aac_priming_uses_decoded_presentation_time(tmp_path):
    path = tmp_path / "priming.m4a"
    rate = 48_000
    with av.open(str(path), "w", format="mp4") as output:
        track = output.add_stream("aac", rate=rate)
        track.layout = "mono"
        for position in range(0, rate // 2, 1024):
            audio = frame(rate, position, value=8000, samples=min(1024, rate // 2 - position))
            for packet in track.encode(audio):
                output.mux(packet)
        for packet in track.encode():
            output.mux(packet)
    with av.open(str(path)) as container:
        first_packet = next(packet for packet in container.demux(audio=0) if packet.size)
        assert first_packet.pts < 0  # Encoder priming precedes audible content.
        assert container.start_time == 0
    with av.open(str(path)) as container:
        decoded = list(container.decode(audio=0))
        assert decoded[0].pts == 0
        assert np.any(decoded[0].to_ndarray())
        # The decoder may retain final codec padding. Account for decoded audio,
        # not an assumed equality between encoded input and decoded sample count.
        decoded_duration = sum(Fraction(item.samples, item.sample_rate) for item in decoded)
    with open_pyav_timeline(path) as media:
        assert media.origin == 0 and media.origin_kind == "container"
        blocks = list(media.blocks)
        assert blocks[0].start == 0
        assert abs(Fraction(sum(item.samples.size for item in blocks), RATE) - decoded_duration) <= Fraction(1, RATE)
