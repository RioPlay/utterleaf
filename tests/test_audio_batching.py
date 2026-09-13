"""Exact, bounded quiet-aware audio batching."""

import numpy as np
import pytest

from utterleaf import audio_batching as batching
from utterleaf.transcript import TranscriptionCancelled


SECOND = batching.SAMPLE_RATE


def _assert_exact_partition(blocks, windows):
    expected = np.concatenate(blocks) if blocks else np.array([], dtype=np.float32)
    actual = np.concatenate(windows) if windows else np.array([], dtype=np.float32)
    np.testing.assert_array_equal(actual, expected)
    assert all(window.dtype == np.float32 for window in windows)
    assert all(0 < len(window) <= 30 * SECOND for window in windows)


def test_prefers_latest_verified_quiet_interval_near_batch_end():
    audio = np.full(35 * SECOND, 0.2, dtype=np.float32)
    audio[27 * SECOND : 27 * SECOND + 10 * 320] = 0

    blocks = [audio]
    windows = list(batching.audio_windows(blocks))

    boundary = 27 * SECOND + 10 * 320
    assert [len(window) for window in windows] == [boundary, len(audio) - boundary]
    _assert_exact_partition(blocks, windows)


def test_exactly_120ms_at_threshold_is_a_verified_quiet_interval():
    audio = np.full(31 * SECOND, 0.2, dtype=np.float32)
    start = 28 * SECOND
    audio[start : start + 6 * 320] = batching.QUIET_RMS

    windows = list(batching.audio_windows([audio]))

    boundary = start + 6 * 320
    assert [len(window) for window in windows] == [boundary, len(audio) - boundary]
    _assert_exact_partition([audio], windows)


def test_short_or_loud_gap_is_not_a_quiet_boundary():
    audio = np.full(31 * SECOND, 0.2, dtype=np.float32)
    audio[28 * SECOND : 28 * SECOND + 5 * 320] = 0
    audio[29 * SECOND : 29 * SECOND + 6 * 320] = 0.02

    blocks = [audio]
    windows = list(batching.audio_windows(blocks))

    assert [len(window) for window in windows] == [30 * SECOND, SECOND]
    _assert_exact_partition(blocks, windows)


def test_all_silence_prefers_latest_boundary_and_preserves_old_windows():
    audio = np.zeros(61 * SECOND, dtype=np.float32)

    blocks = [audio[: 60 * SECOND], audio[60 * SECOND :]]
    windows = list(batching.audio_windows(blocks))

    assert [len(window) for window in windows] == [30 * SECOND, 30 * SECOND, SECOND]
    _assert_exact_partition(blocks, windows)


def test_no_quiet_interval_uses_fixed_30_second_fallback():
    audio = np.full(65 * SECOND, 0.25, dtype=np.float32)

    blocks = [audio[: 60 * SECOND], audio[60 * SECOND :]]
    windows = list(batching.audio_windows(blocks))

    assert [len(window) for window in windows] == [30 * SECOND, 30 * SECOND, 5 * SECOND]
    _assert_exact_partition(blocks, windows)


def test_uneven_blocks_preserve_samples_without_aliasing():
    blocks = [
        np.arange(123, dtype=np.float32),
        np.linspace(0.1, 0.3, 60 * SECOND, dtype=np.float32),
        np.arange(456, dtype=np.float32),
    ]

    windows = list(batching.audio_windows(iter(blocks)))

    assert [len(window) for window in windows] == [30 * SECOND, 30 * SECOND, 579]
    _assert_exact_partition(blocks, windows)
    assert not np.shares_memory(windows[0], windows[1])


def test_cancellation_callable_is_checked_during_input_copy():
    calls = 0

    def cancel():
        nonlocal calls
        calls += 1
        return calls == 3

    with pytest.raises(TranscriptionCancelled, match="batching cancelled"):
        list(batching.audio_windows([np.ones(60 * SECOND, dtype=np.float32)], cancel=cancel))


def test_noncallable_cancellation_is_refused():
    with pytest.raises(TypeError, match="cancel must be callable"):
        list(batching.audio_windows([], cancel=object()))


@pytest.mark.parametrize(
    "block",
    [
        np.zeros((2, 2), dtype=np.float32),
        np.zeros(60 * SECOND + 1, dtype=np.float32),
        np.array([np.nan], dtype=np.float32),
        np.array([np.inf], dtype=np.float32),
        np.array(["private"]),
        np.zeros(2, dtype=np.float64),
        np.zeros(2, dtype=np.int16),
        [0.0],
    ],
)
def test_invalid_input_blocks_are_refused(block):
    with pytest.raises(ValueError, match="invalid or oversized"):
        list(batching.audio_windows([block]))


def test_empty_blocks_do_not_create_empty_windows():
    empty = np.array([], dtype=np.float32)
    assert list(batching.audio_windows([empty, empty])) == []
