import numpy as np

from utterleaf.config import Config
from utterleaf.transcribe import (
    CTranslateEngine,
    PREVIEW_SECONDS,
    _cuda_runtime_error,
    clear_final,
    request_final,
    transcribe,
    transcribe_preview,
)


def test_cuda_runtime_error_detects_cublas() -> None:
    assert _cuda_runtime_error(RuntimeError("Library cublas64_12.dll is not found or cannot be loaded"))
    assert not _cuda_runtime_error(RuntimeError("bad audio"))


def test_transcribe_retries_on_cublas(monkeypatch) -> None:
    class Boom:
        def transcribe(self, audio, cfg):
            raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")

    class Ok:
        def transcribe(self, audio, cfg):
            return "hello"

    calls = {"n": 0}

    def fake_load(cfg, accel=None):
        calls["n"] += 1
        return Boom() if calls["n"] == 1 else Ok()

    monkeypatch.setattr("utterleaf.transcribe.load_model", fake_load)
    monkeypatch.setattr("utterleaf.transcribe._reset_engine", lambda: None)
    monkeypatch.setattr("utterleaf.transcribe.mark_cuda_unusable", lambda: None)

    text = transcribe(np.ones(1600, dtype=np.float32), Config())
    assert text == "hello"
    assert calls["n"] == 2


def test_preview_skips_when_final_requested() -> None:
    request_final()
    try:
        assert transcribe_preview(np.ones(16000, dtype=np.float32), Config()) == ""
    finally:
        clear_final()


def test_preview_skips_when_lock_held(monkeypatch) -> None:
    from utterleaf import transcribe as t

    class Model:
        def transcribe(self, audio, **kwargs):
            raise AssertionError("preview must not infer while the lock is held")

    monkeypatch.setattr(t, "peek_engine", lambda: CTranslateEngine(Model()))
    assert t._infer_lock.acquire(blocking=False)
    try:
        assert transcribe_preview(np.ones(16000, dtype=np.float32), Config()) == ""
    finally:
        t._infer_lock.release()


def test_preview_uses_last_window(monkeypatch) -> None:
    captured: dict[str, int] = {}

    class Model:
        def transcribe(self, audio, **kwargs):
            captured["n"] = len(audio)
            return ([], None)

    monkeypatch.setattr(
        "utterleaf.transcribe.peek_engine", lambda: CTranslateEngine(Model())
    )
    audio = np.ones(int(16000 * 10), dtype=np.float32)
    assert transcribe_preview(audio, Config()) == ""
    assert captured["n"] == int(PREVIEW_SECONDS * 16000)


def test_load_model_reuses_cache_without_pick(monkeypatch) -> None:
    from utterleaf import transcribe as t

    fake = object()
    t._engine = fake
    t._engine_key = ("small.en", "gpu", "ctranslate2")

    def boom(_cfg):
        raise AssertionError("pick should not run when the engine is cached")

    monkeypatch.setattr(t, "pick", boom)
    try:
        assert t.load_model(Config(model="small", language="en")) is fake
    finally:
        t._engine = None
        t._engine_key = None
