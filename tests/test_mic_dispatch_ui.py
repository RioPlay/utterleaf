"""Settings check dispatch recovery with held real workers and no external I/O."""

import queue
import threading
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace

import numpy as np
import pytest

from test_settings_ui import tk_root, window
from utterleaf.audio import microphone_error_hint
from utterleaf.config import Config
from utterleaf.model_setup import ModelAvailability
from utterleaf.settings import SYSTEM_DEFAULT
from utterleaf.settings_ui import SettingsWindow


PRIVATE = "private-dispatch-sentinel C:/private-account/driver"
ACTIONS = ("refresh_mics", "test_mic", "refresh_connection")
COPY = {
    "refresh_mics": "Microphone refresh could not start. The device list was not checked. Select Refresh to retry.",
    "test_mic": "Microphone check could not start. This check recorded no audio. Select Test to retry.",
    "refresh_connection": "App status check could not start · Refresh status to retry",
}


def _blocked(*_args, **_kwargs):
    pytest.fail("Unexpected external operation in a Settings dispatch test")


@pytest.fixture(autouse=True)
def boundaries(monkeypatch):
    details = []
    monkeypatch.setattr("utterleaf.settings_ui.startup_enabled", lambda: False)
    monkeypatch.setattr("utterleaf.settings_ui.dictionary_text", lambda: "utter leaf = Utterleaf")
    monkeypatch.setattr("utterleaf.model_setup.inspect_model",
                        lambda name, backend: ModelAvailability(name, backend, "missing", None))
    for target in (
        "utterleaf.settings_ui.load", "utterleaf.settings.apply_form", "utterleaf.settings_ui.apply_form",
        "utterleaf.config.load", "utterleaf.config.save", "utterleaf.polish.save_dictionary",
        "utterleaf.settings.save", "utterleaf.settings.save_dictionary", "utterleaf.settings.set_startup",
        "utterleaf.audio.list_input_names", "utterleaf.audio.Recorder", "sounddevice.query_devices",
        "sounddevice.InputStream", "utterleaf.ipc.send", "utterleaf.model_setup.run_download",
        "socket.socket", "socket.create_connection", "tkinter.Misc.clipboard_get",
        "tkinter.Misc.clipboard_clear", "tkinter.Misc.clipboard_append",
        "utterleaf.settings_ui.messagebox.showerror", "utterleaf.settings_ui.messagebox.askyesno",
    ):
        monkeypatch.setattr(target, _blocked)
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.showinfo",
                        lambda title, message, **kw: details.append((title, message, kw)))
    return details


@pytest.fixture
def dispatch(monkeypatch):
    state = SimpleNamespace(fail=True, attempts=[], workers=[], error=RuntimeError(PRIVATE))

    def start(thread):
        state.attempts.append(thread)
        if state.fail:
            raise state.error
        state.workers.append(thread._target)

    monkeypatch.setattr(threading.Thread, "start", start)
    return state


def _button(app, action):
    return getattr(app, {"refresh_mics": "refresh_button", "test_mic": "mic_button",
                         "refresh_connection": "connection_button"}[action])


def _message(app, action):
    return (app.connection if action == "refresh_connection" else app.mic_message).get()


def _idle(app):
    assert not app.refreshing_mics and not app.checking_mic and not app.checking_connection
    for button in (app.refresh_button, app.mic_button, app.connection_button):
        assert not button.instate(["disabled"])
    assert app.mic_button.cget("text") == "Test"
    assert app.mic_box.instate(["readonly", "!disabled"])


def _draft(app, selection="Synthetic selected input"):
    app.vars["hotkey"].set("f8")
    app.vars["allow_network"].set(False)
    app.vars["restore_clipboard"].set(False)
    app.vars["microphone"].set(selection)
    app.mic_box.configure(values=(SYSTEM_DEFAULT, "Synthetic selected input", "Synthetic other input"))
    return app._snapshot()


def _finish(app, dispatch, *, deliver=True):
    assert len(dispatch.workers) == 1
    dispatch.workers.pop()()
    records = []
    while True:
        try:
            callback, value = app.events.get_nowait()
        except queue.Empty:
            break
        records.append((callback, value))
        if deliver:
            callback(value)
    assert records
    return records


