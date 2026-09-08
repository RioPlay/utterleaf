"""Hold-to-talk state machine: short taps, queue, cancel, honest failures."""

from __future__ import annotations

from types import SimpleNamespace
import threading
import time

import numpy as np

from utterleaf.app import ENGINE_FAILED, Utterleaf
from utterleaf.config import Config


def test_xorg_tray_titles_handle_non_latin1_status_updates(monkeypatch):
    from utterleaf import app
    monkeypatch.setattr(app, "Icon", SimpleNamespace(__module__="pystray._xorg"))
    for status in ("loading model", app.ENGINE_FAILED, "Downloading…", "日本語"):
        assert app.tray_title(status).encode("latin-1")
    assert app.tray_title("loading model") == "Utterleaf - loading model"


def test_native_tray_titles_preserve_unicode(monkeypatch):
    from utterleaf import app
    monkeypatch.setattr(app, "Icon", SimpleNamespace(__module__="pystray._win32"))
    assert app.tray_title("日本語") == "Utterleaf — 日本語"


def test_tray_backend_reports_imported_icon_module(monkeypatch):
    from utterleaf import app
    monkeypatch.setattr(app, "Icon", SimpleNamespace(__module__="pystray._appindicator"))
    assert app.tray_backend() == "pystray._appindicator"


class FakeRecorder:
    def __init__(self, seconds: float = 1.0) -> None:
        self._seconds = seconds
        self.recording = False
        self.preferred_device = ""

    def audio(self) -> np.ndarray:
        n = max(1, int(self._seconds * 16000))
        return np.ones(n, dtype=np.float32)

    def set_device(self, name: str) -> None:
        self.preferred_device = name

    def prepare(self) -> None:
        return None

    def start(self) -> None:
        self.recording = True

    def stop(self) -> np.ndarray:
        self.recording = False
        return self.audio()

    def snapshot(self, max_seconds=None) -> np.ndarray:
        return self.audio()

    def close(self) -> None:
        return None

    def seconds(self, audio: np.ndarray) -> float:
        return float(len(audio)) / 16000.0


class FakePill:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.closed = 0
        self.started = 0
        self.badges: list[str] = []

    def close(self) -> None:
        self.closed += 1
        self.enabled = False

    def start(self) -> None:
        self.started += 1
        if not self.enabled:
            return

    def set(self, kind: str, caption: str = "") -> None:
        self.badges.append(kind)


def _app(monkeypatch, **cfg_kw) -> Utterleaf:
    monkeypatch.setattr("utterleaf.app.beep", lambda *_a, **_k: None)
    cfg = Config(tray=False, indicator=False, beep=False, min_seconds=0.35, **cfg_kw)
    app = Utterleaf(cfg)
    app.recorder = FakeRecorder()
    return app


def test_cancel_during_decode_never_pastes(monkeypatch):
    app = _app(monkeypatch)
    app.state = "busy"
    pasted = []
    monkeypatch.setattr("utterleaf.app.foreground_app", lambda: "editor")
    monkeypatch.setattr("utterleaf.app.paste", lambda *a, **k: pasted.append(a))
    def decode(*_):
        app.cancel_recording()
        return "This should never be pasted."
    monkeypatch.setattr("utterleaf.app.transcribe", decode)
    app._finish(np.ones(16000, dtype=np.float32), target=123)
    assert not pasted
    assert not app._job_running


def test_edit_command_never_undoes_another_window(monkeypatch):
    app = _app(monkeypatch)
    app.last_text = "Previous text."
    app.last_target = 123
    app.last_paste_at = time.time()
    monkeypatch.setattr("utterleaf.app.foreground_id", lambda: 456)
    monkeypatch.setattr("utterleaf.app.foreground_app", lambda: "editor")
    monkeypatch.setattr("utterleaf.app.transcribe", lambda *a: "scratch that")
    undone = []
    badges = []
    monkeypatch.setattr("utterleaf.app.undo_last", lambda: undone.append(True))
    monkeypatch.setattr(app, "_after_job", lambda badge="hide", caption="": badges.append(badge))
    app._finish(np.ones(16000, dtype=np.float32), target=456)
    assert not undone
    assert badges == ["no_paste"]


