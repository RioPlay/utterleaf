"""Hold-to-talk state machine: short taps, queue, cancel, honest failures."""

from __future__ import annotations

from types import SimpleNamespace
import threading
import time

import numpy as np
import pytest

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

    def start(self, max_seconds=None) -> None:
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
    monkeypatch.setattr("utterleaf.app.edit_target.read_field", lambda: None)
    monkeypatch.setattr("utterleaf.app.copy_text", lambda text: True)
    cfg = Config(tray=False, indicator=False, beep=False, min_seconds=0.35, **cfg_kw)
    app = Utterleaf(cfg)
    app.recorder = FakeRecorder()
    return app


def test_three_prose_passes_keep_separators_after_title_change_and_timeout(monkeypatch):
    app = _app(monkeypatch)
    takes = iter(["Bring it to the front.", "Just little nitpicks.", "Guess that helps."])
    title = ["chat — draft 1"]
    pasted = []
    monkeypatch.setattr("utterleaf.app.foreground_app", lambda: title[0])
    monkeypatch.setattr("utterleaf.app.foreground_id", lambda: 123)
    monkeypatch.setattr("utterleaf.app.transcribe", lambda *a: next(takes))
    monkeypatch.setattr("utterleaf.app.paste", lambda text, **kw: pasted.append(text) or "pasted")
    monkeypatch.setattr("utterleaf.app.edit_target.capture", lambda *a: None)
    monkeypatch.setattr(app, "_schedule_edit_expiry", lambda: None)
    app._finish(np.ones(16000, dtype=np.float32), target=123)
    title[0] = "chat — draft 2"
    app._finish(np.ones(16000, dtype=np.float32), target=123)
    app.last_paste_at -= 30
    app._finish(np.ones(16000, dtype=np.float32), target=123)
    assert "".join(pasted) == "Bring it to the front. Just little nitpicks. Guess that helps. "
    assert app.recent_dictation.get() == "Guess that helps."
    app.recent_dictation.clear()


def test_layout_take_repairs_inner_sentences_and_keeps_next_take_separate(monkeypatch):
    app = _app(monkeypatch)
    takes = iter(["That is wrong.Maybe say no.I have an idea.Whatever works new paragraph",
                  "Next thought.", "Another thought."])
    pasted = []
    monkeypatch.setattr("utterleaf.app.foreground_app", lambda: "Codex.exe")
    monkeypatch.setattr("utterleaf.app.foreground_id", lambda: 123)
    monkeypatch.setattr("utterleaf.app.transcribe", lambda *a: next(takes))
    monkeypatch.setattr("utterleaf.app.paste", lambda text, **kw: pasted.append(text) or "pasted")
    monkeypatch.setattr("utterleaf.app.edit_target.capture", lambda *a: None)
    monkeypatch.setattr(app, "_schedule_edit_expiry", lambda: None)
    for _ in range(3):
        app._finish(np.ones(16000, dtype=np.float32), target=123)
        app.last_paste_at -= 30
    assert "".join(pasted) == ("That is wrong. Maybe say no. I have an idea. Whatever works\n\n"
                                "Next thought. Another thought. ")
    app.recent_dictation.clear()


@pytest.mark.parametrize("outcome", ["replaced", "unavailable", "failed"])
def test_spoken_replacement_uses_verified_entry_and_retains_correction(monkeypatch, outcome):
    app = _app(monkeypatch)
    app.last_text = "Old information."
    app.last_target = 123
    app.last_paste_at = time.time() - 45  # The old 20-second gate was too short.
    app._last_prefix = "\n"
    app._last_suffix = " "
    receipt = object()
    app._edit_receipt = receipt
    replacements, notices = [], []
    monkeypatch.setattr("utterleaf.app.foreground_id", lambda: 123)
    monkeypatch.setattr("utterleaf.app.foreground_app", lambda: "chat")
    monkeypatch.setattr("utterleaf.app.transcribe", lambda *a: "Scratch, that. New information")
    monkeypatch.setattr("utterleaf.app.paste", lambda *a, **k: pytest.fail("No blind paste"))
    monkeypatch.setattr("utterleaf.app.copy_text", lambda *a: pytest.fail("Copy requires a user action"))
    monkeypatch.setattr("utterleaf.app.edit_target.replace", lambda old, text: replacements.append((old, text)) or (outcome, None))
    monkeypatch.setattr(app, "_after_job", lambda badge="hide", caption="": notices.append((badge, caption)))
    monkeypatch.setattr(app, "_schedule_edit_expiry", lambda: None)
    app._finish(np.ones(16000, dtype=np.float32), target=123)
    assert replacements == [(receipt, "\nNew information. ")]
    assert app.recent_dictation.get() == "New information."
    if outcome == "replaced":
        assert app.last_text == "New information."
        assert app._last_suffix == " "
        assert notices[-1][0] == "pasted"
    else:
        assert app.last_text == "Old information."
        assert notices[-1][0] == "no_paste"
        assert "Copy last dictation" in notices[-1][1]
    app.recent_dictation.clear()


