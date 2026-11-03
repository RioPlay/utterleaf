"""Real Settings save/controller checks with synthetic storage, reload and dialogs."""

from dataclasses import replace
import sys
import threading
import tkinter as tk
from types import SimpleNamespace
import unicodedata

import pytest

from test_settings_ui import tk_root, window
from utterleaf.config import Config
from utterleaf.model_setup import ModelAvailability
from utterleaf.settings import FormValidationError, SettingsSaveError
from utterleaf.settings_ui import SettingsWindow


PRIVATE = "private-save-sentinel C:/private-account/settings.toml"
STEPS = ("dictation settings", "vocabulary", "start at login")
RETRY = "Your form entries are kept. Try Save again."


def _blocked(*_args, **_kwargs):
    pytest.fail("Unexpected external operation in a save-recovery UI test")


@pytest.fixture(autouse=True)
def save_guards(monkeypatch):
    alerts, details, questions = [], [], []
    monkeypatch.setattr("utterleaf.model_setup.inspect_model",
                        lambda name, backend: ModelAvailability(name, backend, "missing", None))
    monkeypatch.setattr("utterleaf.settings_ui.load", Config)
    for target in ("utterleaf.settings.save", "utterleaf.settings.save_dictionary",
                   "utterleaf.settings.set_startup", "utterleaf.ipc.send",
                   "utterleaf.config.save", "utterleaf.polish.save_dictionary",
                   "utterleaf.model_setup.run_download", "utterleaf.hardware.probe"):
        monkeypatch.setattr(target, _blocked)
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.showerror",
                        lambda title, message, **kw: alerts.append((title, message, kw)))
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.showinfo",
                        lambda title, message, **kw: details.append((title, message, kw)))

    def ask(title, message, **kw):
        questions.append((title, message, kw))
        return False

    monkeypatch.setattr("utterleaf.settings_ui.messagebox.askyesno", ask)
    return SimpleNamespace(alerts=alerts, details=details, questions=questions)


@pytest.fixture
def held_workers(monkeypatch):
    """Keep production _worker/commit/queue semantics without a background race."""
    workers = []
    monkeypatch.setattr(threading.Thread, "start", lambda thread: workers.append(thread._target))
    return workers


@pytest.fixture
def storage(monkeypatch):
    state = SimpleNamespace(calls=[], reloads=[], loaded=[], configs=[], names=[], login=[],
                            failure=None, reload_error=None, reply="ok", saved=Config())

    def load():
        state.loaded.append(state.saved)
        return state.saved

    def write(stage, values):
        state.calls.append(stage)
        if state.failure == stage:
            raise OSError(PRIVATE)
        values()

    monkeypatch.setattr("utterleaf.settings_ui.load", load)
    monkeypatch.setattr("utterleaf.settings.save",
                        lambda cfg: write(STEPS[0], lambda: state.configs.append(cfg)))
    monkeypatch.setattr("utterleaf.settings.save_dictionary",
                        lambda text: write(STEPS[1], lambda: state.names.append(text)))
    monkeypatch.setattr("utterleaf.settings.set_startup",
                        lambda enabled: write(STEPS[2], lambda: state.login.append(enabled)))

    def reload(command):
        state.reloads.append(command)
        if state.reload_error is not None:
            raise state.reload_error
        return state.reply

    monkeypatch.setattr("utterleaf.ipc.send", reload)
    return state


def _finish(window, workers, *, deliver=True):
    assert len(workers) == 1
    workers.pop()()
    callback, result = window.events.get_nowait()
    assert window.events.empty()
    if deliver:
        callback(result)
    return callback, result


def _edit(window):
    window.vars["hotkey"].set("f8")
    window.vars["allow_network"].set(False)
    window.vars["restore_clipboard"].set(False)
    return window._snapshot()


def _assert_unlocked(window):
    assert not window.saving
    assert window._save_operation is None
    assert not window.save_button.instate(["disabled"])
    assert not window.reset_button.instate(["disabled"])


def _assert_no_details(window):
    assert window._save_details == ""
    assert not window.save_details_button.winfo_manager()


def _assert_safe_alert(window, dialogs, *, title=None, message=None):
    assert len(dialogs.alerts) == 1
    actual_title, actual_message, kwargs = dialogs.alerts[0]
    if title is not None:
        assert actual_title == title
    if message is not None:
        assert actual_message == message
    assert kwargs["parent"] == window.root
    assert "private-save-sentinel" not in actual_title + actual_message + window.status.get()
    assert "C:/private-account" not in actual_title + actual_message + window.status.get()
    assert dialogs.details == []


