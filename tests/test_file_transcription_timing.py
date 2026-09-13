from contextlib import contextmanager
from fractions import Fraction
import threading
import wave

import numpy as np
import pytest

from utterleaf.config import Config
from utterleaf.file_decoder import DecoderSetupError
from utterleaf.file_media import AudioTrack, TimedMedia
from utterleaf.file_timeline import TimelineAudioBlock
from utterleaf.file_transcription import transcribe_file, WavFormatUnsupported
from utterleaf.transcribe import CPU, CTranslateEngine
from utterleaf.transcript import Segment, Transcript, TranscriptionCancelled, render_transcript


def block(start, seconds=1):
    return TimelineAudioBlock(Fraction(start), np.zeros(seconds * 16000, dtype=np.float32))


def media(blocks, *, origin=10):
    return TimedMedia(
        Fraction(origin), "container",
        (AudioTrack(0, 2, "pcm_s16le", 1, 16000, Fraction(origin)),),
        iter(blocks),
    )


def install_external(monkeypatch, tmp_path, value):
    path = tmp_path / "timed.mkv"
    path.write_bytes(b"synthetic local media")
    monkeypatch.setattr("utterleaf.file_decoder.decoder_selection", lambda: {"selected": True})

    @contextmanager
    def opened(selected, **kwargs):
        assert selected == path
        yield value() if callable(value) else value

    monkeypatch.setattr("utterleaf.file_external.open_ffmpeg_timeline", opened)
    monkeypatch.setattr(
        "utterleaf.file_media.open_pyav_timeline",
        lambda *a, **k: pytest.fail("an explicit decoder must use the external timeline"),
    )
    return path


def install_engine(monkeypatch, recognize):
    engine = CTranslateEngine(None)
    monkeypatch.setattr(engine, "transcribe_segments", recognize)
    monkeypatch.setattr("utterleaf.transcribe.load_model", lambda cfg, *a: engine)
    return engine


def test_recording_timing_normalizes_origin_once_and_preserves_gaps(tmp_path, monkeypatch):
    path = install_external(monkeypatch, tmp_path, media([block(12), block(15)]))
    seen = []

    def recognize(audio, cfg, **kwargs):
        seen.append(audio.size)
        return Transcript((Segment(0.25, 0.75, f"window {len(seen)}"),), "en")

    install_engine(monkeypatch, recognize)
    result = transcribe_file(path, Config(), timing="recording")

    assert seen == [16000, 16000]
    assert result.segments == (
        Segment(2.25, 2.75, "window 1"),
        Segment(5.25, 5.75, "window 2"),
    )
    assert "00:00:02,250 --> 00:00:02,750" in render_transcript(result, "srt")
    assert "00:00:05.250 --> 00:00:05.750" in render_transcript(result, "vtt")


def test_window_size_and_start_are_captured_before_model_mutation(tmp_path, monkeypatch):
    path = install_external(monkeypatch, tmp_path, media([block(12), block(15)]))
    calls = 0

    def recognize(audio, cfg, **kwargs):
        nonlocal calls
        calls += 1
        audio.resize(0, refcheck=False)
        return Transcript((Segment(0.5, 2, str(calls)),), "en")

    install_engine(monkeypatch, recognize)
    result = transcribe_file(path, Config(), timing="recording")
    assert result.segments == (Segment(2.5, 3.0, "1"), Segment(5.5, 6.0, "2"))


def test_late_timeline_failure_returns_no_partial_transcript(tmp_path, monkeypatch):
    closed = []

    def value():
        def blocks():
            try:
                yield block(10)
                yield block(12)
                raise RuntimeError("late source identity failure")
            finally:
                closed.append(True)
        return media(blocks())

    path = install_external(monkeypatch, tmp_path, value)
    calls = []
    install_engine(monkeypatch, lambda *a, **k: calls.append(True) or
                   Transcript((Segment(0, 1, "provisional"),), "en"))
    progress = []
    with pytest.raises(RuntimeError, match="late source identity"):
        transcribe_file(path, Config(), timing="recording",
                        progress=lambda *item: progress.append(item))
    assert calls == [True] and closed == [True]
    assert ("complete", 1.0) not in progress


