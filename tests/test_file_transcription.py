import threading
import wave
import importlib.util
from pathlib import Path
import sys

import numpy as np
import pytest

from utterleaf.config import Config
from utterleaf.file_transcription import decode_local_file, transcribe_file
from utterleaf.transcribe import CTranslateEngine, OpenVinoEngine
from utterleaf.transcript import Transcript, TranscriptionCancelled


def wav_file(tmp_path, seconds=1):
    path = tmp_path / "speech.wav"
    with wave.open(str(path), "wb") as out:
        out.setparams((2, 2, 8000, 0, "NONE", ""))
        out.writeframes(np.zeros(int(seconds * 8000 * 2), dtype=np.int16).tobytes())
    return path


def test_real_decoder_resamples_stereo_without_disk_spooling(tmp_path):
    pytest.importorskip("av")
    path = wav_file(tmp_path)
    audio = decode_local_file(path)
    assert audio.shape == (16000,)
    assert audio.dtype == np.float32
    assert list(tmp_path.iterdir()) == [path]


def test_decode_limit_and_cancellation(tmp_path, monkeypatch):
    pytest.importorskip("av")
    from utterleaf import file_transcription as f
    path = wav_file(tmp_path)
    monkeypatch.setattr(f, "MAX_AUDIO_SECONDS", 0.25)
    with pytest.raises(ValueError, match="limit"):
        decode_local_file(path)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(TranscriptionCancelled):
        decode_local_file(path, cancel=cancel)


def test_malformed_empty_missing_and_oversized(tmp_path, monkeypatch):
    pytest.importorskip("av")
    path = tmp_path / "broken.wav"
    with pytest.raises(ValueError, match="existing"):
        decode_local_file(path)
    path.write_bytes(b"")
    with pytest.raises(ValueError, match="nonempty"):
        decode_local_file(path)
    path.write_bytes(b"not media")
    with pytest.raises(RuntimeError, match="decode"):
        decode_local_file(path)
    monkeypatch.setattr("utterleaf.file_transcription.MAX_FILE_BYTES", 1)
    with pytest.raises(ValueError, match="256 MiB"):
        decode_local_file(path)


def test_no_model_downloads_and_explicit_engine_capability(monkeypatch):
    monkeypatch.setattr("utterleaf.file_transcription.iter_local_audio", lambda *a, **k: (x for x in [np.zeros(16000, dtype=np.float32)]))
    seen = []

    def load(cfg):
        seen.append(cfg.allow_network)
        return OpenVinoEngine(None)

    monkeypatch.setattr("utterleaf.transcribe.load_model", load)
    cfg = Config(allow_network=True)
    with pytest.raises(RuntimeError, match="requires the CPU"):
        transcribe_file("explicit.wav", cfg)
    assert seen == [False]
    assert cfg.allow_network is True


def test_missing_model_error_is_preserved(monkeypatch):
    monkeypatch.setattr("utterleaf.file_transcription.iter_local_audio", lambda *a, **k: (x for x in [np.zeros(16000, dtype=np.float32)]))
    def load(cfg):
        assert cfg.allow_network is False
        raise FileNotFoundError("Install the selected model first")
    monkeypatch.setattr("utterleaf.transcribe.load_model", load)
    with pytest.raises(FileNotFoundError, match="Install"):
        transcribe_file("explicit.wav", Config())


def test_file_silence_progress_no_automatic_export(monkeypatch):
    monkeypatch.setattr("utterleaf.file_transcription.iter_local_audio", lambda *a, **k: (x for x in [np.zeros(16000, dtype=np.float32)]))
    class Model:
        def transcribe(self, *args, **kwargs):
            return iter([]), None
    monkeypatch.setattr("utterleaf.transcribe.load_model", lambda cfg: CTranslateEngine(Model()))
    progress = []
    assert transcribe_file("explicit.wav", Config(), progress=lambda *args: progress.append(args)) == Transcript((), "en")
    assert progress == [("loading", None), ("complete", 1.0)]


def test_gpu_runtime_fallback_stays_offline(monkeypatch):
    from utterleaf.transcribe import CPU
    monkeypatch.setattr("utterleaf.file_transcription.iter_local_audio", lambda *a, **k: (x for x in [np.zeros(16000, dtype=np.float32)]))
    class Model:
        def __init__(self, fail):
            self.fail = fail
        def transcribe(self, *args, **kwargs):
            if self.fail:
                raise RuntimeError("CUDA unavailable")
            return iter([]), None
    calls = []
    def load(cfg, accel=None):
        calls.append((cfg.allow_network, accel))
        return CTranslateEngine(Model(accel is None))
    monkeypatch.setattr("utterleaf.transcribe.load_model", load)
    monkeypatch.setattr("utterleaf.transcribe.mark_cuda_unusable", lambda: None)
    monkeypatch.setattr("utterleaf.transcribe.reset_engine", lambda: None)
    assert transcribe_file("explicit.wav", Config()).text == ""
    assert calls == [(False, None), (False, CPU)]


