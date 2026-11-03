"""Last-checked applied-model proof: synthetic IPC, real Settings widgets/keys."""
from dataclasses import replace
import threading
from unittest.mock import call, patch

import pytest

import capture_loaded_model as captures
from capture_backup import descendants
from test_capture_auxiliary import working_tk_display
from utterleaf.settings import SettingsSaveError
from utterleaf.settings_ui import SettingsWindow

REAL_SAVE = SettingsWindow.save


@pytest.fixture
def app(working_tk_display):
    with captures.blocked_runtime() as runtime, captures._window(runtime, visible=False) as window:
        yield window, runtime
        assert runtime.violations == runtime.blocked_actions == runtime.ipc_commands == []


def query(reply, *, legacy=None):
    responses = [reply, legacy] if reply == "unknown" else [reply]
    with patch("utterleaf.ipc.send", side_effect=responses) as send:
        message = SettingsWindow._connection_status()
    expected = [call("status-detail", exact_reply=True)]
    if reply == "unknown":
        expected.append(call("status"))
    assert send.call_args_list == expected
    return message


@pytest.mark.parametrize("reply,words", [
    ("status-v2:ready:tiny.en", ("Ready", "Tiny English")),
    ("status-v2:ready:custom", ("Ready", "Custom model")),
    ("status-v2:listening:unconfirmed", ("Listening", "not confirmed")),
    ("status-v2:processing:base", ("Processing", "Base")),
])
def test_versioned_query_is_one_exact_request_with_fixed_loaded_model_copy(app, reply, words):
    window, runtime = app
    snapshot, baseline = window._snapshot(), window.baseline.copy()
    captures.refresh(window, runtime, [reply])
    text = window.connection.get()
    assert all(word in text for word in words)
    assert "Loaded model for applied settings:" in text and "\n" in text
    assert runtime.status_calls == [("status-detail", {"exact_reply": True})]
    assert window._snapshot() == snapshot and window.baseline == baseline


def test_only_exact_old_server_unknown_requests_legacy_status(app):
    window, runtime = app
    captures.refresh(window, runtime, ["unknown", "status-v1:ready"])
    assert runtime.status_calls == [("status-detail", {"exact_reply": True}), ("status", {})]
    text = window.connection.get().lower()
    assert "ready" in text and "unavailable" in text and "version" in text
    assert "tiny" not in text and "custom" not in text


@pytest.mark.parametrize("reply", [None, "restart-required", "", " unknown", "unknown ",
    "status-v1:ready", "status-v2:ready:unconfirmed",
    "status-v2:ready:/synthetic/private/model.bin", "status-v2:ready:tiny.en\n"])
def test_transport_invalid_and_nonexact_payloads_do_not_fallback_or_echo_private_text(reply):
    text = query(reply)
    assert "Tiny English" not in text and "Custom model" not in text
    assert "/synthetic/private" not in text and "status-v" not in text
    assert text


def test_refresh_clears_previous_claim_while_pending_and_worker_failure_allows_retry(app, monkeypatch):
    window, runtime = app
    captures.refresh(window, runtime, ["status-v2:ready:tiny.en"])
    callbacks = []
    monkeypatch.setattr(window, "_worker", lambda action, done: callbacks.append((action, done)))
    captures.REAL_REFRESH(window)
    assert "Tiny English" not in window.connection.get()
    assert window.checking_connection and window.connection_button.instate(["disabled"])
    captures.REAL_REFRESH(window)
    assert len(callbacks) == 1
    callbacks[0][1](RuntimeError(captures.ERROR))
    assert not window.checking_connection
    assert not window.connection_button.instate(["disabled"])
    assert "Tiny English" not in window.connection.get() and captures.ERROR not in window.connection.get()
    captures.REAL_REFRESH(window)
    assert len(callbacks) == 2
    callbacks[1][1](query("status-v2:ready:custom"))
    assert "Custom model" in window.connection.get()


