"""Recording-feedback reset checks with real Tk and isolated persistence."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
from uuid import uuid4

import pytest

from test_settings_ui import tk_root
from utterleaf.config import Config
from utterleaf.config import load as load_config
from utterleaf.config import save as save_config
from utterleaf.model_setup import ModelAvailability
from utterleaf.settings_ui import SettingsWindow


FEEDBACK = ("indicator", "live_preview", "beep")
PRIVATE = "private-section-reset-sentinel C:/private/settings.toml"


def _blocked(*_args, **_kwargs):
    pytest.fail("Recording-feedback reset performed an external operation")


@pytest.fixture(autouse=True)
def no_external_operations(monkeypatch):
    monkeypatch.setattr(
        "utterleaf.model_setup.inspect_model",
        lambda name, backend: ModelAvailability(name, backend, "missing", None),
    )
    for target in (
        "utterleaf.settings.save",
        "utterleaf.settings.save_dictionary",
        "utterleaf.settings.set_startup",
        "utterleaf.ipc.send",
        "utterleaf.config.save",
        "utterleaf.polish.save_dictionary",
        "utterleaf.model_setup.run_download",
        "utterleaf.hardware.probe",
    ):
        monkeypatch.setattr(target, _blocked)


@pytest.fixture
def app_factory(monkeypatch, tk_root):
    apps = []
    monkeypatch.setattr("utterleaf.settings_ui.startup_enabled", lambda: False)
    monkeypatch.setattr(
        "utterleaf.settings_ui.dictionary_text", lambda: "utter leaf = Utterleaf"
    )

    def make(cfg=None):
        root = tk.Toplevel(tk_root)
        root.withdraw()
        app = SettingsWindow(root, cfg or Config(), background=False)
        apps.append(app)
        return app

    yield make

    for app in apps:
        try:
            exists = bool(app.root.winfo_exists())
        except tk.TclError:
            exists = False
        if not exists:
            continue
        app.closed = True
        try:
            app.root.after_cancel(app.poll_id)
        except tk.TclError:
            pass
        if app._page_reset is not None:
            try:
                app.root.after_cancel(app._page_reset)
            except tk.TclError:
                pass
        app.root.destroy()


def _nondefault_feedback(**changes):
    return replace(
        Config(), indicator=True, live_preview=True, beep=False, **changes
    )


def _feedback(snapshot):
    return {key: snapshot[key] for key in FEEDBACK}


def _confirm(monkeypatch, answer=True, *, move_focus_to=None):
    questions = []

    def ask(title, message, **kwargs):
        questions.append((title, message, kwargs))
        if move_focus_to is not None:
            move_focus_to.focus_set()
        return answer

    monkeypatch.setattr("utterleaf.settings_ui.messagebox.askyesno", ask)
    return questions


def _finish_save(app, held):
    assert len(held) == 1
    action, done = held.pop()
    result = action()
    done(result)
    return result


def test_decline_preserves_entire_draft_flags_focus_and_explains_scope(
    app_factory, monkeypatch
):
    app = app_factory(_nondefault_feedback(allow_network=False))
    app.vars["hotkey"].set("f8")
    app.vars["start_at_login"].set(True)
    app.names.insert("end", "\nprivate = Local")
    app.root.deiconify()
    app.root.geometry("760x560")
    app.navigate("Dictation")
    app.feedback_reset_button.focus_force()
    app.root.update()
    before = app._snapshot()
    baseline = dict(app.baseline)
    cfg = app.cfg
    status = app.status.get()
    questions = _confirm(monkeypatch, False, move_focus_to=app.save_button)

    app.reset_recording_feedback()

    assert app._snapshot() == before
    assert app.cfg is cfg and app.baseline == baseline
    assert not app._reset_pending and not app._resetting_feedback
    assert app.root.focus_get() == app.feedback_reset_button
    assert app.status.get() == status
    assert len(questions) == 1
    title, message, kwargs = questions[0]
    assert title == "Reset Recording feedback?" and kwargs["parent"] is app.root
    lowered = message.lower()
    assert all(term in lowered for term in ("floating indicator", "live preview", "start / stop sounds"))
    assert "other unsaved edits" in lowered and "save changes saves all pending edits" in lowered


def test_focus_query_and_dialog_exceptions_release_reentry_latch(
    app_factory, monkeypatch
):
    app = app_factory(_nondefault_feedback())
    before = app._snapshot()
    original_focus_get = app.root.focus_get
    focus_calls = 0

    def focus_get():
        nonlocal focus_calls
        focus_calls += 1
        if focus_calls == 1:
            raise tk.TclError("gone")
        return original_focus_get()

    monkeypatch.setattr(app.root, "focus_get", focus_get)
    questions = _confirm(monkeypatch)

    app.reset_recording_feedback()

    assert len(questions) == 1
    assert focus_calls > 1
    assert not app._resetting_feedback
    assert _feedback(app._snapshot()) == _feedback(Config().__dict__)

    app.vars["indicator"].set(True)
    before = app._snapshot()
    monkeypatch.setattr(
        "utterleaf.settings_ui.messagebox.askyesno",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("dialog failed")),
    )
    with pytest.raises(RuntimeError, match="dialog failed"):
        app.reset_recording_feedback()
    assert not app._resetting_feedback and app._snapshot() == before


def test_confirm_changes_only_feedback_and_preserves_global_reset_state(
    app_factory, monkeypatch
):
    app = app_factory(
        _nondefault_feedback(compute_type="float16", max_seconds=1, tray=False)
    )
    _confirm(monkeypatch)
    app.restore_defaults()
    assert app._reset_pending
    app.vars["device"].set("gpu")
    app.vars["indicator"].set(True)
    app.vars["live_preview"].set(True)
    app.vars["beep"].set(False)
    before = app._snapshot()
    baseline = dict(app.baseline)
    cfg = app.cfg
    app.checking_mic = True
    app.mic_stop.clear()

    app.reset_recording_feedback()

    after = app._snapshot()
    assert _feedback(after) == _feedback(Config().__dict__)
    assert {key: value for key, value in after.items() if key not in FEEDBACK} == {
        key: value for key, value in before.items() if key not in FEEDBACK
    }
    assert app.cfg is cfg and app.baseline == baseline and app._reset_pending
    assert app.checking_mic is True and not app.mic_stop.is_set()
    app.checking_mic = False
    assert not app._resetting_feedback
    assert "save changes to apply" in app.status.get().lower()


def test_already_default_section_stays_clean(app_factory, monkeypatch):
    app = app_factory(Config())
    questions = _confirm(monkeypatch)
    before = app._snapshot()
    status = app.status.get()

    app.feedback_reset_button.invoke()

    assert len(questions) == 1
    assert app._snapshot() == before == app.baseline
    assert not app._reset_pending
    assert app.save_button.instate(["disabled"])
    assert app.status.get() == status


def test_reset_moves_focus_only_when_preview_becomes_disabled(app_factory, monkeypatch):
    app = app_factory(_nondefault_feedback())
    _confirm(monkeypatch)
    app.root.deiconify()
    app.root.geometry("760x560")
    app.navigate("Dictation")
    app.preview_toggle.focus_force()
    app.root.update()
    assert app.root.focus_get() == app.preview_toggle

    app.reset_recording_feedback()
    app.root.update()

    assert app.preview_toggle.instate(["disabled"])
    assert app.root.focus_get() == app.feedback_reset_button


@pytest.mark.parametrize("state", ["closed", "saving"])
def test_dialog_completion_rechecks_closed_or_saving_state(
    app_factory, monkeypatch, state
):
    app = app_factory(_nondefault_feedback())
    before = app._snapshot()
    calls = []

    def ask(*_args, **_kwargs):
        calls.append(state)
        setattr(app, state, True)
        return True

    monkeypatch.setattr("utterleaf.settings_ui.messagebox.askyesno", ask)
    app.reset_recording_feedback()

    assert calls == [state] and app._snapshot() == before
    assert not app._resetting_feedback
    setattr(app, state, False)


def test_closed_saving_and_reentrant_calls_cannot_open_another_prompt(
    app_factory, monkeypatch
):
    app = app_factory(_nondefault_feedback())
    calls = []

    def ask(*_args, **_kwargs):
        calls.append("outer")
        app.reset_recording_feedback()
        assert calls == ["outer"]
        return True

    monkeypatch.setattr("utterleaf.settings_ui.messagebox.askyesno", ask)
    app.reset_recording_feedback()
    assert calls == ["outer"] and _feedback(app._snapshot()) == _feedback(Config().__dict__)
    app.vars["indicator"].set(True)
    before = app._snapshot()
    app.saving = True
    app.reset_recording_feedback()
    app.saving = False
    app.closed = True
    app.reset_recording_feedback()
    app.closed = False
    assert calls == ["outer"] and app._snapshot() == before


def test_save_success_uses_reset_snapshot_and_keeps_newer_edits_unsaved(
    app_factory, monkeypatch
):
    original = _nondefault_feedback(allow_network=False)
    app = app_factory(original)
    _confirm(monkeypatch)
    app.vars["hotkey"].set("f8")
    app.reset_recording_feedback()
    submitted = app._snapshot()
    held = []
    state = SimpleNamespace(saved=None, names=[], login=[], reloads=[])
    monkeypatch.setattr("utterleaf.settings_ui.load", lambda: original)
    monkeypatch.setattr("utterleaf.settings.save", lambda cfg: setattr(state, "saved", cfg))
    monkeypatch.setattr("utterleaf.settings.save_dictionary", state.names.append)
    monkeypatch.setattr("utterleaf.settings.set_startup", state.login.append)
    monkeypatch.setattr("utterleaf.ipc.send", lambda command: state.reloads.append(command) or "ok")
    monkeypatch.setattr(app, "_worker", lambda action, done: held.append((action, done)))

    app.save()
    assert app.saving and app.feedback_reset_button.instate(["disabled"])
    app.vars["hotkey"].set("f9")
    app.reset_recording_feedback()
    _finish_save(app, held)

    assert state.saved is not None
    assert _feedback(state.saved.__dict__) == _feedback(Config().__dict__)
    assert state.saved.hotkey == "f8" and state.saved.allow_network is False
    assert state.names == [submitted["names"]] and state.login == [False]
    assert state.reloads == ["reload"]
    assert app.cfg == state.saved and app.baseline == submitted
    assert app.vars["hotkey"].get() == "f9"
    assert app.save_button.instate(["!disabled"])
    assert app.feedback_reset_button.instate(["!disabled"])


def test_save_failure_retains_reset_and_retry_succeeds(app_factory, monkeypatch):
    original = _nondefault_feedback()
    app = app_factory(original)
    _confirm(monkeypatch)
    app.vars["device"].set("gpu")
    app.reset_recording_feedback()
    draft = app._snapshot()
    baseline = dict(app.baseline)
    held = []
    attempts = []
    monkeypatch.setattr("utterleaf.settings_ui.load", lambda: original)

    def save(cfg):
        attempts.append(cfg)
        if len(attempts) == 1:
            raise OSError(PRIVATE)

    monkeypatch.setattr("utterleaf.settings.save", save)
    monkeypatch.setattr("utterleaf.settings.save_dictionary", lambda _text: None)
    monkeypatch.setattr("utterleaf.settings.set_startup", lambda _enabled: None)
    monkeypatch.setattr("utterleaf.ipc.send", lambda _command: "ok")
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.showerror", lambda *_a, **_k: None)
    monkeypatch.setattr(app, "_worker", lambda action, done: held.append((action, done)))

    app.save()
    failed = _finish_save(app, held)
    assert failed.error is not None
    assert app._snapshot() == draft and app.baseline == baseline and app.cfg is original
    assert app.save_button.instate(["!disabled"])
    assert app.feedback_reset_button.instate(["!disabled"])
    app.save()
    succeeded = _finish_save(app, held)
    assert succeeded.error is None and app.cfg == attempts[-1]
    assert app.baseline == draft and app.save_button.instate(["disabled"])
    assert app.feedback_reset_button.instate(["!disabled"])


def test_global_reset_still_saves_advanced_defaults_after_section_reset(
    app_factory, monkeypatch
):
    original = _nondefault_feedback(compute_type="float16", max_seconds=1, tray=False)
    app = app_factory(original)
    _confirm(monkeypatch)
    app.restore_defaults()
    app.vars["indicator"].set(True)
    app.vars["live_preview"].set(True)
    app.vars["beep"].set(False)
    app.reset_recording_feedback()
    assert app._reset_pending
    held, saved = [], []
    monkeypatch.setattr("utterleaf.settings_ui.load", _blocked)
    monkeypatch.setattr("utterleaf.settings.save", saved.append)
    monkeypatch.setattr("utterleaf.settings.save_dictionary", lambda _text: None)
    monkeypatch.setattr("utterleaf.settings.set_startup", lambda _enabled: None)
    monkeypatch.setattr("utterleaf.ipc.send", lambda _command: "ok")
    monkeypatch.setattr(app, "_worker", lambda action, done: held.append((action, done)))

    app.save()
    _finish_save(app, held)

    assert len(saved) == 1
    assert saved[0].compute_type == Config().compute_type
    assert saved[0].max_seconds == Config().max_seconds
    assert saved[0].tray == Config().tray
    assert not app._reset_pending


def test_section_reset_then_global_reset_keeps_global_scope(app_factory, monkeypatch):
    app = app_factory(_nondefault_feedback(compute_type="float16", max_seconds=1))
    _confirm(monkeypatch)

    app.reset_recording_feedback()
    app.vars["device"].set("gpu")
    app.restore_defaults()

    assert app._reset_pending
    assert app._snapshot()["device"] == Config().device
    assert _feedback(app._snapshot()) == _feedback(Config().__dict__)


def test_discard_and_reopen_restores_isolated_saved_feedback(
    app_factory, monkeypatch, request
):
    original = _nondefault_feedback(allow_network=False)
    path = Path("artifacts/test-scratch") / f"section-reset-{uuid4().hex}.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    request.addfinalizer(lambda: path.unlink(missing_ok=True))
    monkeypatch.setattr("utterleaf.config.config_path", lambda: path)
    save_config(original)
    saved = path.read_bytes()
    app = app_factory(load_config())
    answers = iter((True, True))
    monkeypatch.setattr(
        "utterleaf.settings_ui.messagebox.askyesno",
        lambda *_args, **_kwargs: next(answers),
    )
    app.vars["hotkey"].set("f8")
    app.reset_recording_feedback()
    assert _feedback(app._snapshot()) == _feedback(Config().__dict__)
    app.close()
    assert app.closed
    assert path.read_bytes() == saved

    reopened = app_factory(load_config())
    assert _feedback(reopened._snapshot()) == _feedback(original.__dict__)
    assert reopened.vars["hotkey"].get() == original.hotkey
    assert reopened.vars["allow_network"].get() is False


@pytest.mark.parametrize("scale", [1.0, 1.5, 2.0])
def test_reset_button_compact_wide_roundtrip_and_native_keyboard(
    tk_root, monkeypatch, scale
):
    monkeypatch.setattr("utterleaf.settings_ui.startup_enabled", lambda: False)
    monkeypatch.setattr(
        "utterleaf.settings_ui.dictionary_text", lambda: "utter leaf = Utterleaf"
    )
    monkeypatch.setattr(
        "utterleaf.model_setup.inspect_model",
        lambda name, backend: ModelAvailability(name, backend, "missing", None),
    )
    questions = _confirm(monkeypatch)
    baseline_scale = float(tk_root.tk.call("tk", "scaling"))
    root = tk.Toplevel(tk_root)
    root.tk.call("tk", "scaling", baseline_scale * scale)
    app = SettingsWindow(root, _nondefault_feedback(), background=False)
    try:
        app.navigate("Dictation")
        for geometry in ("760x560", "960x780", "760x560"):
            root.geometry(geometry)
            root.update()
            app.feedback_reset_button.focus_force()
            app.feedback_reset_button.event_generate("<FocusIn>")
            root.update()
            assert root.focus_get() == app.feedback_reset_button
            assert app.feedback_reset_button.winfo_ismapped()
            top = app.canvas.winfo_rooty()
            bottom = top + app.canvas.winfo_height()
            assert app.feedback_reset_button.winfo_rooty() >= top
            assert (
                app.feedback_reset_button.winfo_rooty()
                + app.feedback_reset_button.winfo_height()
                <= bottom
            )
            assert (
                app.feedback_reset_button.winfo_rootx()
                + app.feedback_reset_button.winfo_width()
                <= app.canvas.winfo_rootx() + app.canvas.winfo_width()
            )
        app.feedback_reset_button.event_generate("<KeyPress-space>")
        app.feedback_reset_button.event_generate("<KeyRelease-space>")
        root.update()
        assert len(questions) == 1
        assert _feedback(app._snapshot()) == _feedback(Config().__dict__)
        assert root.focus_get() == app.feedback_reset_button
    finally:
        app.closed = True
        root.after_cancel(app.poll_id)
        if app._page_reset is not None:
            root.after_cancel(app._page_reset)
        root.destroy()
        tk_root.tk.call("tk", "scaling", baseline_scale)
