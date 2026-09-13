"""Long-file audio bounds, global timing, track isolation and early cleanup."""

from contextlib import closing
import threading
import wave

import numpy as np
import pytest

from utterleaf import file_transcription as files
from utterleaf.config import Config
from utterleaf.transcribe import CTranslateEngine
from utterleaf.transcript import Segment, Transcript, TranscriptionCancelled, render_transcript


def install_engine(monkeypatch, recognize):
    engine = CTranslateEngine(None)
    monkeypatch.setattr(engine, "transcribe_segments", recognize)
    def load(cfg):
        assert cfg.allow_network is False
        return engine
    monkeypatch.setattr("utterleaf.transcribe.load_model", load)


def test_601_second_file_is_consumed_incrementally_with_global_subtitles(tmp_path, monkeypatch):
    path = tmp_path / "long.wav"
    second = np.zeros(16000, dtype="<i2").tobytes()
    with wave.open(str(path), "wb") as out:
        out.setparams((1, 2, 16000, 0, "NONE", ""))
        for _ in range(601):
            out.writeframesraw(second)
    decoded = []
    recognized = []
    decoder = files.iter_local_audio
    def observe(*args, **kwargs):
        with closing(decoder(*args, **kwargs)) as blocks:
            for block in blocks:
                decoded.append(len(block))
                yield block
    monkeypatch.setattr(files, "iter_local_audio", observe)
    monkeypatch.setattr(files, "decode_local_file", lambda *a, **kw: pytest.fail("Whole-file array route"))
    # Legacy helper limits must have no effect on the streaming application path.
    monkeypatch.setattr(files, "MAX_AUDIO_SECONDS", 0.1)
    monkeypatch.setattr(files, "MAX_FILE_BYTES", 1)
    def recognize(audio, cfg, **kwargs):
        recognized.append(len(audio))
        # Decoding pauses at a model window, including the final one-second tail.
        assert sum(decoded) == sum(recognized)
        assert audio.dtype == np.float32 and len(audio) <= 30 * 16000
        kwargs["progress"]("recognizing", 1.0)
        return Transcript((Segment(0, len(audio) / 16000, str(len(recognized))),), "en")
    install_engine(monkeypatch, recognize)
    progress = []
    result = files.transcribe_file(path, Config(allow_network=True), progress=lambda *args: progress.append(args))
    assert recognized == [480000] * 20 + [16000]
    assert len(decoded) == 601 and max(decoded) == 16000
    assert [s.start for s in result.segments] == list(range(0, 601, 30))
    assert result.segments[-1].end == 601
    assert "00:10:00,000 --> 00:10:01,000" in render_transcript(result, "srt")
    assert "00:10:00.000 --> 00:10:01.000" in render_transcript(result, "vtt")
    assert all(fraction is None for phase, fraction in progress if phase == "recognizing")
    assert progress[-1] == ("complete", 1.0)
    assert list(tmp_path.iterdir()) == [path]


def test_windows_preserve_uneven_block_samples_without_aliasing():
    blocks = [np.arange(123, dtype=np.float32), np.arange(960000, dtype=np.float32)]
    windows = list(files.audio_windows(iter(blocks)))
    assert [len(x) for x in windows] == [480000, 480000, 123]
    np.testing.assert_array_equal(np.concatenate(windows), np.concatenate(blocks))
    assert not np.shares_memory(windows[0], windows[1])


@pytest.mark.parametrize("block", [np.zeros((2, 2)), np.zeros(960001), np.array([np.nan]),
                                      np.array([np.inf]), np.array(["private"]), np.zeros(2, dtype=np.int16)])
def test_bad_decoder_block_is_refused(block):
    with pytest.raises(ValueError, match="invalid or oversized"):
        list(files.audio_windows(iter([block])))


@pytest.mark.parametrize("failure", ["cancel", "decode", "model", "timing"])
def test_early_failure_closes_decoder_and_returns_no_partial_transcript(monkeypatch, failure):
    cancel = threading.Event()
    events = []
    def decode(*args, **kwargs):
        try:
            events.append("decode1")
            yield np.zeros(480000, dtype=np.float32)
            if failure == "decode":
                raise RuntimeError("Damaged later audio")
            events.append("decode2")
            yield np.zeros(16000, dtype=np.float32)
        finally:
            events.append("closed")
    monkeypatch.setattr(files, "iter_local_audio", decode)
    def recognize(audio, cfg, **kwargs):
        events.append("recognize")
        if failure == "cancel":
            cancel.set()
        if failure == "model":
            raise RuntimeError("Model failed")
        if failure == "timing":
            return Transcript((Segment(31, 32, "Do not silently discard this"),))
        return Transcript((Segment(0, 1, "Unsaved fixture"),))
    install_engine(monkeypatch, recognize)
    progress = []
    expected = TranscriptionCancelled if failure == "cancel" else ValueError if failure == "timing" else RuntimeError
    with pytest.raises(expected):
        files.transcribe_file("fixture.wav", Config(), cancel=cancel, progress=lambda *x: progress.append(x))
    assert events == ["decode1", "recognize", "closed"]
    assert ("complete", 1.0) not in progress


