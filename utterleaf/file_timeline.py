"""Exact timeline-aware batching for recorded-file audio."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from fractions import Fraction

import numpy as np

from utterleaf.audio_batching import audio_windows
from utterleaf.transcript import TranscriptionCancelled


SAMPLE_RATE = 16_000
MAX_INPUT_SAMPLES = 60 * SAMPLE_RATE


@dataclass(frozen=True)
class TimelineAudioBlock:
    """A bounded mono block whose start is an absolute presentation time."""

    start: Fraction
    samples: np.ndarray = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self.start) is not Fraction:
            raise TypeError("Timeline block start must be a Fraction")
        if (
            not isinstance(self.samples, np.ndarray)
            or self.samples.ndim != 1
            or self.samples.dtype != np.dtype(np.float32)
            or not 1 <= self.samples.size <= MAX_INPUT_SAMPLES
            or not np.isfinite(self.samples).all()
        ):
            raise ValueError("Timeline audio blocks must be finite mono float32 audio of 1 sample to 60 seconds")


def _check_cancel(cancel: Callable[[], bool] | None) -> None:
    if cancel is not None and cancel():
        raise TranscriptionCancelled("Audio timeline batching cancelled")


def timeline_audio_windows(
    blocks: Iterable[TimelineAudioBlock],
    *,
    origin: Fraction,
    cancel: Callable[[], bool] | None = None,
) -> Iterator[TimelineAudioBlock]:
    """Normalize and batch timestamped blocks without filling timeline gaps.

    ``blocks`` remains owned by the caller; callers abandoning iteration should
    close their source iterator explicitly. At most one source block is held as
    lookahead while each contiguous run is passed to the shared quiet-boundary
    batcher. A positive gap starts a new run and is not represented by allocated
    silence. Overlaps and timestamps before ``origin`` fail visibly.
    """
    if type(origin) is not Fraction:
        raise TypeError("Timeline origin must be a Fraction")
    if cancel is not None and not callable(cancel):
        raise TypeError("cancel must be callable")

    source = iter(blocks)
    lookahead: TimelineAudioBlock | None = None

    def validate(block: TimelineAudioBlock) -> Fraction:
        if not isinstance(block, TimelineAudioBlock):
            raise TypeError("Timeline input must contain TimelineAudioBlock values")
        start = block.start - origin
        if start < 0:
            raise ValueError("Timeline audio starts before the selected origin")
        return start

    while True:
        _check_cancel(cancel)
        if lookahead is None:
            try:
                first = next(source)
            except StopIteration:
                return
        else:
            first = lookahead
            lookahead = None
        run_start = validate(first)
        expected = run_start + Fraction(first.samples.size, SAMPLE_RATE)

        def contiguous() -> Iterator[np.ndarray]:
            nonlocal lookahead, expected
            yield first.samples
            while True:
                _check_cancel(cancel)
                try:
                    candidate = next(source)
                except StopIteration:
                    return
                start = validate(candidate)
                if start < expected:
                    raise ValueError("Timeline audio blocks overlap or are out of order")
                if start > expected:
                    lookahead = candidate
                    return
                expected = start + Fraction(candidate.samples.size, SAMPLE_RATE)
                yield candidate.samples

        consumed = 0
        for window in audio_windows(contiguous(), cancel=lambda: cancel is not None and cancel()):
            _check_cancel(cancel)
            window_size = window.size
            start = run_start + Fraction(consumed, SAMPLE_RATE)
            consumed += window_size
            yield TimelineAudioBlock(start, window)
