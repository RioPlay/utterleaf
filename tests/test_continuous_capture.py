from types import SimpleNamespace

import numpy as np
import pytest

from utterleaf.audio import Recorder
from utterleaf.capture_store import CaptureStore, MAX_PENDING_BYTES
from utterleaf.app import _InterruptedTake
from test_app import _app


def append_seconds(store, seconds):
    for index in range(seconds):
        assert store.append(np.full(16000, index / 1000, np.float32))
        if index % 40 == 0:
            with store._condition:
                assert store._condition.wait_for(lambda: store.pending_bytes < MAX_PENDING_BYTES // 2, timeout=2)


def test_default_and_legacy_config_never_schedule_recording_cutoff(monkeypatch):
    app = _app(monkeypatch, max_seconds=120)
    starts = []
    monkeypatch.setattr(app.recorder, "start", lambda **kw: starts.append(kw))
    monkeypatch.setattr("utterleaf.app.foreground_id", lambda: 10)
    monkeypatch.setattr("utterleaf.app.foreground_app", lambda: "synthetic")
    app.start_recording()
    try:
        assert starts == [{"max_seconds": None}]
        assert app.state == "recording"
        assert app._limit_timer is None
        assert app._countdown_timer is None
        assert "left" not in app._recording_caption()
        assert "finish" in app._recording_caption()
    finally:
        app.cancel_recording()


@pytest.mark.parametrize("rate", [16000, 44100, 48000])
def test_actual_recorder_retains_only_preview_tail_and_transfers_store(monkeypatch, rate):
    recorder = Recorder(continuous=True)
    recorder.input_rate = rate
    monkeypatch.setattr(recorder, "prepare", lambda: None)
    recorder.start()
    captured = None
    try:
        for second in range(251):
            recorder._on_audio(np.full((rate, 1), second / 1000, np.float32), rate, None, None)
            if second % 10 == 0:
                store = recorder._store
                with store._condition:
                    assert store._condition.wait_for(lambda: store.pending_bytes < MAX_PENDING_BYTES // 2, timeout=2)
            assert sum(len(chunk) for chunk in recorder._chunks) <= 8 * rate
        tail, count = recorder.endpoint_snapshot()
        assert len(tail) == 8 * 16000
        assert count == 251 * 16000
        assert len(recorder.snapshot(max_seconds=4)) == 4 * 16000
        assert not recorder.limit_reached.is_set()
        captured = recorder.stop()
        recorder.close()
        captured.wait_ready()
        assert captured.error is None
        assert len(captured) == 251 * 16000
        assert sum(len(chunk) for chunk in captured.chunks()) == 251 * 16000
    finally:
        recorder.close()
        if captured is not None:
            captured.close()


def test_long_recognition_batches_and_recovery_preserve_all_text(monkeypatch):
    app = _app(monkeypatch)
    store = CaptureStore(16000)
    append_seconds(store, 601)
    store.finish()
    windows, results, statuses = [], [], []
    def recognize(audio, cfg):
        windows.append(len(audio))
        return f"piece{len(windows)}"
    monkeypatch.setattr("utterleaf.app.transcribe", recognize)
    monkeypatch.setattr("utterleaf.app.paste", lambda *a, **k: pytest.fail("Recovery must not paste"))
    monkeypatch.setattr(app, "_remember_result", results.append)
    monkeypatch.setattr(app, "_after_job", lambda *args: statuses.append(args))
    app._finish(store, _InterruptedTake("Synthetic interrupted capture."))
    assert sum(windows) == 601 * 16000
    assert max(windows) == 30 * 16000
    assert results == [" ".join(f"piece{i}" for i in range(1, 22))]
    assert statuses[-1][0] == "capture_error"
    assert store._file.closed


def test_cancel_between_batches_closes_store_and_never_delivers(monkeypatch):
    app = _app(monkeypatch)
    app.state = "busy"
    app._job_running = True
    store = CaptureStore(16000)
    append_seconds(store, 61)
    store.finish()
    calls = []
    def recognize(audio, cfg):
        calls.append(len(audio))
        app.cancel_recording()
        return "Must not deliver"
    monkeypatch.setattr("utterleaf.app.transcribe", recognize)
    monkeypatch.setattr("utterleaf.app.foreground_app", lambda: "fixture")
    monkeypatch.setattr("utterleaf.app.paste", lambda *a, **k: pytest.fail("Cancelled paste"))
    monkeypatch.setattr(app, "_remember_result", lambda *a: pytest.fail("Cancelled recovery"))
    monkeypatch.setattr(app, "_after_job", lambda *a: None)
    app._finish(store, 10)
    assert calls == [30 * 16000]
    assert store._file.closed


def test_late_storage_failure_is_recovery_only(monkeypatch):
    app = _app(monkeypatch)
    store = CaptureStore(16000)
    append_seconds(store, 1)
    store.finish().wait_ready()
    store._error = "Temporary audio storage failed. Only the stored portion can be recovered."
    recovered, statuses = [], []
    monkeypatch.setattr("utterleaf.app.transcribe", lambda *a: "stored prefix")
    monkeypatch.setattr("utterleaf.app.foreground_app", lambda: pytest.fail("Failed storage reads host"))
    monkeypatch.setattr("utterleaf.app.paste", lambda *a, **k: pytest.fail("Incomplete automatic paste"))
    monkeypatch.setattr(app, "_remember_result", recovered.append)
    monkeypatch.setattr(app, "_after_job", lambda *a: statuses.append(a))
    app._finish(store, 10)
    assert recovered == ["stored prefix"]
    assert statuses[-1][0] == "capture_error"
    assert "Temporary audio storage failed" in statuses[-1][1]
    assert "Reconnect your microphone" not in statuses[-1][1]
    assert store._file.closed


def test_cancel_as_batch_arrives_does_not_start_model_and_closes_store(monkeypatch):
    app = _app(monkeypatch)
    app.state = "busy"
    app._job_running = True
    store = CaptureStore(16000)
    append_seconds(store, 1)
    store.finish()

    def cancelled_batch(blocks, *, cancel):
        for block in blocks:
            app.cancel_recording()
            yield block

    monkeypatch.setattr("utterleaf.app.audio_windows", cancelled_batch)
    monkeypatch.setattr("utterleaf.app.transcribe", lambda *a: pytest.fail("Cancelled model call"))
    monkeypatch.setattr("utterleaf.app.foreground_app", lambda: "fixture")
    monkeypatch.setattr("utterleaf.app.paste", lambda *a, **k: pytest.fail("Cancelled paste"))
    monkeypatch.setattr(app, "_remember_result", lambda *a: pytest.fail("Cancelled recovery"))
    monkeypatch.setattr(app, "_after_job", lambda *a: None)
    app._finish(store, 10)
    assert store._file.closed


def test_cancel_disposes_all_queued_stores(monkeypatch):
    app = _app(monkeypatch)
    first, second = CaptureStore(16000), CaptureStore(16000)
    app._queued_audio = first
    app._queued_takes.append((second, 10, None))
    app.cancel_recording()
    for store in (first, second):
        assert store._ready.wait(2)
        assert store._file.closed
    assert app._queued_audio is None
    assert not app._queued_takes


def test_continuous_close_releases_untransferred_store(monkeypatch):
    recorder = Recorder(continuous=True)
    monkeypatch.setattr(recorder, "prepare", lambda: None)
    recorder.start()
    store = recorder._store
    recorder.close()
    assert store._ready.wait(2)
    assert store._file.closed
    assert recorder._store is None


def test_stopped_capture_prefers_quiet_boundary_and_preserves_every_sample(monkeypatch):
    app = _app(monkeypatch)
    store = CaptureStore(16000)
    source = np.full(35 * 16000, 0.2, dtype=np.float32)
    source[27 * 16000:27 * 16000 + 3200] = 0
    for offset in range(0, len(source), 16000):
        assert store.append(source[offset:offset + 16000])
    store.finish()
    windows, recovered = [], []
    def recognize(block, cfg):
        windows.append(block.copy())
        return "before" if len(windows) == 1 else "after"
    monkeypatch.setattr("utterleaf.app.transcribe", recognize)
    monkeypatch.setattr("utterleaf.app.foreground_app", lambda: pytest.fail("Recovery must not inspect host"))
    monkeypatch.setattr(app, "_remember_result", recovered.append)
    monkeypatch.setattr(app, "_after_job", lambda *args: None)
    app._finish(store, _InterruptedTake("Synthetic capture."))
    assert [len(x) for x in windows] == [435200, 124800]
    np.testing.assert_array_equal(np.concatenate(windows), source)
    assert recovered == ["before after"]
    assert store._file.closed