@pytest.mark.parametrize("failed_index", range(3))
def test_save_failure_reports_real_ordered_progress_and_keeps_draft(
        window, storage, held_workers, save_guards, failed_index):
    snapshot = _edit(window)
    baseline = dict(window.baseline)
    old_cfg = window.cfg
    storage.failure = STEPS[failed_index]
    window.save()
    assert window.saving and window._save_operation is not None
    assert window.save_button.instate(["disabled"])
    assert window.reset_button.instate(["disabled"])
    _, result = _finish(window, held_workers)
    assert isinstance(result.error, SettingsSaveError)
    assert result.error.saved == STEPS[:failed_index]
    assert result.error.failed == STEPS[failed_index]
    assert result.error.pending == STEPS[failed_index + 1:]
    assert storage.calls == list(STEPS[:failed_index + 1])
    assert storage.reloads == (["reload"] if failed_index else [])
    assert len(storage.loaded) == 1
    expected = (f"Saved: {', '.join(STEPS[:failed_index]) or 'none'}.\n"
                f"Not saved: {STEPS[failed_index]}.\n"
                f"Not attempted: {', '.join(STEPS[failed_index + 1:]) or 'none'}.\n\n{RETRY}")
    _assert_safe_alert(window, save_guards,
                       title="Some changes were saved" if failed_index else "Couldn't save settings",
                       message=expected)
    assert window.status.get() == ("Some changes saved" if failed_index else "Couldn't finish saving")
    assert window.cfg is old_cfg
    assert window.baseline == baseline
    assert window._snapshot() == snapshot
    assert PRIVATE in window._save_details
    _assert_unlocked(window)


@pytest.mark.parametrize("malformed", [False, True])
def test_unknown_or_untrusted_save_progress_stays_uncertain(
        window, storage, held_workers, save_guards, monkeypatch, malformed):
    snapshot = _edit(window)
    error = (SettingsSaveError([PRIVATE], "vocabulary", ["start at login"], OSError(PRIVATE))
             if malformed else RuntimeError(PRIVATE))

    def fail(*_args, **_kwargs):
        raise error

    monkeypatch.setattr("utterleaf.settings_ui.apply_form", fail)
    window.save()
    _finish(window, held_workers)
    _assert_safe_alert(window, save_guards, title="Couldn't finish saving",
                       message="Save progress could not be confirmed. Some changes may have been saved.\n\n" + RETRY)
    assert window._snapshot() == snapshot
    assert storage.calls == []
    assert storage.reloads == (["reload"] if malformed else [])
    _assert_unlocked(window)


def test_worker_start_failure_is_safe_unlocks_and_allows_retry(
        window, storage, save_guards, monkeypatch):
    snapshot = _edit(window)
    baseline = dict(window.baseline)

    def fail_start(_thread):
        raise RuntimeError(PRIVATE)

    monkeypatch.setattr(threading.Thread, "start", fail_start)
    window.save()
    _assert_safe_alert(window, save_guards, title="Save did not start",
                       message="This save attempt made no changes.\n\n" + RETRY)
    _assert_unlocked(window)
    assert window._snapshot() == snapshot and window.baseline == baseline
    assert storage.calls == storage.loaded == storage.reloads == []
    workers = []
    monkeypatch.setattr(threading.Thread, "start", lambda thread: workers.append(thread._target))
    window.save()
    _assert_no_details(window)
    _finish(window, workers)
    assert window.baseline == snapshot
    assert not window.saving
    assert len(save_guards.alerts) == 1


@pytest.mark.parametrize("failed_index", [1, 2])
def test_partial_save_keeps_structured_progress_when_reload_also_raises(
        window, storage, held_workers, save_guards, failed_index):
    snapshot = _edit(window)
    baseline = dict(window.baseline)
    storage.failure = STEPS[failed_index]
    storage.reload_error = OSError("private reload-sentinel")
    window.save()
    _, outcome = _finish(window, held_workers)
    assert isinstance(outcome.error, SettingsSaveError)
    assert outcome.error.saved == STEPS[:failed_index]
    assert outcome.reload_error is storage.reload_error
    assert storage.calls == list(STEPS[:failed_index + 1])
    assert storage.reloads == ["reload"]
    _assert_safe_alert(window, save_guards, title="Some changes were saved")
    message = save_guards.alerts[0][1]
    assert f"Saved: {', '.join(STEPS[:failed_index])}." in message
    assert "The running app could not be notified" in message
    assert "private reload-sentinel" not in message + window.status.get()
    assert PRIVATE in window._save_details and "private reload-sentinel" in window._save_details
    assert window._snapshot() == snapshot and window.baseline == baseline
    _assert_unlocked(window)