def test_long_decode_keeps_continuation_captured_at_take_start(monkeypatch):
    app = _app(monkeypatch)
    app.last_text = "The first sentence."
    app.last_app = "editor"
    app.last_target = 123
    app.last_paste_at = time.time()
    monkeypatch.setattr("utterleaf.app.foreground_id", lambda: 123)
    monkeypatch.setattr("utterleaf.app.foreground_app", lambda: "editor")
    app.start_recording()
    continuation = app._take_continuation
    assert continuation == (123, "editor")

    # The decode completes after the ordinary 20-second continuation window.
    app.last_paste_at -= 21
    monkeypatch.setattr("utterleaf.app.transcribe", lambda *_a: "the next sentence")
    monkeypatch.setattr(
        "utterleaf.app.polish",
        lambda *_a, **_k: SimpleNamespace(
            command_only=False, command=None, discarded=False, text="The next sentence"
        ),
    )
    pasted: list[str] = []
    monkeypatch.setattr("utterleaf.app.paste", lambda text, **_k: pasted.append(text) or "pasted")
    app._finish(np.ones(16000, dtype=np.float32), target=123, continuation=continuation)
    assert pasted == [" The next sentence"]


def test_continuation_is_dropped_when_target_switches(monkeypatch):
    app = _app(monkeypatch)
    app.last_text = "The first sentence."
    app.last_app = "editor"
    app.last_target = 123
    app.last_paste_at = time.time()
    continuation = (123, "editor")
    monkeypatch.setattr("utterleaf.app.foreground_app", lambda: "browser")
    monkeypatch.setattr("utterleaf.app.transcribe", lambda *_a: "the next sentence")
    monkeypatch.setattr(
        "utterleaf.app.polish",
        lambda *_a, **_k: SimpleNamespace(
            command_only=False, command=None, discarded=False, text="The next sentence"
        ),
    )
    pasted: list[str] = []
    monkeypatch.setattr("utterleaf.app.paste", lambda text, **_k: pasted.append(text) or "pasted")
    app._finish(np.ones(16000, dtype=np.float32), target=456, continuation=continuation)
    assert pasted == ["The next sentence"]


def test_short_tap_does_not_paste(monkeypatch) -> None:
    app = _app(monkeypatch)
    app.recorder = FakeRecorder(seconds=0.1)
    flashed: list[str] = []
    monkeypatch.setattr(app, "_flash", lambda badge, caption="": flashed.append(badge))
    app.state = "busy"
    app._job_running = True
    app._cut(None, False, app._cut_id)
    assert flashed == ["too_short"]
    assert app._job_running is False
    assert app._queued_audio is None


def test_follow_on_take_is_queued(monkeypatch) -> None:
    app = _app(monkeypatch)
    app.recorder = FakeRecorder(seconds=1.0)
    app.state = "busy"
    app._job_running = True
    app._cut("hwnd", True, app._cut_id)
    assert app._queued_audio is not None
    assert app._queued_target == "hwnd"


def test_cancel_busy_drops_queued_take(monkeypatch) -> None:
    app = _app(monkeypatch)
    app.state = "busy"
    app._job_running = True
    app._queued_audio = np.ones(100, dtype=np.float32)
    app._queued_target = "hwnd"
    app.cancel_recording()
    assert app._queued_audio is None
    assert app._queued_target is None
    assert app._cancel_job is True