def test_actual_dispatch_failure_clears_loaded_claim_and_retry_is_bounded(app, monkeypatch):
    window, runtime = app
    captures.refresh(window, runtime, ["status-v2:ready:tiny.en"])
    calls = len(runtime.status_calls)
    with patch.object(threading.Thread, "start", side_effect=RuntimeError(captures.ERROR)):
        captures.REAL_REFRESH(window)
    assert not window.checking_connection
    assert not window.connection_button.instate(["disabled"])
    assert "could not start" in window.connection.get()
    assert "Tiny English" not in window.connection.get() and "/synthetic/private" not in window.connection.get()
    assert len(runtime.status_calls) == calls
    captures.refresh(window, runtime, ["status-v2:ready:custom"])
    assert "Custom model" in window.connection.get()


def test_duplicate_and_stale_callbacks_cannot_overwrite_or_unlock_newer_check(app, monkeypatch):
    window, _runtime = app
    callbacks = []
    monkeypatch.setattr(window, "_worker", lambda action, done: callbacks.append(done))
    first = query("status-v2:ready:tiny.en")
    second = query("status-v2:ready:custom")
    captures.REAL_REFRESH(window)
    callbacks[0](first)
    callbacks[0](second)
    assert window.connection.get() == first
    captures.REAL_REFRESH(window)
    checking = window.connection.get()
    callbacks[0](first)
    assert window.checking_connection and window.connection.get() == checking
    assert window.connection_button.instate(["disabled"])
    callbacks[1](second)
    assert not window.checking_connection and window.connection.get() == second


@pytest.mark.parametrize("destroy_only", [False, True])
def test_closed_or_destroyed_window_ignores_late_result(app, monkeypatch, destroy_only):
    window, _runtime = app
    callbacks = []
    monkeypatch.setattr(window, "_worker", lambda action, done: callbacks.append(done))
    captures.REAL_REFRESH(window)
    if destroy_only:
        # Isolate the deliberately destroyed-root callback from unrelated Tk
        # timers; these otherwise fire into the next test's interpreter loop.
        window.root.after_cancel(window.poll_id)
        if window._page_reset is not None:
            window.root.after_cancel(window._page_reset)
            window._page_reset = None
        window.root.destroy()
    else:
        window.close()
    callbacks[0](query("status-v2:ready:tiny.en"))
    callbacks[0](RuntimeError(captures.ERROR))


@pytest.mark.parametrize("partial", [False, True])
def test_unsaved_choices_and_save_outcomes_do_not_infer_different_runtime_model(app, partial):
    window, runtime = app
    captures.refresh(window, runtime, ["status-v2:ready:tiny.en"])
    proof = window.connection.get()
    window.vars["model"].set("base")
    window.vars["device"].set("npu")
    window.vars["allow_network"].set(False)
    snapshot = window._snapshot()
    assert window.connection.get() == proof

    def apply(cfg, **values):
        if partial:
            raise SettingsSaveError(("dictation settings",), "vocabulary", ("start at login",), OSError(captures.ERROR))
        return replace(cfg, model=values["model"], device=values["device"], allow_network=False)

    with patch("utterleaf.settings_ui.apply_form", side_effect=apply), \
            patch("utterleaf.ipc.send", return_value="ok") as send:
        runtime.allow_worker = True
        try:
            REAL_SAVE(window)
        finally:
            runtime.allow_worker = False
        assert len(runtime.workers) == 1
        runtime.workers.pop()()
        callback, value = window.events.get_nowait()
        callback(value)
    assert send.call_args_list == [call("reload")]
    assert window.connection.get() == proof and window._snapshot() == snapshot
    assert len(runtime.status_calls) == 1
    assert not window.saving


def test_page_navigation_and_draft_edits_do_not_poll_runtime(app):
    window, runtime = app
    captures.refresh(window, runtime, ["status-v2:ready:tiny.en"])
    proof = window.connection.get()
    for page in window.pages:
        window.show_page(page)
        window.vars["beep"].set(not window.vars["beep"].get())
        window.root.update()
    assert window.connection.get() == proof
    assert runtime.status_calls == [("status-detail", {"exact_reply": True})]


def visible(widget, viewport):
    result = captures.bounds(widget, widget.winfo_toplevel(), clip=viewport)
    assert result["mapped"] and result["fits_viewport"]
    assert result["natural_width"] and result["natural_height"]


