"""Real thread boundaries around delivery cancellation; no mic or OS paste."""

import threading
from types import SimpleNamespace

import numpy as np
import pytest

from utterleaf import app as module
from utterleaf.app import Utterleaf, _EndpointTake
from utterleaf.config import Config
from utterleaf.edit_target import Field


@pytest.fixture
def delivery(monkeypatch):
    application = Utterleaf(Config(tray=False, indicator=False, beep=False))
    field = Field((123, 456, 7), "", 0, 0)
    statuses = []
    monkeypatch.setattr(module, "beep", lambda *args: None)
    monkeypatch.setattr(module, "transcribe", lambda *args: "Keep processing local")
    monkeypatch.setattr(module, "foreground_id", lambda: 123)
    monkeypatch.setattr(module, "foreground_app", lambda: "editor")
    monkeypatch.setattr(module.edit_target, "read_field", lambda: field)
    monkeypatch.setattr(module.edit_target, "capture", lambda *args: "receipt")
    monkeypatch.setattr(application, "_schedule_edit_expiry", lambda: None)

    def flash(badge, caption=""):
        application.state = "idle"
        statuses.append((badge, caption))

    monkeypatch.setattr(application, "_flash", flash)
    yield application, field, statuses
    application.recent_dictation.clear()


@pytest.mark.parametrize("endpoint", [False, True])
def test_cancel_reaches_waiting_delivery_and_drops_queue(delivery, monkeypatch, endpoint):
    application, field, statuses = delivery
    application.state = "busy"
    application._job_running = True
    application.last_text = "Earlier text."
    application._edit_receipt = "earlier receipt"
    entered, release = threading.Event(), threading.Event()
    old_signal = application._delivery_cancel
    predicates = []

    def paste(text, *, cancel, **kwargs):
        predicates.append(cancel)
        entered.set()
        assert old_signal.wait(2), "Cancel did not reach delivery"
        assert cancel()
        assert release.wait(2)
        return "uncertain"

    monkeypatch.setattr(module, "paste", paste)
    target = (_EndpointTake(123, "editor", "insert", application.cfg, field=field)
              if endpoint else 123)
    worker = threading.Thread(target=application._finish, args=(np.ones(16000), target))
    cancel_worker = threading.Thread(target=application.cancel_recording)
    worker.start()
    try:
        assert entered.wait(2)
        with application._lock:
            application._queued_audio = np.ones(16000)
            application._queued_target = 123
        cancel_worker.start()
        assert old_signal.wait(2)
        with application._lock:
            assert application._queued_audio is None
        if endpoint:
            assert cancel_worker.is_alive(), "Fixture must hold capture ownership during paste"
        assert predicates[0]()
    finally:
        release.set()
        worker.join(2)
        if cancel_worker.ident is not None:
            cancel_worker.join(2)
    assert not worker.is_alive() and not cancel_worker.is_alive()
    assert statuses[-1][0] == "uncertain"
    assert "may already be inserted" in statuses[-1][1]
    assert application.last_text == ""
    assert application._edit_receipt is None
    assert not application._job_running
    assert not application._cancel_job
    assert application.recent_dictation.get()

    # Future work gets a fresh signal; the old predicate can never be revived.
    next_cancellations = []
    monkeypatch.setattr(module, "paste", lambda text, *, cancel, **kwargs:
                        next_cancellations.append(cancel()) or "pasted")
    application.state = "busy"
    application._job_running = True
    application._finish(np.ones(16000), target)
    assert next_cancellations == [False]
    assert predicates[0]()
    assert statuses[-1][0] == "pasted"


def test_cancel_during_last_field_read_prevents_manual_paste(delivery, monkeypatch):
    application, field, statuses = delivery
    application.state = "busy"
    application._job_running = True

    def read_field():
        application.cancel_recording()
        return field

    monkeypatch.setattr(module.edit_target, "read_field", read_field)
    monkeypatch.setattr(module, "paste", lambda *args, **kwargs: pytest.fail("Cancelled before dispatch"))
    application._finish(np.ones(16000), 123)
    assert statuses == [("hide", "")]
    assert not application.recent_dictation.get()


def test_cancel_during_review_focus_wait_cannot_insert(delivery, monkeypatch):
    application, field, statuses = delivery
    callbacks = []
    monkeypatch.setattr("utterleaf.review_ui.launch_review", lambda text, action, failure, **kwargs:
                        callbacks.append(action) or SimpleNamespace(close=lambda: None))
    application._remember_result("Reviewed text")
    application._present_review("Reviewed text", _EndpointTake(
        123, "editor", "review", application.cfg, field=field))
    entered = threading.Event()
    old_signal = application._delivery_cancel

    def foreground():
        entered.set()
        assert old_signal.wait(2)
        return 999

    monkeypatch.setattr(module, "foreground_id", foreground)
    monkeypatch.setattr(module, "paste", lambda *args, **kwargs: pytest.fail("Cancelled review must not paste"))
    worker = threading.Thread(target=callbacks[0], args=("insert",))
    cancel_worker = threading.Thread(target=application.cancel_recording)
    worker.start()
    try:
        assert entered.wait(2)
        cancel_worker.start()
    finally:
        worker.join(2)
        if cancel_worker.ident is not None:
            cancel_worker.join(2)
    assert not worker.is_alive() and not cancel_worker.is_alive()
    assert not statuses