def test_recording_mode_keeps_offline_gpu_fallback_and_cancellation(tmp_path, monkeypatch):
    path = install_external(monkeypatch, tmp_path, media([block(10)]))
    cancel = threading.Event()
    calls = []

    def load(cfg, accelerator=None):
        assert cfg.allow_network is False
        calls.append(accelerator)
        engine = CTranslateEngine(None)
        def recognize(*args, **kwargs):
            if accelerator is None:
                raise RuntimeError("CUDA unavailable")
            cancel.set()
            return Transcript((), "en")
        monkeypatch.setattr(engine, "transcribe_segments", recognize)
        return engine

    monkeypatch.setattr("utterleaf.transcribe.load_model", load)
    monkeypatch.setattr("utterleaf.transcribe.mark_cuda_unusable", lambda: None)
    monkeypatch.setattr("utterleaf.transcribe.reset_engine", lambda: None)
    with pytest.raises(TranscriptionCancelled):
        transcribe_file(path, Config(allow_network=True), timing="recording", cancel=cancel)
    assert calls == [None, CPU]


def test_packaged_pcm_recording_needs_no_selected_tools(tmp_path, monkeypatch):
    path = tmp_path / "plain.wav"
    with wave.open(str(path), "wb") as output:
        output.setparams((1, 2, 16000, 0, "NONE", ""))
        output.writeframes(np.zeros(16000, dtype="<i2").tobytes())

    monkeypatch.setattr(
        "utterleaf.file_decoder.decoder_selection",
        lambda: pytest.fail("ordinary PCM must not inspect selected tools"),
    )
    monkeypatch.setattr(
        "utterleaf.file_external.open_ffmpeg_timeline",
        lambda *a, **k: pytest.fail("ordinary PCM must not launch FFmpeg"),
    )
    monkeypatch.setattr(
        "utterleaf.file_media.open_pyav_timeline",
        lambda *a, **k: pytest.fail("ordinary PCM must not open PyAV"),
    )
    starts = []
    install_engine(monkeypatch, lambda audio, *a, **k:
                   starts.append(audio.size) or Transcript((Segment(0, 1, "pcm"),), "en"))

    assert transcribe_file(path, Config(), timing="recording").segments == (
        Segment(0, 1, "pcm"),
    )
    assert starts == [16000]
    path.rename(tmp_path / "released.wav")


@pytest.mark.parametrize("invalid", ("absolute", None, True, ["recording"]))
def test_invalid_timing_fails_before_model_or_file_work(monkeypatch, invalid):
    monkeypatch.setattr(
        "utterleaf.transcribe.load_model",
        lambda *a, **k: pytest.fail("invalid timing must fail before model loading"),
    )
    monkeypatch.setattr(
        "utterleaf.file_transcription.iter_local_audio",
        lambda *a, **k: pytest.fail("invalid timing must fail before decoding"),
    )
    with pytest.raises(ValueError, match="relative.*recording"):
        transcribe_file("missing.wav", Config(), timing=invalid)


def test_packaged_wav_cannot_fallback_after_emitting_audio(tmp_path, monkeypatch):
    path = tmp_path / "late-broken.wav"
    path.write_bytes(b"nonempty fixture")

    def partial(*args, **kwargs):
        yield np.zeros(16000, dtype=np.float32)
        raise WavFormatUnsupported("late malformed WAV")

    monkeypatch.setattr("utterleaf.file_transcription._iter_pcm_wav", partial)
    monkeypatch.setattr(
        "utterleaf.file_decoder.decoder_selection",
        lambda: pytest.fail("a partially decoded WAV must not fall back"),
    )
    install_engine(monkeypatch, lambda *a, **k: Transcript((Segment(0, 1, "provisional"),), "en"))
    with pytest.raises(ValueError, match="became malformed"):
        transcribe_file(path, Config(), timing="recording")


def test_recording_without_pyav_or_selected_tools_has_actionable_setup(tmp_path, monkeypatch):
    path = tmp_path / "clip.mp3"
    path.write_bytes(b"synthetic local media")
    monkeypatch.setattr("utterleaf.file_decoder.decoder_selection", lambda: None)

    @contextmanager
    def unavailable(*args, **kwargs):
        raise DecoderSetupError("development adapter unavailable")
        yield

    monkeypatch.setattr("utterleaf.file_media.open_pyav_timeline", unavailable)
    monkeypatch.setattr(
        "utterleaf.transcribe.load_model",
        lambda *a, **k: pytest.fail("missing timing support must fail before model loading"),
    )
    with pytest.raises(DecoderSetupError, match="FFmpeg and FFprobe.*More formats"):
        transcribe_file(path, Config(), timing="recording")