def _fake_action(app, monkeypatch, action, *, error=None):
    """Run the real action body against one explicit synthetic boundary."""
    calls = []
    if action == "refresh_mics":
        def names():
            calls.append("enumerate")
            if error:
                raise error
            return ["Synthetic selected input", "Synthetic other input"]

        monkeypatch.setattr("utterleaf.audio.list_input_names", names)
    elif action == "refresh_connection":
        def status(command, *, exact_reply=False):
            assert exact_reply is True
            calls.append(command)
            if error:
                raise error
            return "status-v2:idle:unconfirmed"

        monkeypatch.setattr("utterleaf.ipc.send", status)
    else:
        class Probe:
            def __init__(self, *, device):
                calls.append(("recorder", device))

            def start(self):
                calls.append("start")
                if error:
                    raise error

            def capture_error(self):
                return None

            def snapshot(self, **_kwargs):
                calls.append("snapshot")
                return np.array([0.1], dtype=np.float32)

            def close(self):
                calls.append("close")

        waits = iter((False, True))
        monkeypatch.setattr(app.mic_stop, "wait", lambda _duration: next(waits))
        monkeypatch.setattr("utterleaf.audio.Recorder", Probe)
    return calls


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("selection", [SYSTEM_DEFAULT, "Synthetic selected input"])
def test_dispatch_failure_restores_controls_drafts_focus_and_explicit_retry(
        window, monkeypatch, dispatch, boundaries, action, selection):
    window.root.deiconify()
    snapshot = _draft(window, selection)
    baseline = dict(window.baseline)
    choices = window.mic_box.cget("values")
    button = _button(window, action)
    button.focus_force()
    window.root.update()
    assert button.winfo_ismapped()
    getattr(window, action)()
    window.root.update()
    _idle(window)
    assert _message(window, action) == COPY[action]
    assert PRIVATE not in _message(window, action)
    assert window._snapshot() == snapshot and window.baseline == baseline
    assert window.mic_box.cget("values") == choices
    assert window.root.focus_get() == button
    assert window.pages["Dictation"].winfo_ismapped()
    assert window.events.empty() and dispatch.workers == []
    assert len(dispatch.attempts) == 1 and boundaries == []
    if action != "refresh_connection":
        assert PRIVATE in window.error_details[window.mic_details_button]
        window.mic_details_button.invoke()
        assert len(boundaries) == 1 and PRIVATE in boundaries[0][1]
        assert boundaries[0][2]["parent"] == window.root
    else:
        assert window.error_details[window.mic_details_button] == ""

    dispatch.fail = False
    calls = _fake_action(window, monkeypatch, action)
    getattr(window, action)()
    assert calls == [] and len(dispatch.workers) == 1 and len(dispatch.attempts) == 2
    if action != "refresh_connection":
        assert window.error_details[window.mic_details_button] == ""
        assert not window.mic_details_button.winfo_manager()
    if action == "test_mic":
        window.refresh_mics()  # A check keeps refresh blocked; Test remains Stop.
        assert window.mic_button.cget("text") == "Stop"
    else:
        getattr(window, action)()
        if action == "refresh_mics":
            window.test_mic()
    assert len(dispatch.workers) == 1 and len(dispatch.attempts) == 2
    _finish(window, dispatch)
    _idle(window)
    assert window._snapshot() == snapshot and window.baseline == baseline
    if action == "test_mic":
        assert calls == [("recorder", "" if selection == SYSTEM_DEFAULT else selection),
                         "start", "snapshot", "close"]
        assert "Microphone check passed; speech model not tested" in window.mic_message.get()
    elif action == "refresh_mics":
        assert calls == ["enumerate"] and "Devices refreshed" in window.mic_message.get()
    else:
        assert calls == ["status-detail"]
        assert window.connection.get() == ("Idle · app is running\n"
                                           "Loaded model for applied settings: not confirmed.")
    window.root.update()
    assert len(dispatch.attempts) == 2  # Completion does not schedule another check.


def test_constructor_survives_both_initial_dispatch_failures(tk_root, dispatch, boundaries):
    root = tk.Toplevel(tk_root)
    app = None
    initial_timers = set(root.tk.call("after", "info"))
    try:
        app = SettingsWindow(root, Config(), background=True)
        root.update()
        assert len(dispatch.attempts) == 2 and dispatch.workers == []
        assert app.events.empty() and not app.closed
        assert app.poll_id in root.tk.call("after", "info")
        _idle(app)
        assert app.mic_message.get() == COPY["refresh_mics"]
        assert app.connection.get() == COPY["refresh_connection"]
        assert app._snapshot() == app.baseline
        assert boundaries == []
        app.navigate("Help & diagnostics")
        root.update()
        assert app.pages["Help & diagnostics"].winfo_ismapped()
        app.close()
        assert app.closed and app.mic_stop.is_set()
    finally:
        # Also clean up an incompletely constructed pre-fix window in the red run.
        for timer in set(root.tk.call("after", "info")) - initial_timers:
            root.after_cancel(timer)
        if root.winfo_exists():
            root.destroy()