def read_all_status_with_keys(window, label, button):
    """Prove text coverage with native page keys; do not manually place the canvas."""
    button.event_generate("<Home>")
    window.root.update()
    height = label.winfo_height()
    assert height >= label.winfo_reqheight()
    intervals = []
    last = None
    for _ in range(20):
        assert window.root.focus_get() is button
        x = label.winfo_rootx() - window.canvas.winfo_rootx()
        y = label.winfo_rooty() - window.canvas.winfo_rooty()
        assert x >= 0 and x + label.winfo_width() <= window.canvas.winfo_width()
        first, end = max(0, -y), min(height, window.canvas.winfo_height() - y)
        if end > first:
            intervals.append((first, end))
        current = window.canvas.yview()
        if current == last or (intervals and intervals[-1][1] == height):
            break
        last = current
        button.event_generate("<Next>")
        window.root.update()
    covered = 0
    for first, end in sorted(intervals):
        assert first <= covered, "Page keys skipped part of the last-checked model message"
        covered = max(covered, end)
    assert covered == height


@pytest.mark.parametrize("scale", [1.0, 1.5, 2.0])
def test_loaded_status_native_keyboard_resize_and_help_copy(working_tk_display, scale):
    with captures.blocked_runtime() as runtime, captures._window(runtime, visible=False, text_scale=scale) as window:
        window.root.deiconify()
        window.root.geometry("760x560")
        window.root.update()
        captures.refresh(window, runtime, ["status-v2:ready:tiny.en"])
        snapshot = window._snapshot()
        button = captures.landing_refresh(window)
        for geometry in ("760x560", "1600x900", "760x560"):
            window.root.geometry(geometry)
            window.root.update()
            wide_realized = (window.root.winfo_width() >= 1500
                             and window.root.winfo_height() >= 850)
            for variable, action in ((window.connection, button), (window.model_summary, window.model_manage_button)):
                detail = next(widget for widget in descendants(window.pages["Dictation"])
                              if "textvariable" in widget.keys() and str(widget.cget("textvariable")) == str(variable))
                words = detail.master
                if geometry == "760x560" and scale >= 1.5:
                    assert action.winfo_rooty() >= words.winfo_rooty() + words.winfo_height()
                    assert words.winfo_width() == words.master.winfo_width()
                    assert detail.winfo_width() >= words.winfo_width() - 4
                elif geometry == "1600x900" and wide_realized:
                    assert action.winfo_rootx() >= words.winfo_rootx() + words.winfo_width()
                    assert action.winfo_rooty() < words.winfo_rooty() + words.winfo_height()
            button.focus_force()
            window.root.update()
            button.event_generate("<Shift-Tab>")
            window.root.update()
            previous = window.root.focus_get()
            assert previous is not None and previous is not button
            previous.event_generate("<Tab>")
            window.root.update()
            assert window.root.focus_get() is button
            visible(button, window.canvas)
            label = captures.message_label(window, "refresh_connection")
            read_all_status_with_keys(window, label, button)
            for control in (window.save_button, window.close_button, *window.nav.values()):
                visible(control, window.root if control in (window.save_button, window.close_button) else control.master)
            assert window._snapshot() == snapshot
        window.show_page("Help & diagnostics")
        window.root.update()
        labels = [widget for widget in descendants(window.pages["Help & diagnostics"])
                  if "textvariable" in widget.keys() and str(widget.cget("textvariable")) == str(window.connection)]
        assert len(labels) == 1 and "Tiny English" in window.connection.get()
        window.reset_button.focus_force()
        window.root.update()
        read_all_status_with_keys(window, labels[0], window.reset_button)
        window.reset_button.event_generate("<Shift-Tab>")
        window.root.update()
        previous = window.root.focus_get()
        assert previous is not None and previous is not window.reset_button
        previous.event_generate("<Tab>")
        window.root.update()
        assert window.root.focus_get() is window.reset_button
        visible(window.reset_button, window.canvas)
        assert window._snapshot() == snapshot
        assert runtime.status_calls == [("status-detail", {"exact_reply": True})]