def test_late_delivery_after_quit_does_not_restore_ui_or_receipt(delivery, monkeypatch):
    application, field, statuses = delivery
    application.state = "busy"
    application._job_running = True

    def paste(text, *, cancel, **kwargs):
        application.quit()
        assert cancel()
        return "uncertain"

    monkeypatch.setattr(module.ipc, "clear", lambda: None)
    monkeypatch.setattr(module, "paste", paste)
    application._finish(np.ones(16000), 123)
    assert application._stop.is_set()
    assert not application._job_running
    assert not application.recent_dictation.get()
    assert not statuses
    assert application._edit_receipt is None


def test_delayed_cancel_does_not_stop_newer_recording(delivery, monkeypatch):
    application, field, statuses = delivery
    old_signal = application._delivery_cancel
    stopped = []
    monkeypatch.setattr(application, "_cancel_recording", lambda: stopped.append(True))
    with application._capture_lock:
        worker = threading.Thread(target=application.cancel_recording)
        worker.start()
        assert old_signal.wait(2)
        application._cut_id += 1
        application.state = "recording"
    worker.join(2)
    assert not worker.is_alive()
    assert not stopped


@pytest.mark.parametrize("raw", ["scratch that, new text", "scratch that", "make this shorter", "make it more professional"])
def test_cancel_in_edit_focus_guard_prevents_native_edit(delivery, monkeypatch, raw):
    application, field, statuses = delivery
    application.state = "busy"
    application._job_running = True
    application.last_text = "I think we should ship it."
    application.last_target = 123
    application.last_app = "editor"
    application.last_paste_at = module.time.time()
    monkeypatch.setattr(module, "transcribe", lambda *args: raw)

    def foreground():
        application.cancel_recording()
        return 123

    monkeypatch.setattr(module, "foreground_id", foreground)
    monkeypatch.setattr(module.edit_target, "replace", lambda *args: pytest.fail("No native edit after cancellation"))
    monkeypatch.setattr(module, "paste", lambda *args, **kwargs: pytest.fail("No paste after cancellation"))
    application._finish(np.ones(16000), 123)
    assert statuses[-1][0] == "hide"
    assert application.last_text == "I think we should ship it."


def test_cancel_during_native_edit_is_reported_uncertain(delivery, monkeypatch):
    application, field, statuses = delivery
    application.state = "busy"
    application._job_running = True
    application.last_text = "I think we should ship it."
    application.last_target = 123
    application.last_app = "editor"
    application.last_paste_at = module.time.time()
    monkeypatch.setattr(module, "transcribe", lambda *args: "make this shorter")
    calls = []

    def replace(*args):
        calls.append(args)
        application.cancel_recording()
        return "replaced", "receipt"

    monkeypatch.setattr(module.edit_target, "replace", replace)
    application._finish(np.ones(16000), 123)
    assert len(calls) == 1
    assert statuses[-1][0] == "uncertain"
    assert application._edit_receipt is None


def test_uncertain_delivery_is_visible_with_tray_only(delivery, monkeypatch):
    application, field, statuses = delivery
    icons = []
    monkeypatch.setattr(application, "_set_icon", lambda color, status, **kwargs: icons.append((status, kwargs)))
    monkeypatch.setattr(application, "_hide_after", lambda seconds: None)
    assert not application.cfg.indicator
    Utterleaf._flash(application, "uncertain", "Check the field before recovering.")
    assert "unconfirmed" in icons[0][0]
    assert "before retrying" in icons[0][0]
    assert icons[0][1]["badge"] == "no_paste"