@pytest.mark.parametrize("target,age", [(456, 1), (123, 121)])
def test_replacement_never_mutates_wrong_or_expired_entry(monkeypatch, target, age):
    app = _app(monkeypatch)
    app.last_text = "Old information."
    app.last_target = 123
    app.last_paste_at = time.time() - age
    monkeypatch.setattr("utterleaf.app.foreground_id", lambda: target)
    monkeypatch.setattr("utterleaf.app.foreground_app", lambda: "chat")
    monkeypatch.setattr("utterleaf.app.transcribe", lambda *a: "scratch that, new information")
    monkeypatch.setattr("utterleaf.app.edit_target.replace", lambda *a: pytest.fail("Unsafe edit"))
    monkeypatch.setattr("utterleaf.app.paste", lambda *a, **k: pytest.fail("No blind paste"))
    monkeypatch.setattr(app, "_after_job", lambda *a: None)
    app._finish(np.ones(16000, dtype=np.float32), target=target)
    assert app.recent_dictation.get() == "New information."
    assert app.last_text == "Old information."
    app.recent_dictation.clear()


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


@pytest.mark.parametrize("raw", ["New prose.", "scratch that", "scratch that, new information", "make this shorter"])
@pytest.mark.parametrize("stopping", [False, True])
def test_cancel_during_formatting_prevents_delivery_and_edits(monkeypatch, raw, stopping):
    from utterleaf.polish import polish_local
    app = _app(monkeypatch)
    app.state = "busy"
    app.last_text = "I think this is previous text."
    app.last_target = 123
    app.last_paste_at = time.time()
    monkeypatch.setattr("utterleaf.app.foreground_id", lambda: 123)
    monkeypatch.setattr("utterleaf.app.foreground_app", lambda: "chat")
    monkeypatch.setattr("utterleaf.app.transcribe", lambda *a: raw)
    def format_text(*a, **kw):
        if stopping:
            app._stop.set()
        else:
            app.cancel_recording()
        return polish_local(raw, vocab=[])
    monkeypatch.setattr("utterleaf.app.polish", format_text)
    changes = []
    monkeypatch.setattr("utterleaf.app.paste", lambda *a, **kw: changes.append("paste") or "pasted")
    monkeypatch.setattr("utterleaf.app.edit_target.replace", lambda *a: (changes.append("edit") or "replaced", None))
    monkeypatch.setattr(app, "_schedule_edit_expiry", lambda: None)
    app._finish(np.ones(16000, dtype=np.float32), target=123)
    assert not changes
    assert app.recent_dictation.get() == ""
    assert app.last_text == "I think this is previous text."


