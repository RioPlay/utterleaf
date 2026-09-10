"""Interrupted takes must recover locally without unsolicited editor actions."""

import sys
from threading import Event, RLock, Thread as NativeThread, get_ident
from types import SimpleNamespace

import numpy as np
import pytest

from utterleaf import app as module
from utterleaf.app import Utterleaf, _InterruptedTake
from utterleaf.config import Config


@pytest.fixture
def interrupted_app(monkeypatch):
    timers = []

    class Timer:
        def __init__(self, interval, function, args=(), kwargs=None):
            self.interval = interval
            self.function = function
            self.args = args
            self.cancelled = False
            timers.append(self)

        def start(self):
            pass

        def cancel(self):
            self.cancelled = True

    class Thread:
        def __init__(self, target, args=(), **kwargs):
            self.target, self.args = target, args

        def start(self):
            self.target(*self.args)

    class Recorder:
        def __init__(self):
            self.audio = np.ones(16000, dtype=np.float32)
            self.recording = False
            self.closed = False
            self.error = "The microphone stream stopped."

        def start(self, max_seconds=None):
            self.recording = True
            self.closed = False

        def capture_error(self):
            return self.error

        def stop(self):
            self.recording = False
            return self.audio

        def close(self):
            self.closed = True

        def seconds(self, audio):
            return len(audio) / 16000

    monkeypatch.setattr(module.threading, "Timer", Timer)
    monkeypatch.setattr(module.threading, "Thread", Thread)
    monkeypatch.setattr(module, "beep", lambda *args: None)
    monkeypatch.setattr(module, "foreground_id", lambda: 123)
    monkeypatch.setattr(module, "foreground_app", lambda: "editor")
    monkeypatch.setattr(module, "transcribe", lambda *args: "scratch that")
    monkeypatch.setattr(module, "polish", lambda *a, **k: pytest.fail("Interruption must not execute commands"))
    monkeypatch.setattr(module, "paste", lambda *a, **k: pytest.fail("Interruption must not paste"))
    monkeypatch.setattr(module, "copy_text", lambda *a: pytest.fail("Recovery requires explicit copy"))
    monkeypatch.setattr(module.edit_target, "read_field", lambda: pytest.fail("Recovery must not read an editor"))
    application = Utterleaf(Config(tray=False, indicator=False, beep=False))
    application.recent_dictation._timer_factory = Timer
    application.recorder = Recorder()
    resets, statuses = [], []
    application.hotkey = SimpleNamespace(reset_active=lambda: resets.append(True))
    monkeypatch.setattr(application, "_set_icon", lambda *a, **k: statuses.append((a, k)))
    application.start_recording()
    yield SimpleNamespace(app=application, timers=timers, resets=resets, statuses=statuses)
    application._cancel_limit_timer()
    application.recent_dictation.clear()


def test_interrupted_take_recovers_literal_text_and_releases_mic(interrupted_app, monkeypatch):
    application = interrupted_app.app
    monitor = application._capture_timer
    monkeypatch.setattr(module, "foreground_app", lambda: pytest.fail("No target lookup for recovery"))
    monkeypatch.setattr(module, "foreground_id", lambda: pytest.fail("No target lookup for recovery"))
    application._check_capture(application._cut_id)
    assert application.recorder.closed
    assert not application.recorder.recording
    assert interrupted_app.resets == [True]
    assert application.recent_dictation.get() == "scratch that"
    assert application.recent_dictation.ttl == 120
    assert application.state == "idle"
    assert application._limit_timer is None
    assert application._capture_timer is None
    assert application._tail_timer is None
    assert "Copy last dictation" in interrupted_app.statuses[-1][1]["caption"]
    assert monitor.interval == .5
    assert application.cfg.indicator is False


def test_healthy_capture_reschedules_without_stopping(interrupted_app):
    application = interrupted_app.app
    application.recorder.error = None
    previous = application._capture_timer
    application._check_capture(application._cut_id)
    assert application.state == "recording"
    assert not application.recorder.closed
    assert application._capture_timer is not previous
    assert not interrupted_app.resets


def test_old_watchdog_cannot_stop_a_new_take(interrupted_app):
    application = interrupted_app.app
    previous = application._capture_timer
    application._check_capture(application._cut_id - 1)
    assert application.state == "recording"
    assert application._capture_timer is previous
    assert not interrupted_app.resets


def test_quit_watchdog_cannot_recover_or_schedule_again(interrupted_app):
    application = interrupted_app.app
    application._stop.set()
    count = len(interrupted_app.timers)
    application._check_capture(application._cut_id)
    assert application.recent_dictation.get() == ""
    assert len(interrupted_app.timers) == count


def test_cancel_discards_before_watchdog_can_recover(interrupted_app):
    application = interrupted_app.app
    timer = application._capture_timer
    application.cancel_recording()
    application._check_capture(application._cut_id)
    assert timer.cancelled
    assert application.recent_dictation.get() == ""
    assert application.state == "idle"


def test_cancel_during_interrupted_decode_suppresses_recovery(interrupted_app, monkeypatch):
    application = interrupted_app.app

    def transcribe(*args):
        application.cancel_recording()
        return "discard this"

    monkeypatch.setattr(module, "transcribe", transcribe)
    application._check_capture(application._cut_id)
    assert application.recent_dictation.get() == ""
    assert not application._job_running


