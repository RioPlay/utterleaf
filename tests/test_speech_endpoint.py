"""Speech endpoint sample-clock, bounded worker and local-asset contracts."""
import io
import hashlib
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import wave

import numpy as np
import pytest

from utterleaf import speech_endpoint as module
from utterleaf.speech_endpoint import EndpointOptions, SpeechEndpoint, FRAME_SAMPLES, WINDOW_SAMPLES


def pcm(probabilities):
    return np.repeat(np.asarray(probabilities, dtype=np.float32), FRAME_SAMPLES)


def detector(audio):
    return audio.reshape(-1, FRAME_SAMPLES)[:, 0]


class InlineThread:
    def __init__(self, *, target, **_kwargs):
        self.target = target
    def start(self):
        self.target()


@pytest.fixture
def inline(monkeypatch):
    monkeypatch.setattr(module.threading, "Thread", InlineThread)


def submit(endpoint, generation, probabilities, *, end=None):
    audio = pcm(probabilities)
    endpoint.submit(audio, generation, end_sample=len(audio) if end is None else end)


def test_only_sustained_speech_then_captured_pause_ends_once(inline):
    ended = []
    endpoint = SpeechEndpoint(detector, ended.append, options=EndpointOptions(.5))
    generation = endpoint.start()
    submit(endpoint, generation, [0] * 40)
    submit(endpoint, generation, [0] * 40 + [1, 0, 1, 0] + [0] * 20)
    assert ended == []  # Separate blips do not add up to onset.
    prefix = [0] * 64 + [1] * 4
    submit(endpoint, generation, prefix + [0] * 15)
    assert ended == []
    submit(endpoint, generation, prefix + [0] * 16)
    assert ended == [84 * FRAME_SAMPLES]
    submit(endpoint, generation, prefix + [0] * 40)
    assert len(ended) == 1


def test_resumed_speech_in_snapshot_cancels_earlier_pause(inline):
    ended = []
    endpoint = SpeechEndpoint(detector, ended.append, options=EndpointOptions(.5))
    generation = endpoint.start()
    submit(endpoint, generation, [1] * 4 + [0] * 20 + [1] * 5)
    assert ended == []
    submit(endpoint, generation, [1] * 4 + [0] * 20 + [1] * 5 + [.4] * 20)
    assert ended == []  # Hysteresis keeps uncertain continuing speech alive.
    submit(endpoint, generation, [1] * 4 + [0] * 20 + [1] * 5 + [.4] * 20 + [0] * 16)
    assert len(ended) == 1


def test_duplicate_snapshot_cannot_make_silence_or_recount_onset(inline):
    calls, ended = [], []
    endpoint = SpeechEndpoint(lambda a: calls.append(len(a)) or detector(a), ended.append)
    generation = endpoint.start()
    for _ in range(30):
        submit(endpoint, generation, [1] * 2)
    assert calls == [1024]
    assert ended == []
    submit(endpoint, generation, [1] * 2 + [0] * 50)
    assert ended == []


def test_gap_resets_speech_and_partial_frames_never_count(inline):
    ended = []
    endpoint = SpeechEndpoint(detector, ended.append, options=EndpointOptions(.5))
    generation = endpoint.start()
    submit(endpoint, generation, [1] * 4)
    submit(endpoint, generation, [0] * 20, end=100 * FRAME_SAMPLES)
    assert ended == []  # Missing samples cannot be presumed silent.
    endpoint.cancel()
    generation = endpoint.start()
    endpoint.submit(pcm([1] * 4 + [0] * 15).tolist() + [0] * 511,
                    generation, end_sample=20 * FRAME_SAMPLES - 1)
    assert ended == []


def test_cancel_and_restart_ignore_old_generation(inline):
    ended = []
    endpoint = SpeechEndpoint(detector, ended.append, options=EndpointOptions(.5))
    old = endpoint.start()
    submit(endpoint, old, [1] * 4)
    endpoint.cancel()
    submit(endpoint, old, [1] * 4 + [0] * 16)
    new = endpoint.start()
    submit(endpoint, old, [1] * 4 + [0] * 40)
    submit(endpoint, new, [0] * 40)
    assert ended == []
    assert endpoint.active


@pytest.mark.parametrize("result", [[], [float("nan")], [2], [-1]])
def test_bad_probabilities_disable_only_current_take(inline, result):
    errors, ended = [], []
    endpoint = SpeechEndpoint(lambda a: result, ended.append, on_error=lambda: errors.append(True))
    generation = endpoint.start()
    submit(endpoint, generation, [1] * 4)
    assert errors == [True]
    assert ended == []
    assert not endpoint.active
    assert not endpoint._running


def test_slow_worker_coalesces_and_cancelled_result_cannot_end_new_take():
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    calls, ended = [], []
    def slow(audio):
        calls.append(audio.copy())
        if len(calls) == 1:
            entered.set()
            assert release.wait(3)
        else:
            finished.set()
        return detector(audio)
    endpoint = SpeechEndpoint(slow, ended.append, options=EndpointOptions(.5))
    old = endpoint.start()
    submit(endpoint, old, [1] * 4 + [0] * 20)
    assert entered.wait(3)
    endpoint.cancel()
    new = endpoint.start()
    for index in range(1, 20):
        audio = np.zeros(WINDOW_SAMPLES * 2 + index * FRAME_SAMPLES, dtype=np.float32)
        endpoint.submit(audio, new, end_sample=len(audio))
        assert endpoint._latest[1].nbytes <= WINDOW_SAMPLES * 4
    release.set()
    assert finished.wait(3)
    endpoint.cancel()
    assert ended == []
    assert len(calls) == 2
    assert calls[-1].nbytes <= WINDOW_SAMPLES * 4


