from types import SimpleNamespace
import threading
import sys
import time

import numpy as np
import pytest

from utterleaf import app as module
from utterleaf.app import Utterleaf, _EndpointTake
from utterleaf.config import Config
from utterleaf.edit_target import Field


class Recorder:
    def __init__(self):
        self.recording = True
        self.end_sample = 4096
        self.stopped = 0
    def endpoint_snapshot(self):
        return np.ones(min(self.end_sample, 4096), dtype=np.float32), self.end_sample
    def stop(self):
        self.recording = False
        self.stopped += 1
        return np.ones(16000, dtype=np.float32)
    def close(self):
        pass
    def seconds(self, audio):
        return len(audio) / 16000


class Endpoint:
    def __init__(self, _detector, on_end, *, options, on_error):
        self.on_end, self.on_error, self.options = on_end, on_error, options
        self.active = True
        self.cancelled = 0
        self.submitted = []
    def start(self):
        return 7
    def submit(self, audio, generation, *, end_sample):
        self.submitted.append((audio.copy(), generation, end_sample))
    def cancel(self):
        self.active = False
        self.cancelled += 1


class Timer:
    def __init__(self, interval, function, args=(), kwargs=None):
        self.interval, self.function, self.args = interval, function, args
        self.cancelled = False
    def start(self):
        pass
    def cancel(self):
        self.cancelled = True


@pytest.fixture
def endpoint_app(monkeypatch):
    monkeypatch.setattr(module.threading, "Timer", Timer)
    monkeypatch.setattr("utterleaf.speech_endpoint.SpeechEndpoint", Endpoint)
    monkeypatch.setattr(module, "beep", lambda *_a, **_k: None)
    monkeypatch.setattr(module, "request_final", lambda: None)
    monkeypatch.setattr(module, "foreground_id", lambda: 123)
    cfg = Config(tray=False, indicator=False, beep=False, speech_end_enabled=True,
                 speech_end_pause_seconds=1.8)
    app = Utterleaf(cfg)
    app.recorder = Recorder()
    app.state = "recording"
    app._cut_id = 4
    app._endpoint_detector_loaded = True
    app._endpoint_detector = lambda _audio: np.ones(1)
    app.hotkey = SimpleNamespace(reset_active=lambda: None)
    return app


def test_endpoint_poll_uses_take_snapshot_and_automatic_stop_releases_immediately(endpoint_app, monkeypatch):
    app = endpoint_app
    cuts = []
    resets = []
    app.hotkey = SimpleNamespace(reset_active=lambda: resets.append(True))
    app._start_speech_endpoint(4, 123, "editor", None, Config(
        tray=False, speech_end_enabled=True, speech_end_pause_seconds=1.8,
        speech_end_insert=False))
    endpoint = app._endpoint
    assert endpoint.options.pause_seconds == 1.8
    app.cfg.speech_end_insert = True
    app._poll_speech_endpoint(endpoint, 7, 4)
    assert endpoint.submitted[0][1:] == (7, 4096)
    monkeypatch.setattr(app, "_cut", lambda *args: cuts.append(args))
    endpoint.on_end(4096)
    assert app.state == "busy"
    assert resets == [True]
    assert cuts and isinstance(cuts[0][0], _EndpointTake)
    assert cuts[0][0].action == "review"
    assert app._tail_timer is None


def test_stale_or_wrong_target_endpoint_result_never_stops(endpoint_app, monkeypatch):
    app = endpoint_app
    app._start_speech_endpoint(4, 123, "editor", None, app.cfg)
    endpoint = app._endpoint
    app.recorder.end_sample = 20_000
    endpoint.on_end(4096)
    assert app.state == "recording"
    assert endpoint.cancelled
    app._start_speech_endpoint(4, 123, "editor", None, app.cfg)
    endpoint = app._endpoint
    monkeypatch.setattr(module, "foreground_id", lambda: 999)
    endpoint.on_end(4096)
    assert endpoint.cancelled
    assert app.state == "recording"
    assert app._endpoint_unavailable