def test_cancelled_slow_decode_preserves_take_queued_after_cancel(delivery, monkeypatch):
    application, field, statuses = delivery
    application.state = "busy"
    application._job_running = True
    decoding, release, delivered = threading.Event(), threading.Event(), threading.Event()
    pasted = []

    def transcribe(audio, cfg):
        if audio[0] == 1:
            decoding.set()
            assert release.wait(2)
            return "Cancelled old words"
        return "Next take saved"

    def paste(text, *, cancel, **kwargs):
        assert not cancel()
        pasted.append(text)
        delivered.set()
        return "pasted"

    monkeypatch.setattr(module, "transcribe", transcribe)
    monkeypatch.setattr(module, "paste", paste)
    application.recorder = SimpleNamespace(stop=lambda: np.full(16000, 2),
                                           close=lambda: None, seconds=lambda audio: 1)
    worker = threading.Thread(target=application._finish, args=(np.ones(16000), 123))
    worker.start()
    try:
        assert decoding.wait(2)
        application.cancel_recording()
        # The new recording is released through the actual queue insertion path
        # while the cancelled decode still owns the transcription worker.
        application._cut_id += 1
        application._cut(123, True, application._cut_id)
        assert application._queued_audio is not None
        release.set()
        assert delivered.wait(2), "Older cancellation discarded the new queued take"
    finally:
        release.set()
        worker.join(2)
    assert not worker.is_alive()
    assert pasted == ["Next take saved. "]


def test_delayed_cancel_cannot_rearm_flag_between_job_end_and_idle(delivery, monkeypatch):
    application, field, statuses = delivery
    application.state = "busy"
    application._job_running = True
    old_signal = application._delivery_cancel
    entered, allow_cancel, flashing, allow_flash = [threading.Event() for _ in range(4)]
    gate = threading.RLock()

    class CaptureLock:
        def __enter__(self):
            assert allow_cancel.wait(2)
            gate.acquire()

        def __exit__(self, *args):
            gate.release()

    application._capture_lock = CaptureLock()

    def paste(text, *, cancel, **kwargs):
        entered.set()
        assert old_signal.wait(2)
        assert cancel()
        return "uncertain"

    def flash(badge, caption=""):
        flashing.set()
        assert allow_flash.wait(2)
        application.state = "idle"

    monkeypatch.setattr(module, "paste", paste)
    monkeypatch.setattr(application, "_flash", flash)
    worker = threading.Thread(target=application._finish, args=(np.ones(16000), 123))
    cancel_worker = threading.Thread(target=application.cancel_recording)
    worker.start()
    try:
        assert entered.wait(2)
        cancel_worker.start()
        assert flashing.wait(2)
        assert application.state == "busy"
        assert not application._job_running
        allow_cancel.set()
        cancel_worker.join(2)
        assert not cancel_worker.is_alive()
        assert not application._cancel_job
    finally:
        allow_cancel.set()
        allow_flash.set()
        worker.join(2)
        if cancel_worker.ident is not None:
            cancel_worker.join(2)
    assert not worker.is_alive()
    assert not application._delivery_guard()()


@pytest.mark.parametrize("raw", ["scratch that, new text", "scratch that", "make this shorter"])
def test_quit_during_native_edit_cannot_restore_receipt(delivery, monkeypatch, raw):
    application, field, statuses = delivery
    application.state = "busy"
    application._job_running = True
    application.last_text = "I think we should ship it."
    application.last_target = 123
    application.last_app = "editor"
    application.last_paste_at = module.time.time()
    application._edit_receipt = "earlier receipt"
    monkeypatch.setattr(module, "transcribe", lambda *args: raw)
    monkeypatch.setattr(module.ipc, "clear", lambda: None)

    def replace(*args):
        application.quit()
        return "replaced", "late receipt"

    monkeypatch.setattr(module.edit_target, "replace", replace)
    application._finish(np.ones(16000), 123)
    assert application._stop.is_set()
    assert application._edit_receipt is None
    assert not application.recent_dictation.get()
    assert not statuses


@pytest.mark.parametrize("mode", ["manual", "insert", "review"])
def test_quit_between_guard_and_recovery_commit_keeps_result_forgotten(delivery, monkeypatch, mode):
    application, field, statuses = delivery
    application.state = "busy"
    application._job_running = True
    reached, release = threading.Event(), threading.Event()
    remember = application._remember_result

    def delayed_remember(text):
        reached.set()
        assert release.wait(2)
        remember(text)

    monkeypatch.setattr(application, "_remember_result", delayed_remember)
    monkeypatch.setattr(module.ipc, "clear", lambda: None)
    monkeypatch.setattr(module, "paste", lambda text, *, cancel, **kwargs:
                        "cancelled" if cancel() else pytest.fail("No paste after quit"))
    monkeypatch.setattr("utterleaf.review_ui.launch_review", lambda *args, **kwargs:
                        pytest.fail("No review process after quit"))
    target = (123 if mode == "manual" else
              _EndpointTake(123, "editor", mode, application.cfg, field=field))
    worker = threading.Thread(target=application._finish, args=(np.ones(16000), target))
    worker.start()
    try:
        assert reached.wait(2)
        application.quit()
    finally:
        release.set()
        worker.join(2)
    assert not worker.is_alive()
    assert not application.recent_dictation.get()
    assert application._review is None
    assert application._edit_receipt is None
    assert not statuses
