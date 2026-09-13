from types import SimpleNamespace
import threading

import numpy as np
import pytest

from utterleaf.config import Config
from utterleaf.transcribe import CTranslateEngine, TranscriptionLimitError, _infer_lock


def _segment(index, text="word"):
    return SimpleNamespace(start=index / 10, end=(index + 1) / 10, text=text)


def _engine(output, *, called=None):
    class Model:
        def transcribe(self, audio, **kwargs):
            if called is not None:
                called.set()
            return output, SimpleNamespace(language="en")
    return CTranslateEngine(Model())


def test_segment_limit_stops_and_closes_model_iterator():
    closed = threading.Event()

    def output():
        try:
            yield _segment(0)
            yield _segment(1)
            yield _segment(2)
            pytest.fail("Model iterator was consumed after the configured limit")
        finally:
            closed.set()

    engine = _engine(output())
    with pytest.raises(TranscriptionLimitError, match="too many"):
        engine.transcribe_segments(np.zeros(16000, np.float32), Config(), max_segments=2)
    assert closed.is_set()
    assert _infer_lock.acquire(blocking=False)
    _infer_lock.release()


def test_per_segment_utf8_limit_closes_before_consuming_more_output():
    closed = threading.Event()

    def output():
        try:
            yield _segment(0, "éé")
            pytest.fail("Model iterator continued after oversized UTF-8 text")
        finally:
            closed.set()

    with pytest.raises(TranscriptionLimitError, match="oversized"):
        _engine(output()).transcribe_segments(
            np.zeros(16000, np.float32), Config(), max_segment_text_bytes=3
        )
    assert closed.is_set()


def test_obviously_oversized_text_is_rejected_before_utf8_copy():
    class GuardedText(str):
        def encode(self, *args, **kwargs):
            pytest.fail("Oversized text was copied before its character lower bound was checked")

    with pytest.raises(TranscriptionLimitError, match="oversized"):
        _engine(iter([_segment(0, GuardedText("xxxx"))])).transcribe_segments(
            np.zeros(16000, np.float32), Config(), max_segment_text_bytes=3
        )


def test_total_text_limit_is_checked_during_iteration():
    closed = threading.Event()
    progress = []

    def output():
        try:
            yield _segment(0, "abc")
            yield _segment(1, "def")
            pytest.fail("Model iterator continued after aggregate text limit")
        finally:
            closed.set()

    with pytest.raises(TranscriptionLimitError, match="too much"):
        _engine(output()).transcribe_segments(
            np.zeros(16000, np.float32), Config(), max_total_text_bytes=5,
            progress=lambda *args: progress.append(args),
        )
    assert closed.is_set()
    assert len(progress) == 1


def test_invalid_timestamp_closes_iterator_and_releases_inference_lock():
    closed = threading.Event()

    def output():
        try:
            yield SimpleNamespace(start=float("nan"), end=1, text="bad")
            pytest.fail("Model iterator continued after invalid timestamp")
        finally:
            closed.set()

    with pytest.raises(ValueError, match="finite"):
        _engine(output()).transcribe_segments(
            np.zeros(16000, np.float32), Config(), max_segments=10
        )
    assert closed.is_set()
    assert _infer_lock.acquire(blocking=False)
    _infer_lock.release()


def test_default_limits_remain_unset_for_existing_callers():
    result = _engine(iter([_segment(0, "a"), _segment(1, "b")])).transcribe_segments(
        np.zeros(16000, np.float32), Config()
    )
    assert [segment.text for segment in result.segments] == ["a", "b"]


@pytest.mark.parametrize("kwargs", [
    {"max_segments": -1},
    {"max_segments": True},
    {"max_segment_text_bytes": 1.5},
    {"max_total_text_bytes": "10"},
])
def test_invalid_limits_fail_before_model_or_lock(kwargs):
    called = threading.Event()
    engine = _engine(iter(()), called=called)
    with pytest.raises(ValueError, match="nonnegative integers"):
        engine.transcribe_segments(np.zeros(1, np.float32), Config(), **kwargs)
    assert not called.is_set()
    assert _infer_lock.acquire(blocking=False)
    _infer_lock.release()
