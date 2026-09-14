from fractions import Fraction

import numpy as np
import pytest

from utterleaf.file_timeline import TimelineAudioBlock, timeline_audio_windows
from utterleaf.transcript import TranscriptionCancelled


RATE = 16_000
F = Fraction


def block(start, count, value=0.25):
    return TimelineAudioBlock(F(start), np.full(count, value, dtype=np.float32))


def test_negative_origin_normalizes_raw_pts_to_nonnegative_windows():
    first = list(timeline_audio_windows([block(F(-1), RATE)], origin=F(-1)))
    late = list(timeline_audio_windows([block(F(-4, 5), RATE)], origin=F(-1)))
    assert [item.start for item in first] == [F(0)]
    assert [item.start for item in late] == [F(1, 5)]
    assert sum(item.samples.size for item in first) == RATE


def test_late_absolute_start_is_normalized_once():
    result = list(timeline_audio_windows([block(F(3, 2), RATE)], origin=F(1)))
    assert [item.start for item in result] == [F(1, 2)]
    assert sum(item.samples.size for item in result) == RATE


def test_common_origin_and_unequal_starts_preserve_offsets_without_silence():
    result = list(timeline_audio_windows(
        [block(2, RATE // 2, 1), block(5, RATE // 2, 2)], origin=F(1)
    ))
    assert [item.start for item in result] == [F(1), F(4)]
    assert [item.samples[0] for item in result] == [1, 2]
    assert sum(item.samples.size for item in result) == RATE


def test_multi_minute_gap_is_lazy_and_does_not_allocate_silence():
    pulled = []

    def source():
        pulled.append(1)
        yield block(0, 10)
        pulled.append(2)
        yield block(3600, 10)

    result = list(timeline_audio_windows(source(), origin=F(0)))
    assert pulled == [1, 2]
    assert [item.start for item in result] == [F(0), F(3600)]
    assert [item.samples.size for item in result] == [10, 10]


def test_one_block_lookahead_does_not_pull_past_gap():
    pulled = []

    def source():
        for value in (0, 2, 4):
            pulled.append(value)
            yield block(value, 10)

    stream = timeline_audio_windows(source(), origin=F(0))
    assert next(stream).start == 0
    assert pulled == [0, 2]
    assert next(stream).start == 2
    assert pulled == [0, 2, 4]
    stream.close()


def test_consumer_mutation_does_not_change_following_timestamp():
    stream = timeline_audio_windows(
        [block(0, 31 * RATE, 0.2)], origin=F(0)
    )
    first = next(stream)
    assert first.start == 0 and first.samples.size == 30 * RATE
    first.samples.resize(1, refcheck=False)
    second = next(stream)
    assert second.start == 30
    assert second.samples.size == RATE
    stream.close()


def test_quiet_batching_preserves_samples_and_exact_rational_offsets():
    first = np.full(35 * RATE, 0.2, dtype=np.float32)
    first[27 * RATE:27 * RATE + 3200] = 0
    result = list(timeline_audio_windows(
        [TimelineAudioBlock(F(1, 3), first)], origin=F(1, 3)
    ))
    assert [item.start for item in result] == [F(0), F(27, 1) + F(1, 5)]
    assert sum(item.samples.size for item in result) == first.size
    np.testing.assert_array_equal(np.concatenate([item.samples for item in result]), first)


@pytest.mark.parametrize("bad", [
    TimelineAudioBlock(F(0), np.ones(3, dtype=np.float32)),
    TimelineAudioBlock(F(1), np.ones(3, dtype=np.float32)),
])
def test_overlap_and_out_of_order_fail_visibly(bad):
    start = F(0) if bad.start == 0 else F(1)
    with pytest.raises(ValueError, match="before|overlap"):
        list(timeline_audio_windows([block(start, 10), bad], origin=F(0)))


def test_pre_origin_and_invalid_blocks_fail():
    with pytest.raises(ValueError, match="before"):
        list(timeline_audio_windows([block(-1, 10)], origin=F(0)))
    with pytest.raises(ValueError, match="1 sample"):
        list(timeline_audio_windows([TimelineAudioBlock(F(0), np.zeros(0, dtype=np.float32))], origin=F(0)))
    with pytest.raises(TypeError, match="Fraction"):
        list(timeline_audio_windows([block(0, 1)], origin=0))


def test_cancellation_checked_at_run_boundary():
    calls = 0

    def cancel():
        nonlocal calls
        calls += 1
        return calls >= 3

    with pytest.raises(TranscriptionCancelled):
        list(timeline_audio_windows([block(0, 10), block(2, 10)], origin=F(0), cancel=cancel))


def test_decreasing_timestamp_fails_as_out_of_order():
    with pytest.raises(ValueError, match="overlap or are out of order"):
        list(timeline_audio_windows([block(2, 10), block(1, 10)], origin=F(0)))


def test_source_iterator_is_caller_owned_and_not_closed():
    class Source:
        def __init__(self):
            self.closed = False

        def __iter__(self):
            return iter([block(0, 10)])

        def close(self):
            self.closed = True

    source = Source()
    list(timeline_audio_windows(source, origin=F(0)))
    assert source.closed is False