@pytest.mark.parametrize("action", ACTIONS)
def test_started_result_failure_keeps_existing_recovery_path(
        window, monkeypatch, dispatch, boundaries, action):
    dispatch.fail = False
    snapshot = _draft(window)
    error = OSError(PRIVATE)
    calls = _fake_action(window, monkeypatch, action, error=error)
    getattr(window, action)()
    _finish(window, dispatch)
    _idle(window)
    assert calls and len(dispatch.attempts) == 1
    assert window._snapshot() == snapshot and boundaries == []
    expected = ("Could not refresh microphones. The device list may be out of date. "
                "Check microphone access, then select Refresh to retry." if action == "refresh_mics"
                else "Could not check the app · Refresh status to retry" if action == "refresh_connection"
                else microphone_error_hint(error))
    assert _message(window, action) == expected
    assert PRIVATE not in _message(window, action)


@pytest.mark.parametrize("action", ACTIONS)
def test_closed_completion_and_calls_do_not_touch_destroyed_window(
        window, monkeypatch, dispatch, boundaries, action):
    dispatch.fail = False
    _fake_action(window, monkeypatch, action)
    getattr(window, action)()
    records = _finish(window, dispatch, deliver=False)
    window.close()
    assert window.closed and window.mic_stop.is_set()
    for callback, result in records:
        callback(result)
    for name in ACTIONS:
        getattr(window, name)()
    assert len(dispatch.attempts) == 1 and dispatch.workers == [] and boundaries == []


@pytest.mark.parametrize("change", ["stop", "input"])
def test_retry_keeps_stop_and_input_change_cancellation(window, monkeypatch, dispatch, change):
    window.test_mic()
    _idle(window)
    dispatch.fail = False
    _fake_action(window, monkeypatch, "test_mic")
    window.test_mic()
    records = _finish(window, dispatch, deliver=False)
    if change == "stop":
        window.test_mic()
    else:
        window.vars["microphone"].set("Different synthetic input")
    assert window.mic_stop.is_set()
    for callback, result in records:
        callback(result)
    _idle(window)
    expected = "Microphone check stopped." if change == "stop" else "Input changed. Select Test to check it; Save to apply."
    assert window.mic_message.get() == expected
    assert float(window.meter.cget("value")) == 0
    assert window.error_details[window.mic_details_button] == ""
    assert len(dispatch.attempts) == 2


@pytest.mark.parametrize("action", ["refresh_mics", "test_mic"])
def test_dispatch_details_are_bounded_and_clear_on_input_change(window, dispatch, boundaries, action):
    dispatch.error = RuntimeError(PRIVATE + "\x00\x1b\u202e" + "x" * 4000)
    getattr(window, action)()
    assert boundaries == [] and _message(window, action) == COPY[action]
    window.mic_details_button.invoke()
    details = boundaries[0][1]
    assert PRIVATE in details and len(details) < 2200 and "Details shortened" in details
    assert not any(character in details for character in "\x00\x1b\u202e")
    window.vars["microphone"].set("Another synthetic input")
    assert window.error_details[window.mic_details_button] == ""
    assert not window.mic_details_button.winfo_manager()


def _visible(widget, viewport):
    assert widget.winfo_ismapped()
    assert widget.winfo_width() >= widget.winfo_reqwidth()
    assert widget.winfo_height() >= widget.winfo_reqheight()
    x, y = widget.winfo_rootx() - viewport.winfo_rootx(), widget.winfo_rooty() - viewport.winfo_rooty()
    assert 0 <= x and 0 <= y
    assert x + widget.winfo_width() <= viewport.winfo_width()
    assert y + widget.winfo_height() <= viewport.winfo_height()


def _traverse_back(root, widget):
    """A new native focus event reveals the target after a layout reflow."""
    widget.focus_force()
    root.update()
    widget.event_generate("<Shift-Tab>")
    root.update()
    previous = root.focus_get()
    assert previous is not None and previous is not widget
    previous.event_generate("<Tab>")
    root.update()
    assert root.focus_get() == widget


