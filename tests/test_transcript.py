import threading
from types import SimpleNamespace

import numpy as np
import pytest

from utterleaf.config import Config
from utterleaf.transcribe import CTranslateEngine, _infer_lock
from utterleaf.transcript import (
    Segment, Transcript, TranscriptionCancelled, export_transcript, render_transcript,
)


@pytest.mark.parametrize("start,end", [(-1, 2), (2, 1), (float("nan"), 1), (0, float("inf"))])
def test_reject_invalid_timing(start, end):
    with pytest.raises(ValueError):
        Segment(start, end, "test")


def test_reject_out_of_order_segments():
    with pytest.raises(ValueError):
        Transcript((Segment(2, 3, "later"), Segment(1, 2, "earlier")))


def test_subtitle_rounding_unicode_and_literal_markup():
    result = Transcript((Segment(59.9996, 3600.001, " café <東京>\n\nscratch that "),))
    assert render_transcript(result, "txt") == "café <東京>\n\nscratch that\n"
    assert render_transcript(result, "srt") == (
        "1\n00:01:00,000 --> 01:00:00,001\ncafé &lt;東京&gt; scratch that\n"
    )
    assert render_transcript(result, "vtt").startswith("WEBVTT\n\n1\n00:01:00.000 --> 01:00:00.001")


def test_no_fabricated_subtitle_duration():
    with pytest.raises(ValueError, match="no duration"):
        render_transcript(Transcript((Segment(1, 1.0001, "word"),)), "srt")


def test_silence_and_bad_format():
    assert render_transcript(Transcript(()), "txt") == ""
    assert render_transcript(Transcript(()), "vtt") == "WEBVTT\n\n"
    with pytest.raises(ValueError):
        render_transcript(Transcript(()), "json")


def test_export_requires_explicit_overwrite_and_cleans_temp(tmp_path):
    result = Transcript((Segment(0, 1, "日本語"),))
    path = tmp_path / "result.txt"
    path.write_text("previous", encoding="utf-8")
    with pytest.raises(FileExistsError):
        export_transcript(result, path)
    assert path.read_text(encoding="utf-8") == "previous"
    assert list(tmp_path.iterdir()) == [path]
    export_transcript(result, path, overwrite=True)
    assert path.read_text(encoding="utf-8") == "日本語\n"


def test_model_segments_preserve_words_timing_and_release_lock_on_cancel():
    cancel = threading.Event()

    class Model:
        def transcribe(self, audio, **kwargs):
            def segments():
                yield SimpleNamespace(start=0.125, end=1.25, text=" scratch that ")
                cancel.set()
                yield SimpleNamespace(start=2, end=3, text="discard")
            return segments(), SimpleNamespace(language="en")

    engine = CTranslateEngine(Model())
    progress = []
    with pytest.raises(TranscriptionCancelled):
        engine.transcribe_segments(np.zeros(48000), Config(), cancel=cancel,
                                   progress=lambda *args: progress.append(args))
    assert len(progress) == 1
    assert _infer_lock.acquire(blocking=False)
    _infer_lock.release()


def test_model_segments_are_unedited():
    class Model:
        def transcribe(self, audio, **kwargs):
            return iter([SimpleNamespace(start=0.125, end=1.25, text=" scratch that ")]), SimpleNamespace(language="en")

    result = CTranslateEngine(Model()).transcribe_segments(np.zeros(48000), Config())
    assert result.segments == (Segment(0.125, 1.25, " scratch that "),)
    assert result.text == "scratch that"