@pytest.mark.parametrize("raw", ["scratch that", "scratch that, new information", "make this shorter"])
def test_command_cannot_retarget_earlier_take_by_switching_windows_during_decode(monkeypatch, raw):
    app = _app(monkeypatch)
    app.last_text = "I think this is previous text."
    app.last_target = 123
    app.last_paste_at = time.time()
    # This command was released in window 456, then focus moved back to 123.
    monkeypatch.setattr("utterleaf.app.foreground_id", lambda: 123)
    monkeypatch.setattr("utterleaf.app.foreground_app", lambda: "chat")
    monkeypatch.setattr("utterleaf.app.transcribe", lambda *a: raw)
    changes = []
    monkeypatch.setattr("utterleaf.app.edit_target.replace", lambda *a: (changes.append("edit") or "replaced", None))
    monkeypatch.setattr("utterleaf.app.paste", lambda *a, **kw: changes.append("paste") or "pasted")
    monkeypatch.setattr(app, "_schedule_edit_expiry", lambda: None)
    app._finish(np.ones(16000, dtype=np.float32), target=456)
    assert not changes
    assert app.last_target == 123
    app.recent_dictation.clear()


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
    monkeypatch.setattr("utterleaf.app.edit_target.replace", lambda *args: undone.append(True))
    monkeypatch.setattr(app, "_after_job", lambda badge="hide", caption="": badges.append(badge))
    app._finish(np.ones(16000, dtype=np.float32), target=456)
    assert not undone
    assert badges == ["no_paste"]


@pytest.mark.parametrize("outcome,badge", [("replaced", "pasted"), ("unavailable", "clipboard"), ("failed", "no_paste")])
def test_edit_command_reports_delivery_and_tracks_only_success(monkeypatch, outcome, badge):
    app = _app(monkeypatch)
    app.last_text = "I think we should ship it."
    app.last_target = 123
    app.last_app = "editor"
    app.last_paste_at = time.time() - 10
    old_time = app.last_paste_at
    monkeypatch.setattr("utterleaf.app.foreground_id", lambda: 123)
    monkeypatch.setattr("utterleaf.app.foreground_app", lambda: "editor")
    monkeypatch.setattr("utterleaf.app.transcribe", lambda *a: "make this shorter")
    monkeypatch.setattr("utterleaf.app.edit_target.replace", lambda *a: (outcome, None))
    monkeypatch.setattr("utterleaf.app.paste", lambda *a, **k: pytest.fail("Edits must not send blind paste"))
    badges = []
    monkeypatch.setattr(app, "_after_job", lambda badge="hide", caption="": badges.append(badge))
    app._finish(np.ones(16000, dtype=np.float32), target=123)
    assert badges == [badge]
    if outcome == "replaced":
        assert app.last_text
        assert app.last_target == 123
        assert app.last_paste_at > old_time
    else:
        assert app.last_text == "I think we should ship it."
        assert app._edit_receipt is None
        assert app.last_paste_at == old_time


@pytest.mark.parametrize("command", ["scratch that", "make this shorter"])
def test_failed_verified_edit_preserves_last_dictation_without_blind_paste(monkeypatch, command):
    app = _app(monkeypatch)
    app.last_text = "I think we should ship it."
    app.last_target = 123
    app.last_paste_at = time.time()
    monkeypatch.setattr("utterleaf.app.foreground_id", lambda: 123)
    monkeypatch.setattr("utterleaf.app.foreground_app", lambda: "editor")
    monkeypatch.setattr("utterleaf.app.transcribe", lambda *a: command)
    monkeypatch.setattr("utterleaf.app.edit_target.replace", lambda *a: ("failed", None))
    pasted = []
    monkeypatch.setattr("utterleaf.app.paste", lambda *a, **k: pasted.append(a))
    badges = []
    monkeypatch.setattr(app, "_after_job", lambda badge="hide", caption="": badges.append(badge))
    app._finish(np.ones(16000, dtype=np.float32), target=123)
    assert not pasted
    assert app.last_text == "I think we should ship it."
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


def test_rapid_restart_harvests_tail_with_original_target_and_worker(monkeypatch):
    app = _app(monkeypatch)
    launched = []

    class Timer:
        def __init__(self, interval, callback, args):
            self.callback, self.args = callback, args
        def start(self):
            pass
        def cancel(self):
            pass

    class Thread:
        def __init__(self, **kwargs):
            launched.append(kwargs)
        def start(self):
            pass

    monkeypatch.setattr("utterleaf.app.threading.Timer", Timer)
    monkeypatch.setattr("utterleaf.app.threading.Thread", Thread)
    monkeypatch.setattr("utterleaf.app.foreground_id", lambda: 123)
    monkeypatch.setattr("utterleaf.app.foreground_app", lambda: "editor")
    app.start_recording()
    app.stop_recording()
    monkeypatch.setattr("utterleaf.app.foreground_id", lambda: 456)
    app.start_recording()
    assert len(launched) == 1
    assert launched[0]["target"] == app._finish
    assert launched[0]["args"][1] == 123
    assert app._queued_audio is None
    assert app.state == "recording"