def _read_status_with_page_keys(app, label, button):
    """Long-page copy may span views; keyboard views must cover every line."""
    button.event_generate("<Home>")
    app.root.update()
    height = label.winfo_height()
    assert height >= label.winfo_reqheight()
    font = label.cget("font") or ttk.Style(app.root).lookup(label.cget("style") or "TLabel", "font")
    line_height = int(label.tk.call("font", "metrics", font or "TkDefaultFont", "-linespace"))
    intervals = []
    for key in (None, "<Next>"):
        if key:
            button.event_generate(key)
            app.root.update()
        assert app.root.focus_get() == button
        x = label.winfo_rootx() - app.canvas.winfo_rootx()
        y = label.winfo_rooty() - app.canvas.winfo_rooty()
        assert 0 <= x and x + label.winfo_width() <= app.canvas.winfo_width()
        start, end = max(0, -y), min(height, app.canvas.winfo_height() - y)
        if end > start:
            intervals.append((start, end))
    covered = 0
    for start, end in sorted(intervals):
        assert start <= covered, "Keyboard scrolling left part of the recovery text unreadable"
        if covered and end > covered:
            assert covered - start >= line_height, "Adjacent views must overlap by a full text line"
        covered = max(covered, end)
    assert covered == height
    _traverse_back(app.root, button)
    _visible(button, app.canvas)
    assert not button.instate(["disabled"])


@pytest.mark.parametrize("scale", [1.0, 1.5, 2.0])
@pytest.mark.parametrize("action", ACTIONS)
def test_dispatch_recovery_compact_resize_keyboard_and_pointer(
        tk_root, monkeypatch, dispatch, boundaries, scale, action):
    scaling = float(tk_root.tk.call("tk", "scaling"))
    root = tk.Toplevel(tk_root)
    app = None
    try:
        root.tk.call("tk", "scaling", scaling * scale)
        app = SettingsWindow(root, Config(), background=False)
        root.geometry("760x560")
        snapshot = _draft(app)
        root.update()
        button = _button(app, action)
        button.focus_force()
        root.update()
        getattr(app, action)()
        root.update()
        assert root.focus_get() == button
        variable = app.connection if action == "refresh_connection" else app.mic_message
        label, = [label for label in app._column_labels
                  if str(label.cget("textvariable")) == str(variable)]
        for geometry in ("760x560", "1180x820", "760x560"):
            root.geometry(geometry)
            root.update()
            if action == "refresh_connection":
                _traverse_back(root, button)
                _read_status_with_page_keys(app, label, button)
            else:
                _traverse_back(root, app.mic_details_button)
                _visible(label, app.canvas)
                _visible(app.mic_details_button, app.canvas)
            for control in (app.close_button, app.save_button, *app.nav.values()):
                _visible(control, root if control in (app.close_button, app.save_button) else control.master)
            assert app._snapshot() == snapshot and _message(app, action) == COPY[action]

        if action != "refresh_connection":
            details = app.mic_details_button
            details.focus_force()
            root.update()
            next_control = details.tk_focusNext()
            details.event_generate("<Tab>")
            root.update()
            assert root.focus_get() == next_control
            next_control.event_generate("<Shift-Tab>")
            root.update()
            assert root.focus_get() == details
            details.event_generate("<KeyPress-space>")
            root.update()
            assert len(boundaries) == 1
        # Retry through native pointer activation, with no hardware action run.
        button.focus_force()
        root.update()
        dispatch.fail = False
        x, y = button.winfo_width() // 2, button.winfo_height() // 2
        before = (button.winfo_rootx(), button.winfo_rooty())
        button.event_generate("<Enter>")
        button.event_generate("<ButtonPress-1>", x=x, y=y)
        root.update()
        assert (button.winfo_rootx(), button.winfo_rooty()) == before
        button.event_generate("<ButtonRelease-1>", x=x, y=y)
        root.update()
        assert len(dispatch.workers) == 1 and len(dispatch.attempts) == 2
        assert app._snapshot() == snapshot
    finally:
        if app is not None:
            app.closed = True
            root.after_cancel(app.poll_id)
            if app._page_reset is not None:
                root.after_cancel(app._page_reset)
        root.destroy()
        tk_root.tk.call("tk", "scaling", scaling)