def test_model_tail_estimate_preserves_words_and_stays_inside_real_audio(monkeypatch):
    monkeypatch.setattr(files, "iter_local_audio", lambda *a, **kw: (x for x in [np.zeros(425280, dtype=np.float32)]))
    install_engine(monkeypatch, lambda *a, **kw: Transcript((Segment(22, 27, "tail"),), "en"))
    result = files.transcribe_file("fixture.wav", Config())
    assert result.segments == (Segment(22, 26.58, "tail"),)


@pytest.mark.parametrize("start", [1.0, 1.02])
def test_model_words_starting_outside_audio_fail_without_silent_removal(monkeypatch, start):
    monkeypatch.setattr(files, "iter_local_audio", lambda *a, **kw: (x for x in [np.zeros(16000, dtype=np.float32)]))
    install_engine(monkeypatch, lambda *a, **kw: Transcript((Segment(start, 1.5, "do not discard"),)))
    with pytest.raises(ValueError, match="outside the audio batch"):
        files.transcribe_file("fixture.wav", Config())


def test_quiet_batch_offsets_and_clipped_ends_keep_words_and_order(monkeypatch):
    audio = np.full(35 * 16000, 0.2, dtype=np.float32)
    audio[27 * 16000:27 * 16000 + 3200] = 0
    monkeypatch.setattr(files, "iter_local_audio", lambda *a, **kw: (x for x in [audio]))
    lengths = []
    def recognize(block, cfg, **kwargs):
        lengths.append(len(block))
        if len(lengths) == 1:
            return Transcript((Segment(26, 30, "before"),), "en")
        return Transcript((Segment(0, 1, "after"),), "en")
    install_engine(monkeypatch, recognize)
    result = files.transcribe_file("fixture.wav", Config())
    assert lengths == [435200, 124800]
    assert result.segments == (Segment(26, 27.2, "before"), Segment(27.2, 28.2, "after"))
    assert result.text == "before after"


def test_cancel_between_pcm_blocks_closes_file(tmp_path):
    path = tmp_path / "cancel.wav"
    with wave.open(str(path), "wb") as out:
        out.setparams((1, 2, 16000, 0, "NONE", ""))
        out.writeframes(bytes(64000))
    cancel = threading.Event()
    with closing(files.iter_local_audio(path, cancel=cancel)) as stream:
        assert len(next(stream)) == 16000
        cancel.set()
        with pytest.raises(TranscriptionCancelled):
            next(stream)
    # Windows cannot rename an open wave input handle without delete sharing.
    path.rename(tmp_path / "closed.wav")


def test_selected_container_tracks_are_distinct_from_stereo_channels(tmp_path, monkeypatch):
    av = pytest.importorskip("av")
    monkeypatch.setattr("utterleaf.file_decoder.decoder_selection", lambda: None)
    path = tmp_path / "tracks.mkv"
    with av.open(str(path), "w") as out:
        tracks = [out.add_stream("flac", rate=16000) for _ in range(2)]
        # Configure every stream before the first mux writes the container header.
        for track in tracks:
            track.layout = "mono"
        for track, level in zip(tracks, [1200, -2400]):
            frame = av.AudioFrame.from_ndarray(np.full((1, 16000), level, dtype=np.int16), format="s16", layout="mono")
            frame.sample_rate = 16000
            frame.pts = 0
            for packet in track.encode(frame):
                out.mux(packet)
            for packet in track.encode(None):
                out.mux(packet)
    first = np.concatenate(list(files.iter_local_audio(path, audio_track=0)))
    second = np.concatenate(list(files.iter_local_audio(path, audio_track=1)))
    np.testing.assert_allclose(first, 1200 / 32768, atol=1e-6)
    np.testing.assert_allclose(second, -2400 / 32768, atol=1e-6)
    assert len(first) == len(second) == 16000
    with pytest.raises(ValueError, match="does not exist"):
        list(files.iter_local_audio(path, audio_track=2))


@pytest.mark.parametrize("track", [-1, 256, True, 1.5, "1"])
def test_invalid_track_is_rejected_before_decoding(tmp_path, track):
    with pytest.raises(ValueError, match="audio track"):
        list(files.iter_local_audio(tmp_path / "anything.wav", audio_track=track))