def test_cancelled_finish_does_not_run_queue(monkeypatch) -> None:
    app = _app(monkeypatch)
    app._cancel_job = True
    app._queued_audio = np.ones(16000, dtype=np.float32)
    app._queued_target = "hwnd"
    started: list[object] = []

    class BoomThread:
        def __init__(self, **kwargs) -> None:
            started.append(kwargs)

        def start(self) -> None:
            return None

    monkeypatch.setattr("utterleaf.app.threading.Thread", BoomThread)
    flashed: list[str] = []
    monkeypatch.setattr(app, "_flash", lambda badge, caption="": flashed.append(badge))
    app.state = "busy"
    app._job_running = True
    app._finish(np.ones(16000, dtype=np.float32))
    assert app._queued_audio is None
    assert started == []
    assert flashed == ["hide"]
    assert app._cancel_job is False


def test_transcription_error_is_not_a_paste_failure(monkeypatch) -> None:
    app = _app(monkeypatch)
    monkeypatch.setattr("utterleaf.app.foreground_app", lambda: "notepad")

    def boom(*_a, **_k):
        raise RuntimeError("cublas exploded")

    monkeypatch.setattr("utterleaf.app.transcribe", boom)
    badges: list[str] = []
    monkeypatch.setattr(app, "_after_job", lambda badge="hide", caption="": badges.append(badge))
    app._finish(np.ones(16000, dtype=np.float32))
    assert badges == ["transcribe"]


def test_engine_error_does_not_auto_hide(monkeypatch) -> None:
    app = _app(monkeypatch)
    hidden: list[float] = []
    monkeypatch.setattr(app, "_hide_after", lambda seconds: hidden.append(seconds))
    app._show_error("engine", ENGINE_FAILED, "down", seconds=None)
    assert hidden == []
    app._show_error("no_mic", "x", "y", seconds=4.0)
    assert hidden == [4.0]


def test_idle_keeps_engine_failed_pill(monkeypatch) -> None:
    app = _app(monkeypatch)
    app._status = ENGINE_FAILED
    badges: list[str] = []
    monkeypatch.setattr(
        app, "_set_icon", lambda color, status=None, badge=None, caption="": badges.append(badge or "")
    )
    app._idle()
    assert badges == ["engine"]


def test_ipc_toggle_replies_before_recording_side_effects(monkeypatch):
    app = _app(monkeypatch)
    release = threading.Event()
    finished = threading.Event()

    def blocked_toggle() -> None:
        release.wait(2)
        finished.set()

    app.hotkey = SimpleNamespace(toggle=blocked_toggle)
    assert app._handle_ipc("toggle") == "ok"
    assert not finished.is_set()
    release.set()
    assert finished.wait(2)


def test_reload_honors_indicator_off(monkeypatch) -> None:
    monkeypatch.setattr("utterleaf.app.beep", lambda *_a, **_k: None)
    app = Utterleaf(Config(tray=True, indicator=True, beep=False))
    app.recorder = FakeRecorder()
    app.indicator = FakePill(enabled=True)
    monkeypatch.setattr("utterleaf.app.Indicator", FakePill)
    monkeypatch.setattr(
        "utterleaf.config.load",
        lambda: Config(tray=True, indicator=False, beep=False, hotkey=app.cfg.hotkey, mode=app.cfg.mode),
    )
    app.reload_config()
    assert app.indicator.enabled is False


def test_reload_honors_indicator_on(monkeypatch) -> None:
    monkeypatch.setattr("utterleaf.app.beep", lambda *_a, **_k: None)
    app = Utterleaf(Config(tray=True, indicator=False, beep=False))
    app.recorder = FakeRecorder()
    app.indicator = FakePill(enabled=False)
    monkeypatch.setattr("utterleaf.app.Indicator", FakePill)
    monkeypatch.setattr(
        "utterleaf.config.load",
        lambda: Config(tray=True, indicator=True, beep=False, hotkey=app.cfg.hotkey, mode=app.cfg.mode),
    )
    app.reload_config()
    assert app.indicator.enabled is True
    assert app.indicator.started == 1