def test_manual_cancel_invalidates_late_endpoint_callback(endpoint_app):
    app = endpoint_app
    app._start_speech_endpoint(4, 123, "editor", None, app.cfg)
    endpoint = app._endpoint
    app.cancel_recording()
    assert endpoint.cancelled
    endpoint.on_end(4096)
    assert app.state == "idle"


def test_endpoint_review_keeps_editor_commands_literal_and_does_not_read_editor(monkeypatch):
    app = Utterleaf(Config(tray=False, indicator=False, beep=False))
    app.recorder = Recorder()
    take = _EndpointTake(123, "editor", "review", app.cfg)
    monkeypatch.setattr(module, "transcribe", lambda *_a: "scratch that")
    monkeypatch.setattr(module.edit_target, "read_field", lambda: pytest.fail("review must not inspect editor"))
    monkeypatch.setattr(module, "paste", lambda *_a, **_k: pytest.fail("review must not paste"))
    monkeypatch.setattr("utterleaf.review_ui.launch_review", lambda text, action, failure, **kwargs: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(app, "_flash", lambda *_a, **_k: None)
    app._finish(np.ones(16000, dtype=np.float32), take)
    assert app.recent_dictation.get() == "scratch that"
    assert app._review is not None
    assert app._review.text == "scratch that"


def test_review_insert_rechecks_original_target_and_keeps_recovery(monkeypatch):
    app = Utterleaf(Config(tray=False, indicator=False, beep=False))
    app.recorder = Recorder()
    take = _EndpointTake(123, "editor", "review", app.cfg)
    app._remember_result("keep these words")
    monkeypatch.setattr("utterleaf.review_ui.launch_review", lambda text, action, failure, **kwargs: SimpleNamespace(close=lambda: None))
    app._present_review("keep these words", take)
    monkeypatch.setattr(module, "foreground_id", lambda: 999)
    monkeypatch.setattr(module, "paste", lambda *_a, **_k: pytest.fail("wrong target must not paste"))
    monkeypatch.setattr(app, "_after_job", lambda *_a, **_k: None)
    app._review_action(app._review.generation, "insert")
    assert app.recent_dictation.get() == "keep these words"


def test_automatic_insert_is_literal_but_uses_guarded_paste(monkeypatch):
    app = Utterleaf(Config(tray=False, indicator=False, beep=False))
    app.recorder = Recorder()
    field = Field((123, 456, 7), "", 0, 0)
    take = _EndpointTake(123, "editor", "insert", app.cfg, field=field)
    pasted = []
    monkeypatch.setattr(module, "transcribe", lambda *_a: "scratch that")
    monkeypatch.setattr(module, "foreground_id", lambda: 123)
    monkeypatch.setattr(module.edit_target, "read_field", lambda: field)
    monkeypatch.setattr(module.edit_target, "capture", lambda *_a: None)
    monkeypatch.setattr(module, "paste", lambda text, **kwargs: pasted.append((text, kwargs)) or "pasted")
    monkeypatch.setattr(app, "_schedule_edit_expiry", lambda: None)
    monkeypatch.setattr(app, "_after_job", lambda *_a, **_k: None)
    app._finish(np.ones(16000, dtype=np.float32), take)
    assert len(pasted) == 1
    text, kwargs = pasted[0]
    assert text == "Scratch that"
    assert kwargs["restore_clipboard"] is True
    assert kwargs["target"] == 123
    assert callable(kwargs["cancel"])
    assert not kwargs["cancel"]()


def test_endpoint_uses_markdown_formatting_but_keeps_editor_commands_literal(monkeypatch):
    app = Utterleaf(Config(tray=False, indicator=False, beep=False))
    app.recorder = Recorder()
    shown = []
    monkeypatch.setattr(module, "transcribe", lambda *_a: "heading two Project notes")
    monkeypatch.setattr(app, "_present_review", lambda text, take: shown.append(text) or True)
    monkeypatch.setattr(app, "_after_job", lambda *_a, **_k: None)
    take = _EndpointTake(123, "editor", "review", Config(
        tray=False, output_format="markdown"))
    app._finish(np.ones(16000, dtype=np.float32), take)
    assert shown == ["## Project notes"]

    shown.clear()
    monkeypatch.setattr(module, "transcribe", lambda *_a: "scratch that")
    app._finish(np.ones(16000, dtype=np.float32), take)
    assert shown == ["scratch that"]


def test_endpoint_raw_mode_preserves_model_text(monkeypatch):
    app = Utterleaf(Config(tray=False, indicator=False, beep=False))
    app.recorder = Recorder()
    shown = []
    raw = "  keep THIS exactly  "
    monkeypatch.setattr(module, "transcribe", lambda *_a: raw)
    monkeypatch.setattr(app, "_present_review", lambda text, take: shown.append(text) or True)
    monkeypatch.setattr(app, "_after_job", lambda *_a, **_k: None)
    app._finish(np.ones(16000, dtype=np.float32), _EndpointTake(
        123, "terminal", "review", Config(tray=False, text_cleanup=False)))
    assert shown == [raw]


def test_endpoint_markdown_insert_keeps_heading_boundaries(monkeypatch):
    app = Utterleaf(Config(tray=False, indicator=False, beep=False))
    app.recorder = Recorder()
    field = Field((123, 456, 7), "Intro", 5, 5)
    pasted = []
    monkeypatch.setattr(module, "transcribe", lambda *_a: "heading two Project notes")
    monkeypatch.setattr(module, "foreground_id", lambda: 123)
    monkeypatch.setattr(module.edit_target, "read_field", lambda: field)
    monkeypatch.setattr(module.edit_target, "capture", lambda *_a: None)
    monkeypatch.setattr(module, "paste", lambda text, **kwargs: pasted.append(text) or "pasted")
    monkeypatch.setattr(app, "_schedule_edit_expiry", lambda: None)
    monkeypatch.setattr(app, "_after_job", lambda *_a, **_k: None)
    app._finish(np.ones(16000, dtype=np.float32), _EndpointTake(
        123, "editor", "insert", Config(tray=False, output_format="markdown"), field=field))
    assert pasted == ["\n\n## Project notes\n\n"]


def test_auto_insert_falls_back_to_review_without_verified_native_field(endpoint_app):
    app = endpoint_app
    cfg = Config(tray=False, speech_end_enabled=True, speech_end_insert=True)
    app._start_speech_endpoint(4, 123, "browser", None, cfg, None)
    endpoint = app._endpoint
    cuts = []
    app._cut = lambda *args: cuts.append(args)
    endpoint.on_end(4096)
    assert cuts[0][0].action == "review"


def test_endpoint_start_failure_leaves_manual_recording_available(endpoint_app, monkeypatch):
    class BrokenEndpoint(Endpoint):
        def start(self):
            raise RuntimeError("local runtime unavailable")

    app = endpoint_app
    statuses = []
    app._set_icon = lambda *args, **kwargs: statuses.append((args, kwargs))
    monkeypatch.setattr("utterleaf.speech_endpoint.SpeechEndpoint", BrokenEndpoint)
    app._start_speech_endpoint(4, 123, "editor", None, app.cfg)
    assert app.state == "recording"
    assert app._endpoint is None
    assert app._endpoint_unavailable
    assert "automatic stop unavailable" in statuses[-1][0][1]


def test_detector_loader_thread_failure_keeps_manual_recording_available(endpoint_app, monkeypatch):
    app = endpoint_app
    app._endpoint_detector_loaded = False
    app._endpoint_detector = None

    class BrokenThread:
        def __init__(self, **_kwargs):
            pass
        def start(self):
            raise RuntimeError("thread unavailable")

    monkeypatch.setattr(module.threading, "Thread", BrokenThread)
    app._start_speech_endpoint(4, 123, "editor", None, app.cfg)
    assert app.state == "recording"
    assert app._endpoint is None
    assert app._endpoint_unavailable
    assert not app._endpoint_detector_loading
    app.cancel_recording()
    assert app.state == "idle"
    assert app.recorder.stopped == 1


def test_async_detector_import_failure_completes_loader_state(monkeypatch):
    app = Utterleaf(Config(tray=False, indicator=False, beep=False,
                           speech_end_enabled=True))
    monkeypatch.setitem(sys.modules, "utterleaf.speech_endpoint", None)
    app._ensure_endpoint_detector()
    deadline = time.monotonic() + 1
    while app._endpoint_detector_loading and time.monotonic() < deadline:
        time.sleep(0.01)
    assert app._endpoint_detector_loaded
    assert not app._endpoint_detector_loading
    assert app._endpoint_detector is None


@pytest.mark.parametrize("wrong_window,wrong_field", [(True, False), (False, True)])
def test_auto_insert_guard_failure_opens_review(monkeypatch, wrong_window, wrong_field):
    app = Utterleaf(Config(tray=False, indicator=False, beep=False))
    app.state = "busy"
    field = Field((123, 456, 7), "before", 6, 6)
    take = _EndpointTake(123, "editor", "insert", app.cfg, field=field)
    shown = []
    monkeypatch.setattr(module, "foreground_id", lambda: 999 if wrong_window else 123)
    monkeypatch.setattr(module.edit_target, "read_field", lambda: (
        Field(field.identity, "before", 0, 0) if wrong_field else field))
    monkeypatch.setattr(module, "paste", lambda *_a, **_k: pytest.fail("guard failure must not paste"))
    monkeypatch.setattr(app, "_present_review", lambda text, review_take: shown.append((text, review_take)) or True)
    monkeypatch.setattr(app, "_after_job", lambda *_a, **_k: None)
    with app._capture_lock:
        app._deliver_endpoint_text("private words", take, fallback_review=True)
    assert shown[0][0] == "private words"
    assert shown[0][1].action == "review"


def test_cancel_during_auto_insert_guard_prevents_paste(monkeypatch):
    app = Utterleaf(Config(tray=False, indicator=False, beep=False))
    app.state = "busy"
    field = Field((123, 456, 7), "", 0, 0)
    take = _EndpointTake(123, "editor", "insert", app.cfg, field=field)

    def cancel_then_report_target():
        app.cancel_recording()
        return 123

    monkeypatch.setattr(module, "foreground_id", cancel_then_report_target)
    monkeypatch.setattr(module.edit_target, "read_field", lambda: field)
    monkeypatch.setattr(module, "paste", lambda *_a, **_k: pytest.fail("cancelled text must not paste"))
    monkeypatch.setattr(app, "_after_job", lambda *_a, **_k: None)
    with app._capture_lock:
        app._deliver_endpoint_text("private words", take, fallback_review=True)
    assert app._cancel_job


def test_new_recovery_closes_obsolete_review_and_invalidates_its_action(monkeypatch):
    app = Utterleaf(Config(tray=False, indicator=False, beep=False))
    callbacks, closed, copied = [], [], []
    monkeypatch.setattr("utterleaf.review_ui.launch_review", lambda text, action, failure, **kwargs: (
        callbacks.append(action) or SimpleNamespace(close=lambda: closed.append(text))))
    monkeypatch.setattr(module, "copy_text", lambda text: copied.append(text) or True)
    app._remember_result("take A")
    app._present_review("take A", _EndpointTake(123, "editor", "review", app.cfg))
    app._remember_result("take B")
    callbacks[0]("copy")
    assert closed == ["take A"]
    assert copied == []
    assert app.recent_dictation.get() == "take B"


def test_old_expiry_cannot_clear_newer_recovery_context():
    app = Utterleaf(Config(tray=False, indicator=False, beep=False))
    first = app.recent_dictation.put("take A")
    app._recent_generation = first
    app._review_lock.acquire()
    worker = threading.Thread(target=app._expire_recovery_context, args=(first,))
    worker.start()
    app._remember_result("take B")
    app.last_text = "take B"
    app._review_lock.release()
    worker.join(timeout=1)
    assert not worker.is_alive()
    assert app.recent_dictation.get() == "take B"
    assert app.last_text == "take B"