def test_cancel_after_decode_check_wins_before_result_commit(interrupted_app):
    application = interrupted_app.app
    application.state = "busy"
    application._job_running = True
    attempted_commit = Event()
    gate = RLock()
    caller = get_ident()

    class CommitLock:
        def __enter__(self):
            if get_ident() != caller:
                attempted_commit.set()
            gate.acquire()

        def __exit__(self, *args):
            gate.release()

    application._capture_lock = CommitLock()
    with application._capture_lock:
        worker = NativeThread(target=application._finish, args=(
            application.recorder.audio, _InterruptedTake("The microphone stream stopped.")))
        worker.start()
        assert attempted_commit.wait(2), "Worker did not reach the recovery commit boundary"
        application.cancel_recording()
    worker.join(2)
    assert not worker.is_alive()
    assert application.recent_dictation.get() == ""
    assert not application._job_running
    assert not application._cancel_job


def test_manual_stop_detects_interruption_before_watchdog_fires(interrupted_app):
    application = interrupted_app.app
    application.stop_recording()
    assert application.recorder.closed
    assert application._tail_timer is None
    assert application.recent_dictation.get() == "scratch that"
    assert interrupted_app.resets == [True]


@pytest.mark.parametrize("queued", [False, True])
def test_healthy_release_then_tail_failure_recovers_without_insertion(interrupted_app, monkeypatch, queued):
    application = interrupted_app.app
    application.recorder.error = None
    application._take_continuation = (123, "editor")
    application._job_running = queued
    results = []
    finish = application._finish

    def observe_finish(audio, target=None, continuation=None):
        results.append((target, continuation))
        finish(audio, target, continuation)

    monkeypatch.setattr(application, "_finish", observe_finish)
    application.stop_recording()
    tail = application._tail_timer
    assert tail is not None
    assert tail.args[0] == 123
    assert tail.args[3] == (123, "editor")
    assert application._capture_timer is None
    application.recorder.error = "The microphone stream stopped."
    application._cut(*tail.args)
    assert application.recorder.closed
    if queued:
        assert isinstance(application._queued_target, _InterruptedTake)
        assert application._queued_continuation is None
        application._after_job()
    assert application.recent_dictation.get() == "scratch that"
    assert len(results) == 1
    assert isinstance(results[0][0], _InterruptedTake)
    assert results[0][1] is None
    application._cut(*tail.args)
    assert len(results) == 1


def test_already_interrupted_take_does_not_recheck_or_replace_reason(interrupted_app, monkeypatch):
    application = interrupted_app.app
    calls = []

    def check():
        calls.append(True)
        return "The microphone stopped sending audio."

    monkeypatch.setattr(application.recorder, "capture_error", check)
    application._check_capture(application._cut_id)
    assert calls == [True]
    assert "stopped sending audio" in interrupted_app.statuses[-1][1]["caption"]


def test_short_interruption_explains_missing_recovery(interrupted_app, monkeypatch):
    application = interrupted_app.app
    application.recorder.audio = np.ones(100, dtype=np.float32)
    monkeypatch.setattr(module, "transcribe", lambda *args: pytest.fail("Too short to decode"))
    application._check_capture(application._cut_id)
    assert application.recorder.closed
    assert application.state == "idle"
    assert not application._job_running
    assert "Too little audio" in interrupted_app.statuses[-1][1]["caption"]


def test_silent_interrupted_decode_explains_no_recovered_speech(interrupted_app, monkeypatch):
    application = interrupted_app.app
    monkeypatch.setattr(module, "transcribe", lambda *args: "")
    application._check_capture(application._cut_id)
    assert application.recent_dictation.get() == ""
    assert "No speech was recovered" in interrupted_app.statuses[-1][1]["caption"]


def test_interruption_queued_behind_existing_decode_retains_recovery_marker(interrupted_app):
    application = interrupted_app.app
    application._job_running = True
    application._check_capture(application._cut_id)
    assert isinstance(application._queued_target, _InterruptedTake)
    assert application.recorder.closed
    assert application.recent_dictation.get() == ""
    application._after_job()
    assert application.recent_dictation.get() == "scratch that"
    assert not application._job_running


def test_close_error_does_not_discard_interrupted_speech(interrupted_app, monkeypatch):
    application = interrupted_app.app

    def close():
        raise RuntimeError("Device disappeared")

    monkeypatch.setattr(application.recorder, "close", close)
    application._check_capture(application._cut_id)
    assert application.recent_dictation.get() == "scratch that"


def test_new_take_clears_interrupted_status_and_arms_fresh_monitor(interrupted_app):
    application = interrupted_app.app
    old_id = application._cut_id
    application._check_capture(old_id)
    application.recorder.error = None
    application.start_recording()
    application._check_capture(old_id)
    assert application.state == "recording"
    assert application._cut_id == old_id + 1
    assert application._capture_timer.args == (old_id + 1,)


def test_tray_file_action_loads_file_ui_only_when_invoked(monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, "utterleaf.file_ui", SimpleNamespace(launch_files=lambda: calls.append(True)))
    Utterleaf._launch_files()
    assert calls == [True]