@pytest.mark.parametrize("later_edit", [False, True])
def test_full_save_reload_exception_keeps_confirmed_success_and_captured_baseline(
        window, storage, held_workers, save_guards, later_edit):
    snapshot = _edit(window)
    storage.reload_error = OSError(PRIVATE)
    window.save()
    if later_edit:
        window.vars["hotkey"].set("f9")
    _, outcome = _finish(window, held_workers)
    assert outcome.error is None and outcome.config is storage.configs[0]
    assert outcome.reload_error is storage.reload_error
    assert storage.calls == list(STEPS) and storage.reloads == ["reload"]
    assert window.cfg is outcome.config
    assert window.baseline == snapshot
    assert not window._reset_pending and not window.saving
    assert window.vars["hotkey"].get() == ("f9" if later_edit else "f8")
    assert window.status.get() == ("Unsaved changes" if later_edit else "Saved · Restart Utterleaf to apply")
    _assert_safe_alert(window, save_guards)
    assert "saved" in save_guards.alerts[0][1].lower()
    assert "restart" in save_guards.alerts[0][1].lower() or "reopen" in save_guards.alerts[0][1].lower()
    assert "Some changes may have been saved" not in save_guards.alerts[0][1]
    assert PRIVATE in window._save_details


def test_save_snapshot_overlap_close_and_later_edits_keep_existing_semantics(
        window, storage, held_workers, save_guards):
    snapshot = _edit(window)
    window.save()
    operation = window._save_operation
    window.save()
    window.close()
    assert len(held_workers) == 1 and window._save_operation is operation
    assert not window.closed and save_guards.questions == []
    assert window.status.get() == "Finishing your save…"
    window.vars["hotkey"].set("f9")
    window.vars["allow_network"].set(True)
    _finish(window, held_workers)
    assert storage.configs[0].hotkey == "f8" and not storage.configs[0].allow_network
    assert not storage.configs[0].restore_clipboard
    assert window.baseline == snapshot
    assert window.vars["hotkey"].get() == "f9" and window.vars["allow_network"].get()
    assert window.status.get() == "Unsaved changes"
    assert storage.calls == list(STEPS) and storage.reloads == ["reload"]
    _assert_unlocked(window)


def test_stale_save_completion_does_not_unlock_or_replace_new_attempt(
        window, storage, held_workers, save_guards):
    _edit(window)
    storage.failure = "vocabulary"
    window.save()
    old_done, old_result = _finish(window, held_workers)
    storage.failure = None
    window.vars["hotkey"].set("f9")
    snapshot = window._snapshot()
    window.save()
    operation, status = window._save_operation, window.status.get()
    old_done(old_result)
    assert window.saving and window._save_operation is operation
    assert window.status.get() == status
    assert len(save_guards.alerts) == 1
    _finish(window, held_workers)
    old_done(old_result)
    assert window.baseline == snapshot
    assert window.status.get() == "Changes saved"
    assert len(save_guards.alerts) == 1
    _assert_no_details(window)


def test_closed_save_callback_and_public_save_never_touch_destroyed_tk(
        window, storage, held_workers, save_guards):
    _edit(window)
    window.save()
    done, result = _finish(window, held_workers, deliver=False)
    window.closed = True
    window.root.after_cancel(window.poll_id)
    if window._page_reset is not None:
        window.root.after_cancel(window._page_reset)
    window.root.destroy()
    done(result)
    done(RuntimeError(PRIVATE))
    window.save()
    window.show_save_details()
    assert held_workers == [] and save_guards.alerts == save_guards.details == []
    assert storage.calls == list(STEPS)


@pytest.mark.parametrize("field", ["hotkey", "names"])
def test_save_validation_still_routes_native_alert_and_field_line_focus(
        window, storage, held_workers, save_guards, field):
    window.root.deiconify()
    window.navigate("Help & diagnostics")
    if field == "names":
        window.names.delete("1.0", "end")
        window.names.insert("1.0", "valid = replacement\nmissing separator")
    else:
        window.vars["hotkey"].set("escape")
    window.root.update()
    snapshot = window._snapshot()
    window.save()
    _, result = _finish(window, held_workers)
    window.root.update()
    assert isinstance(result, FormValidationError)
    assert storage.calls == storage.reloads == []
    assert len(save_guards.alerts) == 1 and save_guards.alerts[0][0] == "Check your settings"
    assert save_guards.alerts[0][1] == str(result)
    target = window.fields[field]
    assert window.root.focus_get() == target
    if field == "names":
        assert window.pages["Vocabulary"].winfo_ismapped()
        assert target.get("sel.first", "sel.last") == "missing separator"
    else:
        assert window.pages["Dictation"].winfo_ismapped()
    assert window._snapshot() == snapshot
    _assert_no_details(window)
    _assert_unlocked(window)