def test_follow_on_tail_starts_worker_when_previous_decode_finished(monkeypatch):
    app = _app(monkeypatch)
    app.state = "busy"
    app._job_running = False
    launched = []

    class Thread:
        def __init__(self, **kwargs):
            launched.append(kwargs)
        def start(self):
            pass

    monkeypatch.setattr("utterleaf.app.threading.Thread", Thread)
    app._cut(123, True, app._cut_id)
    assert len(launched) == 1
    assert launched[0]["args"][1] == 123
    assert app._job_running
    assert app._queued_audio is None


def test_previous_decode_does_not_hide_pending_tail(monkeypatch):
    app = _app(monkeypatch)
    app.state = "busy"
    app._job_running = True
    app._tail_timer = object()
    flashed = []
    monkeypatch.setattr(app, "_flash", lambda *a: flashed.append(a))
    app._after_job("pasted")
    assert not flashed
    assert app.state == "busy"
    assert not app._job_running


def test_limit_stops_once_announces_reason_and_resets_toggle(monkeypatch):
    app = _app(monkeypatch)
    app.state = "recording"
    reset = []
    app.hotkey = SimpleNamespace(reset_active=lambda: reset.append(True))
    timers = []
    class Timer:
        def __init__(self, *args, **kwargs):
            timers.append(self)
        def start(self):
            pass
        def cancel(self):
            pass
    monkeypatch.setattr("utterleaf.app.threading.Timer", Timer)
    messages = []
    monkeypatch.setattr(app, "_set_icon", lambda *a, **kw: messages.append(kw))
    app._recording_limit(app._cut_id)
    app._recording_limit(app._cut_id)
    assert app.state == "busy"
    assert reset == [True]
    assert len(timers) == 1
    assert "limit reached" in messages[0]["caption"]


def test_old_limit_timer_cannot_stop_a_new_take(monkeypatch):
    app = _app(monkeypatch)
    app.state = "recording"
    app._cut_id = 5
    app._preview_stop.clear()
    app._recording_limit(4)
    assert app.state == "recording"
    assert not app._preview_stop.is_set()
    assert app._tail_timer is None


def test_failed_microphone_start_resets_toggle_for_next_attempt(monkeypatch):
    app = _app(monkeypatch, mode="toggle")
    resets = []
    app.hotkey = SimpleNamespace(reset_active=lambda: resets.append(True))
    monkeypatch.setattr("utterleaf.app.foreground_id", lambda: 1)
    monkeypatch.setattr("utterleaf.app.foreground_app", lambda: "editor")
    def fail(**kwargs):
        raise RuntimeError("Device disappeared")
    monkeypatch.setattr(app.recorder, "start", fail)
    app.start_recording()
    assert app.state == "idle"
    assert resets == [True]
    assert app._limit_timer is None


def test_countdown_keeps_preview_and_stale_ticks_cannot_overwrite_status(monkeypatch):
    app = _app(monkeypatch)
    shown, timers = [], []
    app.indicator = SimpleNamespace(enabled=True, set=lambda *args: shown.append(args))
    app.state = "recording"
    app._cut_id = 5
    app._recording_deadline = 130.0
    app._recording_draft = "My draft"
    monkeypatch.setattr("utterleaf.app.time.monotonic", lambda: 120.0)
    class Timer:
        def __init__(self, *args, **kwargs):
            self.cancelled = False
            timers.append(self)
        def start(self):
            pass
        def cancel(self):
            self.cancelled = True
    monkeypatch.setattr("utterleaf.app.threading.Timer", Timer)
    app._update_countdown(5)
    assert shown == [("listening", "0:10 left · Finishing soon · My draft")]
    assert len(timers) == 1
    app._update_countdown(4)
    assert len(shown) == 1
    app.state = "busy"
    app._cancel_limit_timer()
    assert timers[0].cancelled
    app._update_countdown(5)
    assert len(shown) == 1