def test_cancel_during_decode_discards_audio(tmp_path):
    pytest.importorskip("av")
    cancel = threading.Event()
    path = wav_file(tmp_path)
    with pytest.raises(TranscriptionCancelled):
        decode_local_file(path, cancel=cancel, progress=lambda *args: cancel.set())
    assert list(tmp_path.iterdir()) == [path]


def test_decoder_blocks_external_io(tmp_path, monkeypatch):
    av = pytest.importorskip("av")
    path = wav_file(tmp_path)
    def attempt_external(source, **kwargs):
        assert kwargs["options"]["protocol_whitelist"] == ""
        kwargs["io_open"]("https://example.invalid/audio", 0, {})
    monkeypatch.setattr(av, "open", attempt_external)
    with pytest.raises(ValueError, match="external"):
        decode_local_file(path)


@pytest.fixture
def packaged_decoder(monkeypatch, tmp_path):
    monkeypatch.setattr("utterleaf.file_decoder._settings_path", lambda: tmp_path / "decoder.json")
    stub_path = Path(__file__).resolve().parents[1] / "packaging" / "stubs" / "av" / "__init__.py"
    spec = importlib.util.spec_from_file_location("av", stub_path)
    stub = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(stub)
    monkeypatch.setitem(sys.modules, "av", stub)


def test_packaged_wav_works_without_pyav(tmp_path, packaged_decoder):
    audio = decode_local_file(wav_file(tmp_path))
    assert audio.shape == (16000,)
    assert audio.dtype == np.float32


@pytest.mark.parametrize("width", [1, 2, 3, 4])
def test_packaged_pcm_widths_and_unicode_path(tmp_path, packaged_decoder, width):
    path = tmp_path / "日本語.wav"
    with wave.open(str(path), "wb") as out:
        out.setparams((1, width, 16000, 0, "NONE", ""))
        out.writeframes(bytes([128 if width == 1 else 0]) * 16000 * width)
    audio = decode_local_file(path)
    assert audio.shape == (16000,)
    assert np.max(np.abs(audio)) == 0


def test_packaged_rejects_other_media_and_truncation(tmp_path, packaged_decoder):
    path = tmp_path / "other.mp3"
    path.write_bytes(b"not wave")
    with pytest.raises(RuntimeError, match="More formats"):
        decode_local_file(path)
    path = wav_file(tmp_path)
    path.write_bytes(path.read_bytes()[:-100])
    with pytest.raises(ValueError, match="truncated"):
        decode_local_file(path)


def test_packaged_limits_and_cancels(tmp_path, packaged_decoder, monkeypatch):
    path = wav_file(tmp_path)
    cancel = threading.Event()
    with pytest.raises(TranscriptionCancelled):
        decode_local_file(path, cancel=cancel, progress=lambda *args: cancel.set())
    monkeypatch.setattr("utterleaf.file_transcription.MAX_AUDIO_SECONDS", 0.25)
    with pytest.raises(ValueError, match="10-minute"):
        decode_local_file(path)


def test_native_wav_does_not_need_selected_decoder(tmp_path, packaged_decoder, monkeypatch):
    monkeypatch.setattr("utterleaf.file_decoder.decoder_selection", lambda: {"path": "missing-ffmpeg", "sha256": "changed"})
    monkeypatch.setattr("utterleaf.file_decoder.decode_with_ffmpeg", lambda *a, **k: pytest.fail("PCM WAV needs no external program"))
    assert decode_local_file(wav_file(tmp_path)).shape == (16000,)


def test_unsupported_wav_uses_explicit_optional_decoder(tmp_path, packaged_decoder, monkeypatch):
    path = tmp_path / "compressed.wav"
    path.write_bytes(b"RIFF unsupported fixture")
    calls = []
    monkeypatch.setattr("utterleaf.file_decoder.decode_with_ffmpeg", lambda selected, **kw: calls.append(selected) or np.zeros(16000))
    assert decode_local_file(path).shape == (16000,)
    assert calls == [path]


def test_explicit_decoder_used_in_source_install_too(tmp_path, monkeypatch):
    path = tmp_path / "clip.mp3"
    path.write_bytes(b"sample")
    monkeypatch.setattr("utterleaf.file_decoder.decoder_selection", lambda: {"path": "selected-ffmpeg", "sha256": "identity"})
    monkeypatch.setattr("utterleaf.file_decoder.decode_with_ffmpeg", lambda selected, **kw: np.zeros(8000))
    assert decode_local_file(path).shape == (8000,)