def test_failed_staged_reset_retains_privacy_and_retry_uses_defaults_without_load(
        window, storage, held_workers, save_guards, monkeypatch):
    window.cfg = replace(Config(), compute_type="float16", max_seconds=1, tray=False)
    _edit(window)
    vocabulary = window.names.get("1.0", "end-1c")
    baseline = dict(window.baseline)
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.askyesno", lambda *a, **k: True)
    monkeypatch.setattr("utterleaf.settings_ui.load", _blocked)
    window.restore_defaults()
    snapshot = window._snapshot()
    assert window._reset_pending
    assert not snapshot["allow_network"] and not snapshot["restore_clipboard"]
    assert snapshot["names"] == vocabulary
    storage.failure = "start at login"
    window.save()
    _finish(window, held_workers)
    assert window._reset_pending and window.baseline == baseline
    assert window._snapshot() == snapshot
    assert storage.configs[0].compute_type == Config().compute_type
    assert storage.configs[0].max_seconds == Config().max_seconds
    storage.failure = None
    window.save()
    _assert_no_details(window)
    _finish(window, held_workers)
    assert not window._reset_pending and window.baseline == snapshot
    assert storage.calls == list(STEPS) * 2 and storage.reloads == ["reload"] * 2
    assert storage.loaded == []


@pytest.mark.parametrize("change", ["edit", "reset", "retry", "close"])
def test_error_details_clear_on_new_intent_and_hidden_focus_stays_useful(
        window, storage, held_workers, save_guards, monkeypatch, change):
    _edit(window)
    storage.failure = "vocabulary"
    window.root.deiconify()
    window.save()
    _finish(window, held_workers)
    window.root.update()
    window.save_details_button.focus_force()
    window.root.update()
    assert window.root.focus_get() == window.save_details_button
    if change == "edit":
        window.vars["hotkey"].set("f9")
    elif change == "reset":
        monkeypatch.setattr("utterleaf.settings_ui.messagebox.askyesno", lambda *a, **k: True)
        window.restore_defaults()
    elif change == "retry":
        window.save()
    else:
        monkeypatch.setattr("utterleaf.settings_ui.messagebox.askyesno", lambda *a, **k: True)
        window.close()
    assert window._save_details == ""
    if change == "close":
        assert window.closed
        return
    window.root.update()
    _assert_no_details(window)
    focused = window.root.focus_get()
    assert focused in (window.save_button, window.close_button)
    assert focused.winfo_ismapped() and not focused.instate(["disabled"])
    assert len(save_guards.alerts) == 1 and save_guards.details == []


def test_save_details_are_explicit_bounded_and_control_sanitized(
        window, held_workers, save_guards, monkeypatch):
    _edit(window)

    def fail(*_args, **_kwargs):
        raise RuntimeError(PRIVATE + "\x00\x1b\u202e\t" + "x" * 6000 + "\nline" * 30)

    monkeypatch.setattr("utterleaf.settings_ui.apply_form", fail)
    window.save()
    _finish(window, held_workers)
    _assert_safe_alert(window, save_guards)
    details = window._save_details
    assert PRIVATE in details and len(details) < 2200
    assert len(details.splitlines()) <= 13
    assert all(char == "\n" or unicodedata.category(char) not in {"Cc", "Cf", "Cs"} for char in details)
    window.save_details_button.invoke()
    assert len(save_guards.details) == 1
    assert save_guards.details[0][1] == details
    assert save_guards.details[0][2]["parent"] == window.root


def test_ctrl_s_from_details_keeps_enabled_visible_focus_during_retry_and_success(
        window, storage, held_workers, save_guards):
    _edit(window)
    storage.failure = "vocabulary"
    window.root.deiconify()
    window.save()
    _finish(window, held_workers)
    window.root.update()
    window.save_details_button.focus_force()
    window.root.update()
    assert window.root.focus_get() == window.save_details_button
    storage.failure = None
    shortcut = "<Command-s>" if sys.platform == "darwin" else "<Control-s>"
    window.save_details_button.event_generate(shortcut)
    window.root.update()
    assert window.saving and len(held_workers) == 1
    _assert_no_details(window)
    assert window.root.focus_get() == window.close_button
    assert window.close_button.winfo_ismapped() and not window.close_button.instate(["disabled"])
    _finish(window, held_workers)
    window.root.update()
    assert not window.saving and window.save_button.instate(["disabled"])
    assert window.root.focus_get() == window.close_button
    assert window.close_button.winfo_ismapped() and not window.close_button.instate(["disabled"])
    assert len(save_guards.alerts) == 1 and save_guards.details == []