def test_cut_releases_microphone_before_transcription(monkeypatch):
    app = _app(monkeypatch)
    released = []
    monkeypatch.setattr(app.recorder, "close", lambda: released.append(True))
    class Thread:
        def __init__(self, **kwargs):
            assert released == [True]
        def start(self):
            pass
    monkeypatch.setattr("utterleaf.app.threading.Thread", Thread)
    app._cut(123, False, app._cut_id)
    assert released == [True]


def test_cancel_releases_microphone(monkeypatch):
    app = _app(monkeypatch)
    app.state = "recording"
    released = []
    monkeypatch.setattr(app.recorder, "close", lambda: released.append(True))
    app.cancel_recording()
    assert released == [True]
    assert app.state == "idle"


def test_start_sound_only_after_microphone_is_open(monkeypatch):
    app = _app(monkeypatch)
    events = []
    monkeypatch.setattr(app.recorder, "start", lambda **kw: events.append("open"))
    monkeypatch.setattr("utterleaf.app.beep", lambda kind, enabled: events.append(kind))
    app.start_recording()
    app.cancel_recording()
    assert events[:2] == ["open", "start"]


def test_full_backlog_refuses_new_recording_without_dropping_audio(monkeypatch):
    from utterleaf.app import MAX_PENDING_TAKES
    app = _app(monkeypatch)
    app.state = "busy"
    app._queued_audio = np.ones(16000, dtype=np.float32)
    app._queued_takes.extend((app._queued_audio, i, None) for i in range(MAX_PENDING_TAKES - 1))
    monkeypatch.setattr(app.recorder, "start", lambda **kw: pytest.fail("Queue full"))
    app.start_recording()
    assert len(app._queued_takes) == MAX_PENDING_TAKES - 1
    assert app.state == "busy"


def test_dictation_text_is_not_in_debug_logs(monkeypatch, caplog):
    import logging
    app = _app(monkeypatch)
    secret = "My private project is called Pineapple."
    monkeypatch.setattr("utterleaf.app.foreground_app", lambda: "editor")
    monkeypatch.setattr("utterleaf.app.transcribe", lambda *args: secret)
    monkeypatch.setattr("utterleaf.app.paste", lambda *args, **kwargs: "pasted")
    with caplog.at_level(logging.DEBUG, logger="utterleaf"):
        app._finish(np.ones(16000, dtype=np.float32), target=123)
    assert secret not in caplog.text
    assert "Pineapple" not in caplog.text
    assert "characters" in caplog.text


def test_failed_delivery_can_be_recovered_without_retranscribing(monkeypatch):
    app = _app(monkeypatch)
    monkeypatch.setattr("utterleaf.app.foreground_app", lambda: "editor")
    monkeypatch.setattr("utterleaf.app.transcribe", lambda *args: "Please keep this sentence.")
    monkeypatch.setattr("utterleaf.app.paste", lambda *args, **kwargs: "fail")
    app._finish(np.ones(16000, dtype=np.float32), target=123)
    copied = []
    monkeypatch.setattr("utterleaf.app.copy_text", lambda text: copied.append(text) or True)
    assert app.copy_last_dictation()
    assert copied == ["Please keep this sentence."]


def test_recovery_copy_failure_is_honest_and_keeps_text(monkeypatch):
    app = _app(monkeypatch)
    app.recent_dictation.put("Keep me.")
    monkeypatch.setattr("utterleaf.app.copy_text", lambda text: False)
    messages = []
    monkeypatch.setattr(app, "_show_error", lambda *args: messages.append(args))
    assert app.copy_last_dictation() is False
    assert app.recent_dictation.get() == "Keep me."
    assert messages[0][0] == "no_paste"


def test_forget_clears_recovery_and_edit_context_without_changing_clipboard(monkeypatch):
    app = _app(monkeypatch)
    app.recent_dictation.put("Keep me.")
    app.last_text = "Keep me."
    app._edit_receipt = object()
    monkeypatch.setattr("utterleaf.app.copy_text", lambda text: pytest.fail("Clipboard belongs to user"))
    app.forget_last_dictation()
    assert app.recent_dictation.get() == ""
    assert app.last_text == ""
    assert app._edit_receipt is None


