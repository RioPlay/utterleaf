"""Bounded audio batching with conservative quiet-interval boundaries."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator

import numpy as np

from utterleaf.transcript import TranscriptionCancelled


SAMPLE_RATE = 16_000
MAX_BATCH_SECONDS = 30
QUIET_SEARCH_SECONDS = 5
RMS_WINDOW_SECONDS = 0.020
MIN_QUIET_SECONDS = 0.120
QUIET_RMS = 0.01
MAX_INPUT_BLOCK_SECONDS = 60

_BATCH_SAMPLES = SAMPLE_RATE * MAX_BATCH_SECONDS
_SEARCH_SAMPLES = SAMPLE_RATE * QUIET_SEARCH_SECONDS
_RMS_SAMPLES = int(SAMPLE_RATE * RMS_WINDOW_SECONDS)
_MIN_QUIET_WINDOWS = round(MIN_QUIET_SECONDS / RMS_WINDOW_SECONDS)
_MAX_INPUT_SAMPLES = SAMPLE_RATE * MAX_INPUT_BLOCK_SECONDS


def _check_cancel(cancel: Callable[[], bool] | None) -> None:
    if cancel is not None and cancel():
        raise TranscriptionCancelled("Audio batching cancelled")


def _quiet_boundary(audio: np.ndarray) -> int:
    """Choose the latest end of a verified quiet run, or the hard limit."""
    search_start = len(audio) - _SEARCH_SAMPLES
    frames = audio[search_start:].reshape(-1, _RMS_SAMPLES)
    rms = np.sqrt(np.mean(np.square(frames, dtype=np.float64), axis=1))
    quiet = rms <= QUIET_RMS

    run = 0
    latest = None
    for index, is_quiet in enumerate(quiet):
        run = run + 1 if is_quiet else 0
        if run >= _MIN_QUIET_WINDOWS:
            latest = search_start + (index + 1) * _RMS_SAMPLES
    return len(audio) if latest is None else latest


def audio_windows(
    blocks: Iterable[np.ndarray], *, cancel: Callable[[], bool] | None = None
) -> Iterator[np.ndarray]:
    """Yield every float32 sample once in ordered batches of at most 30 seconds.

    A batch that reaches 30 seconds ends at the latest 20 ms boundary completing
    at least 120 ms of continuous quiet within its final five seconds. If none is
    found, it ends at 30 seconds. At most one 30-second working buffer is retained.
    """
    if cancel is not None and not callable(cancel):
        raise TypeError("cancel must be callable")

    buffer = np.empty(_BATCH_SAMPLES, dtype=np.float32)
    filled = 0
    for block in blocks:
        _check_cancel(cancel)
        if (
            not isinstance(block, np.ndarray)
            or block.ndim != 1
            or block.size > _MAX_INPUT_SAMPLES
            or block.dtype != np.float32
            or not np.isfinite(block).all()
        ):
            raise ValueError("The decoder returned an invalid or oversized audio block")
        position = 0
        while position < len(block):
            _check_cancel(cancel)
            count = min(_BATCH_SAMPLES - filled, len(block) - position)
            buffer[filled : filled + count] = block[position : position + count]
            filled += count
            position += count
            if filled == _BATCH_SAMPLES:
                boundary = _quiet_boundary(buffer)
                yield buffer[:boundary].copy()
                remaining = filled - boundary
                if remaining:
                    buffer[:remaining] = buffer[boundary:filled]
                filled = remaining
    _check_cancel(cancel)
    if filled:
        yield buffer[:filled].copy()