def _assert_inside(widget, viewport):
    assert widget.winfo_ismapped()
    assert widget.winfo_width() >= widget.winfo_reqwidth()
    assert widget.winfo_height() >= widget.winfo_reqheight()
    x, y = widget.winfo_rootx() - viewport.winfo_rootx(), widget.winfo_rooty() - viewport.winfo_rooty()
    assert 0 <= x and 0 <= y
    assert x + widget.winfo_width() <= viewport.winfo_width()
    assert y + widget.winfo_height() <= viewport.winfo_height()


@pytest.mark.parametrize("scale", [1.0, 1.5, 2.0])
@pytest.mark.parametrize("failure", ["partial", "unknown", "start", "reload"])
def test_save_recovery_footer_navigation_and_input_fit_resize_roundtrip(
        tk_root, monkeypatch, held_workers, storage, save_guards, scale, failure):
    monkeypatch.setattr("utterleaf.settings_ui.startup_enabled", lambda: False)
    monkeypatch.setattr("utterleaf.settings_ui.dictionary_text", lambda: "utter leaf = Utterleaf")
    scaling = float(tk_root.tk.call("tk", "scaling"))
    root = tk.Toplevel(tk_root)
    app = None
    try:
        root.tk.call("tk", "scaling", scaling * scale)
        app = SettingsWindow(root, Config(), background=False)
        root.geometry("760x560")
        _edit(app)
        root.update()
        if failure == "partial":
            storage.failure = "vocabulary"
        elif failure == "reload":
            storage.reload_error = OSError(PRIVATE)
        else:
            def fail(*_args, **_kwargs):
                raise RuntimeError(PRIVATE)

            monkeypatch.setattr(threading.Thread if failure == "start" else sys.modules["utterleaf.settings_ui"],
                                "start" if failure == "start" else "apply_form", fail)
        app.save_button.focus_force()
        root.update()
        app.save_button.event_generate("<KeyPress-space>")
        if failure != "start":
            _finish(app, held_workers)
        root.update()
        snapshot = app._snapshot()
        expected_status = app.status.get()
        assert app._save_details and len(save_guards.alerts) == 1
        for width, height in ((760, 560), (1180, 820), (760, 560)):
            root.geometry(f"{width}x{height}")
            root.update()
            for control in (app.footer_status, app.save_details_button, app.save_button, app.close_button):
                _assert_inside(control, root)
            for control in app.nav.values():
                _assert_inside(control, control.master)
            assert app._snapshot() == snapshot and app.status.get() == expected_status

        # Native keyboard activation opens only explicit bounded Details.
        app.save_details_button.focus_force()
        root.update()
        following = app.save_details_button.tk_focusNext()
        app.save_details_button.event_generate("<Tab>")
        root.update()
        assert root.focus_get() == following
        following.event_generate("<Shift-Tab>")
        root.update()
        assert root.focus_get() == app.save_details_button
        app.save_details_button.event_generate("<KeyPress-space>")
        root.update()
        assert len(save_guards.details) == 1

        # A real press/release sequence keeps its original footer target fixed.
        app.close_button.focus_force()
        root.update()
        button = app.save_details_button
        before = (button.winfo_rootx(), button.winfo_rooty(), button.winfo_width(), button.winfo_height())
        x, y = button.winfo_width() // 2, button.winfo_height() // 2
        button.event_generate("<Enter>")
        button.event_generate("<ButtonPress-1>", x=x, y=y)
        root.update()
        assert (button.winfo_rootx(), button.winfo_rooty(), button.winfo_width(), button.winfo_height()) == before
        button.event_generate("<ButtonRelease-1>", x=x, y=y)
        root.update()
        assert len(save_guards.details) == 2
        assert app._snapshot() == snapshot
    finally:
        if app is not None and not app.closed:
            app.closed = True
            root.after_cancel(app.poll_id)
            if app._page_reset is not None:
                root.after_cancel(app._page_reset)
        root.destroy()
        tk_root.tk.call("tk", "scaling", scaling)