def test_transcript_mode_does_not_execute_commands_or_add_sentence_formatting(monkeypatch):
    app = _app(monkeypatch, text_cleanup=False)
    app.last_text = "Previous words"
    app.last_app = "editor"
    app.last_target = 123
    app.last_paste_at = time.time()
    raw = "scratch that"
    monkeypatch.setattr("utterleaf.app.foreground_app", lambda: "editor")
    monkeypatch.setattr("utterleaf.app.foreground_id", lambda: 123)
    monkeypatch.setattr("utterleaf.app.transcribe", lambda *args: raw)
    monkeypatch.setattr("utterleaf.app.edit_target.replace", lambda *args: pytest.fail("Command must stay literal"))
    pasted = []
    monkeypatch.setattr("utterleaf.app.paste", lambda text, **kwargs: pasted.append(text) or "pasted")
    app._finish(np.ones(16000, dtype=np.float32), target=123)
    assert pasted == [raw]


def test_slow_decode_preserves_multiple_follow_on_takes_in_order(monkeypatch):
    app = _app(monkeypatch)
    app.state = "busy"
    app._job_running = True
    launched = []

    class Thread:
        def __init__(self, **kwargs):
            launched.append(kwargs)
        def start(self):
            pass

    monkeypatch.setattr("utterleaf.app.threading.Thread", Thread)
    app._cut(123, True, app._cut_id)
    app._cut_id += 1
    app._cut(456, True, app._cut_id)
    assert app._queued_target == 123
    app._after_job()
    app._after_job()
    assert [job["args"][1] for job in launched] == [123, 456]
    assert app._queued_audio is None
    assert not app._queued_takes


def test_cancel_busy_drops_queued_take(monkeypatch) -> None:
    app = _app(monkeypatch)
    app.state = "busy"
    app._job_running = True
    app._queued_audio = np.ones(100, dtype=np.float32)
    app._queued_target = "hwnd"
    app._queued_takes.append((app._queued_audio, "second", None))
    app.cancel_recording()
    assert app._queued_audio is None
    assert app._queued_target is None
    assert not app._queued_takes
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


def test_overlay_toggle_preserves_other_saved_settings(monkeypatch):
    app = _app(monkeypatch)
    saved = []
    monkeypatch.setattr("utterleaf.config.load", lambda: Config(model="medium", indicator=False))
    monkeypatch.setattr("utterleaf.config.save", lambda cfg: saved.append(cfg))
    monkeypatch.setattr(app, "_sync_indicator", lambda: None)
    app.toggle_indicator()
    assert saved[0].model == "medium"
    assert saved[0].indicator is True
    assert app.cfg.indicator is True


def test_overlay_save_failure_keeps_current_preference(monkeypatch):
    app = _app(monkeypatch)
    monkeypatch.setattr("utterleaf.config.load", lambda: Config())
    def fail(_):
        raise OSError("read only")
    monkeypatch.setattr("utterleaf.config.save", fail)
    app.toggle_indicator()
    assert app.cfg.indicator is False


def test_hidden_overlay_does_not_start_preview_inference(monkeypatch):
    app = _app(monkeypatch, live_preview=True)
    app.state = "recording"
    waits = iter([False, True])
    monkeypatch.setattr(app._preview_stop, "wait", lambda _: next(waits))
    def infer(*_):
        raise AssertionError("Hidden captions must not transcribe")
    monkeypatch.setattr("utterleaf.app.transcribe_preview", infer)
    app._preview_loop(app._cut_id)


def test_tray_failure_uses_error_art_and_recovers(monkeypatch):
    app = _app(monkeypatch)
    app.icon = SimpleNamespace(icon=None, title="")
    monkeypatch.setattr("utterleaf.app.leaf_image", lambda state: state)
    app._set_icon("idle", "Microphone unavailable", badge="no_mic")
    assert app.icon.icon == "error"
    app._set_icon("idle", "Ready", badge="hide")
    assert app.icon.icon == "idle"


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