def test_pending_resumed_speech_wins_over_old_endpoint_result():
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    calls, ended = [], []
    def slow(audio):
        calls.append(True)
        if len(calls) == 1:
            entered.set()
            assert release.wait(3)
        else:
            finished.set()
        return detector(audio)
    endpoint = SpeechEndpoint(slow, ended.append, options=EndpointOptions(.5))
    generation = endpoint.start()
    submit(endpoint, generation, [1] * 4 + [0] * 20)
    assert entered.wait(3)
    submit(endpoint, generation, [1] * 4 + [0] * 20 + [1] * 10)
    release.set()
    assert finished.wait(3)
    endpoint.cancel()
    assert ended == []


@pytest.mark.parametrize("pause", [float("nan"), float("inf"), 0, .4, 3.1])
def test_invalid_pause_rejected(pause):
    with pytest.raises(ValueError):
        EndpointOptions(pause)


def test_wrong_or_oversized_asset_never_constructs_runtime(monkeypatch):
    requested = []
    class Source(io.BytesIO):
        def read(self, size):
            requested.append(size)
            return super().read(size)
    class Asset:
        def open(self, mode):
            assert mode == "rb"
            return Source(b"wrong")
    class Root:
        def joinpath(self, *parts):
            assert parts == ("assets", "silero_vad_v6.onnx")
            return Asset()
    monkeypatch.setattr(module, "files", lambda name: Root())
    monkeypatch.setattr(module.metadata, "version", lambda name: module.REVIEWED_PACKAGES[name])
    monkeypatch.setitem(sys.modules, "faster_whisper.vad", SimpleNamespace(
        SileroVADModel=lambda path: pytest.fail("Unverified model reached the runtime")))
    assert module.local_silero_detector() is None
    assert requested == [module.SILERO_BYTES + 1]


def test_unreviewed_wrapper_or_runtime_never_loads_asset(monkeypatch):
    monkeypatch.setattr(module.metadata, "version", lambda name: "unreviewed")
    monkeypatch.setattr(module, "files", lambda name: pytest.fail("Unreviewed dependency reached the loader"))
    assert module.local_silero_detector() is None


def test_worker_start_failure_releases_audio_and_reports_unavailable(monkeypatch):
    class FailedThread:
        def __init__(self, **kwargs):
            pass
        def start(self):
            raise RuntimeError("No more worker threads")
    monkeypatch.setattr(module.threading, "Thread", FailedThread)
    errors = []
    endpoint = SpeechEndpoint(detector, lambda end: pytest.fail("Unexpected endpoint"),
                              on_error=lambda: errors.append(True))
    generation = endpoint.start()
    submit(endpoint, generation, [1] * 4)
    assert not endpoint.active
    assert not endpoint._running
    assert endpoint._latest is None
    assert errors == [True]


def test_installed_reviewed_model_accepts_context_and_rejects_synthetic_silence():
    local = module.local_silero_detector()
    if local is None:
        pytest.skip("Reviewed local Silero asset/runtime unavailable; no download")
    audio = np.zeros(WINDOW_SAMPLES, dtype=np.float32)
    probabilities = np.asarray(local(audio)).reshape(-1)
    assert len(probabilities) == len(audio) // FRAME_SAMPLES
    assert np.isfinite(probabilities).all()
    assert probabilities.max() < .5


def test_factory_passes_verified_bytes_not_a_reopened_path(monkeypatch):
    try:
        raw = module.files("faster_whisper").joinpath("assets", "silero_vad_v6.onnx").read_bytes()
    except (ImportError, FileNotFoundError):
        pytest.skip("Reviewed local asset unavailable; no download")
    if hashlib.sha256(raw).hexdigest() != module.SILERO_SHA256:
        pytest.skip("Installed asset is not the reviewed fixture")
    monkeypatch.setattr(module.metadata, "version", lambda name: module.REVIEWED_PACKAGES[name])
    loaded = []
    sentinel = object()
    monkeypatch.setitem(sys.modules, "faster_whisper.vad", SimpleNamespace(
        SileroVADModel=lambda value: loaded.append(value) or sentinel))
    assert module.local_silero_detector() is sentinel
    assert loaded == [raw]
    assert isinstance(loaded[0], bytes)


def test_public_speech_fixture_ends_after_captured_pause(inline):
    # Reuse the existing reviewed local fixture; do not fetch speech or add a
    # recording to the source/binary just to run this optional integration check.
    path = Path(__file__).resolve().parents[1] / "artifacts" / "file-jfk-fixture.wav"
    if not path.is_file():
        pytest.skip("Local public JFK fixture unavailable; no automatic download")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == "59dfb9a4acb36fe2a2affc14bacbee2920ff435cb13cc314a08c13f66ba7860e"
    local = module.local_silero_detector()
    if local is None:
        pytest.skip("Reviewed local Silero asset/runtime unavailable; no download")
    with wave.open(str(path), "rb") as source:
        assert (source.getnchannels(), source.getsampwidth(), source.getframerate()) == (1, 2, 16000)
        speech = np.frombuffer(source.readframes(64000), dtype="<i2").astype(np.float32) / 32768
    audio = np.concatenate((np.zeros(16000, dtype=np.float32), speech, np.zeros(32000, dtype=np.float32)))
    ended = []
    endpoint = SpeechEndpoint(local, ended.append)
    generation = endpoint.start()
    for end in range(4000, len(audio) + 1, 4000):
        endpoint.submit(audio[:end], generation, end_sample=end)
    assert len(ended) == 1
    assert 5 * 16000 <= ended[0] <= 7 * 16000
