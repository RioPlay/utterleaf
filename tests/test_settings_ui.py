"""Exercise real Tk widgets without hardware, network, or personal config writes."""
import gc
import time
import tkinter as tk
from tkinter import ttk
import pytest

from utterleaf.config import Config
from utterleaf.host import is_wayland
from utterleaf.settings_ui import SettingsWindow, _service_close_request


@pytest.fixture(scope="module")
def tk_root():
    failure = None
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        failure = str(exc)
    if failure is not None:
        gc.collect()
        pytest.skip(f"Tk needs a working display: {failure}")
    root.withdraw()
    yield root
    root.destroy()
    del root
    gc.collect()


@pytest.fixture
def window(monkeypatch, tk_root):
    monkeypatch.setattr("utterleaf.settings_ui.startup_enabled", lambda: False)
    monkeypatch.setattr("utterleaf.settings_ui.dictionary_text", lambda: "utter leaf = Utterleaf")
    root = tk.Toplevel(tk_root)
    root.withdraw()
    app = SettingsWindow(root, Config(), background=False)
    yield app
    if not app.closed:
        app.closed = True
        root.after_cancel(app.poll_id)
        if app._page_reset is not None:
            root.after_cancel(app._page_reset)
        root.destroy()


def test_companion_close_request_waits_for_inflight_save():
    import threading
    from types import SimpleNamespace

    request = threading.Event()
    request.set()
    messages = []
    calls = []
    window = SimpleNamespace(
        saving=True,
        closed=False,
        status=SimpleNamespace(set=messages.append),
    )

    def close():
        calls.append("close")
        window.closed = True

    window.close = close
    assert not _service_close_request(window, request)
    assert request.is_set() and calls == []
    assert messages == ["Finishing your save…"]

    window.saving = False
    assert _service_close_request(window, request)
    assert not request.is_set() and calls == ["close"]


def test_pages_preserve_edits_and_preview(window):
    window.vars["hotkey"].set("f8")
    for page in window.pages:
        window.show_page(page)
        assert window.pages[page].grid_info()
        assert sum(bool(frame.grid_info()) for frame in window.pages.values()) == 1
    assert window.vars["hotkey"].get() == "f8"
    assert str(window.save_button.cget("state")) == "normal"
    window.preview()
    assert "Utterleaf" in window.preview_result.get()
    assert "um" not in window.preview_result.get().lower()


@pytest.mark.parametrize("interrupted", [False, True])
def test_microphone_check_cannot_report_ready_after_stream_loss(window, monkeypatch, interrupted):
    import numpy as np
    from utterleaf import audio
    probes = []
    class Probe:
        def __init__(self, **kwargs):
            self.checks = 0
            self.closed = False
            probes.append(self)
        def start(self):
            pass
        def capture_error(self):
            self.checks += 1
            return "Stream stopped" if interrupted and self.checks > 1 else None
        def snapshot(self, **kwargs):
            return np.ones(160, dtype=np.float32) * .1
        def close(self):
            self.closed = True
    def run_worker(action, done):
        try:
            result = action()
        except Exception as exc:
            result = exc
        while not window.events.empty():
            callback, value = window.events.get_nowait()
            callback(value)
        done(result)
    monkeypatch.setattr(audio, "Recorder", Probe)
    monkeypatch.setattr(window.mic_stop, "wait", lambda duration: False)
    monkeypatch.setattr(window, "_worker", run_worker)
    window.test_mic()
    assert probes[0].closed
    if interrupted:
        assert "interrupted" in window.mic_message.get().lower()
        assert "ready" not in window.mic_message.get().lower()
        assert probes[0].checks == 2
    else:
        assert "Microphone check passed; speech model not tested" in window.mic_message.get()
        assert "ready" not in window.mic_message.get().lower()
    assert window.mic_button.cget("text") == "Test"


def test_model_status_updates_without_saving_or_downloading(window, tmp_path, monkeypatch):
    monkeypatch.setattr("utterleaf.models.models_dir", lambda: tmp_path)
    monkeypatch.setattr("utterleaf.model_setup.run_download", lambda *a, **k: pytest.fail("Status must not download"))
    window.vars["model"].set("tiny")
    window.vars["language"].set("en")
    window.vars["device"].set("cpu")
    assert "Missing" in window.model_status.get()
    assert "Tiny English" in window.model_status.get()
    folder = tmp_path / "faster-whisper-tiny.en"
    folder.mkdir()
    (folder / "model.bin").write_bytes(b"weights")
    window.refresh_model_status()
    assert "Incomplete" in window.model_status.get()
    assert not (tmp_path / "config.toml").exists()


def test_download_decline_preserves_offline_choice(window, tmp_path, monkeypatch):
    monkeypatch.setattr("utterleaf.models.models_dir", lambda: tmp_path)
    window.vars["allow_network"].set(False)
    window.vars["model"].set("tiny")
    window.vars["device"].set("cpu")
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.askyesno", lambda *a, **k: False)
    monkeypatch.setattr("utterleaf.model_setup.run_download", lambda *a, **k: pytest.fail("Decline must not download"))
    window.download_model()
    assert window.vars["allow_network"].get() is False
    assert not window.model_downloading


def test_download_is_scoped_and_completion_does_not_replace_new_selection(window, tmp_path, monkeypatch):
    monkeypatch.setattr("utterleaf.models.models_dir", lambda: tmp_path)
    window.vars["allow_network"].set(False)
    window.vars["model"].set("tiny")
    window.vars["language"].set("en")
    window.vars["device"].set("cpu")
    calls = []
    pending = []
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.askyesno", lambda *a, **k: True)
    monkeypatch.setattr("utterleaf.model_setup.run_download", lambda *a, **k: calls.append(a))
    def worker(action, done, *, daemon=True):
        assert daemon is False  # Closing Tk must still allow cancellation to reap the child.
        pending.append((action, done))
    monkeypatch.setattr(window, "_worker", worker)
    window.download_model()
    window.download_model()
    assert len(pending) == 1
    window.vars["model"].set("base")
    pending[0][0]()
    pending[0][1](None)
    assert calls == [("tiny.en", "ctranslate2")]
    assert "Base English" in window.model_status.get()
    assert "Missing" in window.model_status.get()
    assert window.vars["allow_network"].get() is False


def test_mascots_are_loaded_from_package_and_fit_compact_header(window):
    assert set(window.mascots) == {"Dictation", "Vocabulary", "Voice commands", "Help & diagnostics"}
    window.root.deiconify()
    window.root.geometry("760x560")
    for name in window.mascots:
        window.show_page(name)
        window.root.update()
        label = window.mascot_labels[name]
        assert label.winfo_width() >= 80
        assert label.winfo_rootx() >= window.canvas.winfo_rootx()
        assert label.winfo_rootx() + label.winfo_width() <= window.canvas.winfo_rootx() + window.canvas.winfo_width()


def test_tray_only_disables_caption_control_without_losing_preference(window):
    assert not window.vars["indicator"].get()
    assert window.preview_toggle.instate(["disabled"])
    window.vars["live_preview"].set(True)
    window.vars["indicator"].set(True)
    assert not window.preview_toggle.instate(["disabled"])
    window.vars["indicator"].set(False)
    assert window.preview_toggle.instate(["disabled"])
    assert window.vars["live_preview"].get()


def test_appearance_guide_shows_all_assets_and_reuses_window(window):
    from utterleaf import brand
    window.show_appearance()
    guide = window.appearance_guide
    window.show_appearance()
    assert window.appearance_guide is guide
    assert len(guide.tabs.tabs()) == 5
    for state in brand.STATE_COLORS:
        assert state in guide.entries
        assert f"cutout-{state}" in guide.entries
    for expression in brand.MASCOT_LABELS:
        assert f"mascot-{expression}" in guide.entries
    for variant in brand.MARK_COLORS:
        assert f"mark-{variant}" in guide.entries
    assert "wordmark" in guide.entries
    guide.close()


@pytest.mark.parametrize("result,expression", [(0.1, "success"), (0.0, "thinking"), (RuntimeError("unavailable"), "error")])
def test_microphone_check_mascot_follows_result(window, monkeypatch, result, expression):
    callbacks, expressions = [], []
    monkeypatch.setattr(window, "_worker", lambda action, done: callbacks.append(done))
    monkeypatch.setattr(window, "_set_mascot", lambda page, state: expressions.append(state))
    window.test_mic()
    assert expressions == ["thinking"]
    assert window.mic_message.get() == "Opening your microphone…"
    window._mic_check_listening()
    assert expressions[-1] == "listening"
    callbacks[0](result)
    assert expressions[-1] == expression
    assert str(window.mic_button.cget("text")) == "Test"


def test_refresh_microphones_preserves_missing_selection_and_explains_recovery(window, monkeypatch):
    callbacks = []
    monkeypatch.setattr(window, "_worker", lambda action, done: callbacks.append(done))
    window.vars["microphone"].set("Headset Mic")
    window.refresh_mics()
    callbacks.pop()(["Laptop Mic"])
    assert window.vars["microphone"].get() == "Headset Mic"
    assert "unavailable" in window.mic_message.get()
    window.refresh_mics()
    callbacks.pop()(["Headset Mic", "Laptop Mic"])
    assert "Devices refreshed" in window.mic_message.get()
    assert window.vars["microphone"].get() == "Headset Mic"


def test_refresh_failure_is_recoverable_and_cannot_overlap_a_check(window, monkeypatch):
    callbacks, dialogs = [], []
    monkeypatch.setattr(window, "_worker", lambda action, done: callbacks.append(done))
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.showinfo", lambda *a, **k: dialogs.append(a))
    window.vars["microphone"].set("My input")
    window.mic_box.configure(values=("System default", "My input"))
    choices, snapshot = window.mic_box.cget("values"), window._snapshot()
    window.refresh_mics()
    window.refresh_mics()
    window.test_mic()
    assert len(callbacks) == 1
    assert window.refreshing_mics
    assert window.mic_button.instate(["disabled"])
    callbacks.pop()(RuntimeError("private backend enumeration failure"))
    assert not window.refreshing_mics
    assert window.mic_button.instate(["!disabled"])
    assert window.refresh_button.instate(["!disabled"])
    assert window.mic_box.cget("values") == choices
    assert window._snapshot() == snapshot
    assert "out of date" in window.mic_message.get()
    assert "private" not in window.mic_message.get()
    assert dialogs == []
    window.mic_details_button.invoke()
    assert "private backend" in dialogs[0][1]
    assert "Review before sharing" in dialogs[0][1]
    window.refresh_mics()
    assert window.mic_details_button.instate(["disabled"])
    assert not window.mic_details_button.winfo_manager()
    # A form change while enumerating must remain in the returned picker.
    window.vars["microphone"].set("Another input")
    callbacks.pop()(["Laptop input"])
    assert "Another input" in window.mic_box.cget("values")
    assert window.vars["microphone"].get() == "Another input"
    assert "unavailable" in window.mic_message.get()


@pytest.mark.parametrize("result", [0.1, RuntimeError("private old-input failure")])
def test_microphone_change_invalidates_old_check_result(window, monkeypatch, result):
    callbacks = []
    monkeypatch.setattr(window, "_worker", lambda action, done: callbacks.append(done))
    window.test_mic()
    assert window.checking_mic
    assert window.mic_box.instate(["disabled"])
    assert window.refresh_button.instate(["disabled"])
    assert window.mic_button.instate(["!disabled"])
    window.refresh_mics()
    assert len(callbacks) == 1
    # Reset or another programmatic form update can change a disabled picker.
    window.vars["microphone"].set("Different microphone")
    assert window.mic_stop.is_set()
    window._mic_check_listening()
    assert "Input changed" in window.mic_message.get()
    window._mic_check_level(80)
    assert float(window.meter.cget("value")) == 0
    callbacks.pop()(result)
    assert not window.checking_mic
    assert window.mic_box.instate(["readonly", "!disabled"])
    assert window.refresh_button.instate(["!disabled"])
    assert window.mic_button.cget("text") == "Test"
    assert "Input changed" in window.mic_message.get()
    assert window.mic_details_button.instate(["disabled"])
    assert float(window.meter.cget("value")) == 0
    window.test_mic()
    callbacks.pop()(0.1)
    assert "Microphone check passed" in window.mic_message.get()
    window.vars["microphone"].set("Third microphone")
    assert "Input changed" in window.mic_message.get()


def test_microphone_error_details_are_explicit_bounded_and_cleared_on_retry(window, monkeypatch):
    callbacks, dialogs = [], []
    monkeypatch.setattr(window, "_worker", lambda action, done: callbacks.append(done))
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.showinfo", lambda *a, **k: dialogs.append(a))
    window.test_mic()
    callbacks.pop()(RuntimeError("private driver failure\x00" + "x" * 4000))
    assert "private" not in window.mic_message.get()
    assert dialogs == []
    window.mic_details_button.invoke()
    assert "private driver failure" in dialogs[0][1]
    assert "\x00" not in dialogs[0][1]
    assert "Details shortened" in dialogs[0][1]
    assert len(dialogs[0][1]) < 2200
    window.test_mic()
    assert not window.error_details[window.mic_details_button]
    assert not window.mic_details_button.winfo_manager()
    # Stop cannot be overwritten by an opening callback queued by the worker.
    window.test_mic()
    window._mic_check_listening()
    assert "Stopping" in window.mic_message.get()
    callbacks.pop()(0.1)
    assert "stopped" in window.mic_message.get()
    assert window.refresh_button.instate(["!disabled"])
    assert window.mic_box.instate(["readonly", "!disabled"])


@pytest.mark.parametrize("code", [-9998, -9997, -9994, -9993])
def test_unsupported_microphone_format_preserves_drafts_and_retry(window, monkeypatch, code):
    from sounddevice import PortAudioError

    callbacks, dialogs = [], []
    monkeypatch.setattr(window, "_worker", lambda action, done: callbacks.append(done))
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.showinfo", lambda *a, **k: dialogs.append(a))
    window.vars["microphone"].set("Selected USB microphone")
    window.vars["hotkey"].set("f8")
    draft, baseline = window._snapshot(), window.baseline
    window.test_mic()
    callbacks.pop()(PortAudioError("private driver format detail", code))

    assert window.mic_message.get() == (
        "This microphone cannot use the requested audio format. "
        "Choose another input in Settings → Dictation, then try again."
    )
    assert window._snapshot() == draft
    assert window.baseline == baseline
    assert not window.checking_mic
    assert window.mic_button.cget("text") == "Test"
    assert window.mic_box.instate(["readonly", "!disabled"])
    assert window.refresh_button.instate(["!disabled"])
    assert window.save_button.instate(["!disabled"])
    assert dialogs == []
    window.mic_details_button.invoke()
    assert "private driver format detail" in dialogs[0][1]
    assert len(callbacks) == 0  # An error must not schedule an automatic retry.

    window.test_mic()
    assert window.error_details[window.mic_details_button] == ""
    assert not window.mic_details_button.winfo_manager()
    callbacks.pop()(0.1)
    assert "Microphone check passed" in window.mic_message.get()
    assert "speech model not tested" in window.mic_message.get()
    assert window._snapshot() == draft
    assert window.baseline == baseline


@pytest.mark.parametrize("action", ["refresh_mics", "test_mic"])
def test_microphone_callbacks_ignore_closed_settings(window, monkeypatch, action):
    callbacks = []
    monkeypatch.setattr(window, "_worker", lambda action, done: callbacks.append(done))
    getattr(window, action)()
    window.close()
    assert window.closed
    callbacks.pop()(RuntimeError("late callback"))
    window._mic_check_listening()
    window._mic_check_level(80)
    window.refresh_mics()
    window.test_mic()
    assert callbacks == []


def test_download_failure_details_preserve_selection_consent_and_retry(window, tmp_path, monkeypatch):
    pending, dialogs, confirmations = [], [], []
    monkeypatch.setattr("utterleaf.models.models_dir", lambda: tmp_path)
    monkeypatch.setattr(window, "_worker", lambda action, done, **kw: pending.append(done))
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.showinfo", lambda *a, **k: dialogs.append(a))
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.askyesno",
                        lambda *a, **k: confirmations.append(a) or True)
    window.vars["model"].set("tiny")
    window.vars["allow_network"].set(False)
    snapshot = window._snapshot()
    window.download_model()
    window.vars["model"].set("base")
    pending.pop()(RuntimeError("private backend download failure"))
    assert not window.model_downloading
    assert "Download of Tiny English did not finish" in window.model_action_status.get()
    assert "private" not in window.model_action_status.get()
    assert "retry" in window.model_action_status.get()
    assert window.vars["model"].get() == "base"
    assert not window.vars["allow_network"].get()
    assert dialogs == []
    window.model_details_button.invoke()
    assert "private backend download failure" in dialogs[0][1]
    window.vars["model"].set("tiny")
    assert window._snapshot() == snapshot
    window.download_model()
    assert len(confirmations) == 2  # Retry is a fresh explicit network decision.
    assert window.model_details_button.instate(["disabled"])
    assert not window.model_details_button.winfo_manager()
    window.cancel_model_download()
    pending.pop()(RuntimeError("cancelled"))
    assert "cancelled" in window.model_action_status.get()
    assert window.model_details_button.instate(["disabled"])
    assert window._snapshot() == snapshot


def test_late_cancel_does_not_relabel_a_completed_download(window, monkeypatch):
    from types import SimpleNamespace
    pending = []
    availability = SimpleNamespace(state="missing")
    monkeypatch.setattr("utterleaf.model_setup.inspect_model", lambda *_: availability)
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.askyesno", lambda *a, **k: True)
    monkeypatch.setattr(window, "_worker", lambda action, done, **kw: pending.append(done))
    window.download_model()
    # The child has succeeded, but Tk has not processed its completion yet.
    availability.state = "installed"
    window.cancel_model_download()
    assert window.model_download_cancel.is_set()
    pending.pop()(None)
    assert "installed" in window.model_action_status.get()
    assert "cancelled" not in window.model_action_status.get()
    assert "Installed" in window.model_status.get()
    assert not window.model_downloading
    assert window.model_details_button.instate(["disabled"])
    result = window.model_action_status.get()
    window.cancel_model_download()
    assert window.model_action_status.get() == result


def test_preview_can_preserve_transcript_without_vocabulary_or_commands(window):
    window.vars["text_cleanup"].set(False)
    window.sample.delete("1.0", "end")
    sample = "um utter leaf, new paragraph, I mean scratch that"
    window.sample.insert("1.0", sample)
    window.preview()
    assert window.preview_result.get() == sample


def test_save_uses_snapshot_and_keeps_later_edits(window, monkeypatch):
    import threading
    def unexpected_error(title, message, **_kwargs):
        pytest.fail(f"Unexpected Settings error dialog: {title}: {message}")
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.showerror", unexpected_error)
    release = threading.Event()
    values = []
    def save(cfg, **fields):
        values.append(fields)
        release.wait(2)
        return cfg
    monkeypatch.setattr("utterleaf.settings_ui.load", Config)
    monkeypatch.setattr("utterleaf.settings_ui.apply_form", save)
    monkeypatch.setattr("utterleaf.ipc.send", lambda _: "ok")
    window.vars["hotkey"].set("f8")
    window.save()
    window.vars["hotkey"].set("right ctrl")
    release.set()
    deadline = time.monotonic() + 3
    while window.saving and time.monotonic() < deadline:
        window.root.update()
        time.sleep(0.02)
    assert not window.saving
    assert values[0]["hotkey"] == "f8"
    assert window.baseline["hotkey"] == "f8"
    assert window.status.get() == "Unsaved changes"


def test_close_preserves_unsaved_work(window, monkeypatch):
    window.vars["hotkey"].set("f8")
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.askyesno", lambda *a, **k: False)
    window.close()
    assert not window.closed


def test_markdown_output_choice_is_previewed_saved_and_reset(window, monkeypatch):
    window.vars["output_format"].set("markdown")
    window.sample.delete("1.0", "end")
    window.sample.insert("1.0", "heading two Project notes")
    window.preview()
    assert window.preview_result.get() == "## Project notes"
    saved = []
    monkeypatch.setattr("utterleaf.settings.save", saved.append)
    monkeypatch.setattr("utterleaf.settings.set_startup", lambda _on: None)
    monkeypatch.setattr("utterleaf.settings.save_dictionary", lambda _names: None)
    monkeypatch.setattr("utterleaf.ipc.send", lambda _command: "ok")
    monkeypatch.setattr(window, "_worker", lambda action, done: done(action()))
    window.save()
    assert saved[-1].output_format == "markdown"
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.askyesno", lambda *a, **k: True)
    window.restore_defaults()
    assert window.vars["output_format"].get() == "prose"


def test_discarded_markdown_choice_reopens_with_last_saved_value(window, monkeypatch):
    saved = []
    monkeypatch.setattr("utterleaf.settings.save", saved.append)
    monkeypatch.setattr("utterleaf.settings.set_startup", lambda _on: None)
    monkeypatch.setattr("utterleaf.settings.save_dictionary", lambda _names: None)
    monkeypatch.setattr("utterleaf.ipc.send", lambda _command: "ok")
    monkeypatch.setattr(window, "_worker", lambda action, done: done(action()))
    window.vars["output_format"].set("markdown")
    window.save()
    window.vars["output_format"].set("prose")
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.askyesno", lambda *a, **k: True)
    window.close()
    reopened = SettingsWindow(tk.Toplevel(window.root.master), saved[-1], background=False)
    try:
        assert reopened.vars["output_format"].get() == "markdown"
    finally:
        reopened.closed = True
        reopened.root.after_cancel(reopened.poll_id)
        reopened.root.destroy()


def test_invalid_output_format_reveals_dictation_control(window, monkeypatch):
    from utterleaf.settings import FormValidationError

    window.root.deiconify()
    window.root.geometry("770x655")
    window.show_page("Vocabulary")
    window.root.update()
    field = window.fields["output_format"]
    focus_requests = []
    monkeypatch.setattr(field, "focus_set", lambda: focus_requests.append(field))
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.showerror", lambda *a, **k: None)
    window._show_invalid_field(FormValidationError("output_format", "Choose prose or Markdown output."))
    window.root.update()
    assert window.pages["Dictation"].grid_info()
    assert not window.pages["Vocabulary"].grid_info()
    assert focus_requests == [field]
    assert field.winfo_ismapped()
    assert field.winfo_rooty() >= window.canvas.winfo_rooty()
    assert field.winfo_rooty() + field.winfo_height() <= (
        window.canvas.winfo_rooty() + window.canvas.winfo_height()
    )


def test_speech_end_preferences_save_discard_reopen_and_reset(window, monkeypatch):
    assert not window.vars["speech_end_enabled"].get()
    assert str(window.speech_end_pause.cget("state")) == "disabled"
    window.vars["speech_end_enabled"].set(True)
    window.vars["speech_end_pause_seconds"].set("1.8")
    window.vars["speech_end_insert"].set(True)
    saved = []
    monkeypatch.setattr("utterleaf.settings.save", saved.append)
    monkeypatch.setattr("utterleaf.settings.set_startup", lambda _on: None)
    monkeypatch.setattr("utterleaf.settings.save_dictionary", lambda _names: None)
    monkeypatch.setattr("utterleaf.ipc.send", lambda _command: "ok")
    monkeypatch.setattr(window, "_worker", lambda action, done: done(action()))
    window.save()
    assert saved[-1].speech_end_enabled is True
    assert saved[-1].speech_end_pause_seconds == 1.8
    assert saved[-1].speech_end_insert is True
    window.vars["speech_end_pause_seconds"].set("2.5")
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.askyesno", lambda *a, **k: True)
    window.close()
    reopened = SettingsWindow(tk.Toplevel(window.root.master), saved[-1], background=False)
    try:
        assert reopened.vars["speech_end_enabled"].get() is True
        assert float(reopened.vars["speech_end_pause_seconds"].get()) == 1.8
        assert reopened.vars["speech_end_insert"].get() is True
        monkeypatch.setattr("utterleaf.settings_ui.messagebox.askyesno", lambda *a, **k: True)
        reopened.restore_defaults()
        assert reopened.vars["speech_end_enabled"].get() is False
        assert float(reopened.vars["speech_end_pause_seconds"].get()) == 1.2
        assert reopened.vars["speech_end_insert"].get() is False
    finally:
        reopened.closed = True
        reopened.root.after_cancel(reopened.poll_id)
        reopened.root.destroy()


def test_restore_defaults_is_staged_and_preserves_vocabulary(window, monkeypatch):
    window.vars["device"].set("gpu")
    window.vars["indicator"].set(True)
    window.vars["start_at_login"].set(True)
    before = window._snapshot()
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.askyesno", lambda *a, **k: False)
    window.restore_defaults()
    assert window._snapshot() == before
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.askyesno", lambda *a, **k: True)
    monkeypatch.setattr("utterleaf.settings.save", lambda _: pytest.fail("Saved before user chose Save"))
    window.restore_defaults()
    assert window.vars["device"].get() == "auto"
    assert not window.vars["indicator"].get()
    assert not window.vars["start_at_login"].get()
    assert window._snapshot()["names"] == before["names"]
    assert window._reset_pending
    assert str(window.save_button.cget("state")) == "normal"


def test_reset_saves_advanced_defaults_and_reloads_app(window, monkeypatch):
    saved, names, startup, commands = [], [], [], []
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.askyesno", lambda *a, **k: True)
    monkeypatch.setattr("utterleaf.settings_ui.load", lambda: pytest.fail("Reset reused broken config"))
    monkeypatch.setattr("utterleaf.settings.save", saved.append)
    monkeypatch.setattr("utterleaf.settings.save_dictionary", names.append)
    monkeypatch.setattr("utterleaf.settings.set_startup", startup.append)
    monkeypatch.setattr("utterleaf.ipc.send", lambda command: commands.append(command) or "ok")
    monkeypatch.setattr(window, "_worker", lambda action, done: done(action()))
    window.cfg = Config(compute_type="float16", max_seconds=1, tray=False)
    window.restore_defaults()
    # Reset must still be dirty when all visible values already matched defaults.
    assert window._reset_pending
    window.save()
    assert saved == [Config(model="small.en")]
    assert names == ["utter leaf = Utterleaf"]
    assert startup == [False]
    assert commands == ["reload"]
    assert not window._reset_pending
    assert str(window.save_button.cget("state")) == "disabled"


def test_cuda_report_can_be_exported_and_failure_retains_previous_report(window, monkeypatch):
    monkeypatch.setattr(window, "_worker", lambda action, done: done("GPU setup steps"))
    window.cuda_setup()
    assert window.report == "GPU setup steps"
    assert str(window.export_button.cget("state")) == "normal"
    monkeypatch.setattr(window, "_worker", lambda action, done: done(RuntimeError("probe failed")))
    window.cuda_setup()
    assert window.report == "GPU setup steps"
    assert window.diagnostic_text.get("1.0", "end-1c") == "GPU setup steps"
    assert "Previous report retained" in window.report_status.get()
    assert "probe failed" not in window.report_status.get()
    assert str(window.export_button.cget("state")) == "normal"


def test_partial_save_reloads_completed_settings_and_keeps_form_for_retry(window, monkeypatch):
    from utterleaf.settings import SettingsSaveError
    def fail(*args, **kwargs):
        raise SettingsSaveError(["dictation settings"], "vocabulary", ["start at login"], OSError("locked"))
    monkeypatch.setattr("utterleaf.settings_ui.load", Config)
    monkeypatch.setattr("utterleaf.settings_ui.apply_form", fail)
    reloads = []
    monkeypatch.setattr("utterleaf.ipc.send", lambda command: reloads.append(command) or "ok")
    errors = []
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.showerror", lambda title, message, **kw: errors.append(message))
    window.vars["hotkey"].set("f8")
    baseline = dict(window.baseline)
    window.save()
    deadline = time.monotonic() + 3
    while window.saving and time.monotonic() < deadline:
        window.root.update()
        time.sleep(.02)
    assert not window.saving
    assert reloads == ["reload"]
    assert "Some changes saved" in window.status.get()
    assert "Saved: dictation settings" in errors[0]
    assert window.baseline == baseline
    assert window.vars["hotkey"].get() == "f8"
    assert str(window.save_button.cget("state")) == "normal"


def test_validation_returns_to_vocabulary_and_selects_bad_line(window, monkeypatch):
    from utterleaf.settings import FormValidationError
    window.names.delete("1.0", "end")
    window.names.insert("1.0", "valid = replacement\nmissing separator")
    window.show_page("Help & diagnostics")
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.showerror", lambda *a, **k: None)
    window._show_invalid_field(FormValidationError("names", "Vocabulary line 2: use spoken = written.", 2))
    assert window.pages["Vocabulary"].grid_info()
    assert window.names.get("sel.first", "sel.last") == "missing separator"
    assert "line 2" in window.status.get()


def test_long_status_keeps_footer_actions_inside_compact_window(window):
    window.root.deiconify()
    window.root.geometry("760x560")
    window.status.set("Some changes could not be saved. Review your vocabulary and settings, then try saving again.")
    window.root.update()
    for button in (window.close_button, window.save_button):
        assert button.winfo_rootx() + button.winfo_width() <= window.root.winfo_rootx() + window.root.winfo_width()
    assert window.footer_status.winfo_rootx() + window.footer_status.winfo_width() < window.close_button.winfo_rootx()


def test_friendly_device_labels_keep_config_values_and_reset_in_sync(window):
    field = window.fields["device"]
    assert field.get() == "Automatic"
    field.set("NVIDIA GPU")
    field.event_generate("<<ComboboxSelected>>")
    assert window._snapshot()["device"] == "gpu"
    window.vars["device"].set("auto")
    assert field.get() == "Automatic"


def test_first_combobox_click_does_not_scroll_or_detach_popup(window):
    window.root.deiconify()
    window.root.geometry("770x655")
    window.show_page("Dictation")
    window.root.update()
    # Wayland intentionally disables the in-app shortcut combobox; exercise
    # popup anchoring with the enabled microphone combobox in that environment.
    box = window.mic_box if is_wayland() else window.hotkey_box
    if is_wayland():
        # Establish visibility through the same focus-reveal path used by the
        # UI, rather than choosing an arbitrary scroll offset for the control.
        box.focus_set()
        window.root.update()
        canvas_top = window.canvas.winfo_rooty()
        canvas_bottom = canvas_top + window.canvas.winfo_height()
        assert box.winfo_rooty() >= canvas_top
        assert box.winfo_rooty() + box.winfo_height() <= canvas_bottom
        initial_scroll = window.canvas.yview()[0]
    else:
        initial_scroll = 0
        assert window.canvas.yview()[0] == pytest.approx(initial_scroll)

    # Aqua Tk synchronously enters Cocoa menu tracking from TkpPostMenu, so
    # Unpost cannot cancel it. Intercept only the final menu `post` command;
    # this preserves Press/Post/AquaPlacePopdown and records requested native
    # placement without entering the untestable physical menu loop.
    popup = box.tk.call("ttk::combobox::PopdownWindow", str(box))
    menu = f"{popup}.menu"
    windowing_system = box.tk.call("tk", "windowingsystem")
    native_post = []
    if windowing_system == "aqua":
        original = f"{menu}.__original__"
        box.tk.call("rename", menu, original)

        def menu_command(*args):
            if args and args[0] == "post":
                native_post.append(tuple(map(int, args[1:3])))
                return ""
            return box.tk.call(original, *args)

        box.tk.createcommand(menu, menu_command)
    try:
        box.event_generate("<Button-1>", x=box.winfo_width() - 5, y=box.winfo_height() // 2)
        window.root.update()
        assert window.canvas.yview()[0] == pytest.approx(initial_scroll)
        if windowing_system == "aqua":
            assert native_post == [(box.winfo_rootx() + 2, box.winfo_rooty() + box.winfo_height() + 2)]
        else:
            popup = box.tk.call("ttk::combobox::PopdownWindow", str(box))
            assert int(box.tk.call("winfo", "rootx", popup)) == box.winfo_rootx()
            assert int(box.tk.call("winfo", "rooty", popup)) == box.winfo_rooty() + box.winfo_height()
            window.root.event_generate("<Escape>")
        window.root.update()
    finally:
        if windowing_system == "aqua":
            box.tk.deletecommand(menu)
            box.tk.call("rename", original, menu)


def test_focus_reveal_handles_above_and_near_bottom_controls(window):
    window.root.deiconify()
    window.root.geometry("770x655")
    window.show_page("Vocabulary")
    window.root.update()
    canvas_top = window.canvas.winfo_rooty()
    canvas_bottom = canvas_top + window.canvas.winfo_height()

    window.canvas.yview_moveto(1)
    window.root.update()
    above = window.names
    assert above.winfo_rooty() < canvas_top
    # Exercise Tk's focus binding without depending on this test process owning
    # the Windows foreground; focus_set() is only a request when it does not.
    above.event_generate("<FocusIn>")
    window.root.update()
    assert above.winfo_rooty() >= canvas_top
    assert above.winfo_rooty() + above.winfo_height() <= canvas_bottom

    window.canvas.yview_moveto(0)
    window.root.update()
    near_bottom = window.sample
    assert near_bottom.winfo_rooty() + near_bottom.winfo_height() > canvas_bottom
    near_bottom.event_generate("<FocusIn>")
    window.root.update()
    assert near_bottom.winfo_rooty() >= canvas_top
    assert near_bottom.winfo_rooty() + near_bottom.winfo_height() <= canvas_bottom


def test_first_button_click_activates_without_focus_scroll(window, monkeypatch):
    window.root.deiconify()
    window.root.geometry("770x655")
    window.show_page("Dictation")
    window.root.update()
    calls = []
    button = window.mic_button
    button.configure(command=lambda: calls.append("mic"))
    # Reveal through the real focus path; its position changes with layout and
    # platform metrics. A fixed scroll fraction can put it above the viewport.
    button.event_generate("<FocusIn>")
    window.root.update()
    assert button.winfo_rooty() >= window.canvas.winfo_rooty()
    initial_scroll = window.canvas.yview()
    button.event_generate("<ButtonPress-1>", x=10, y=10)
    button.event_generate("<ButtonRelease-1>", x=10, y=10)
    window.root.update()
    assert calls == ["mic"]
    assert window.canvas.yview() == pytest.approx(initial_scroll)


def test_vocabulary_explanatory_labels_are_not_clipped_at_compact_size(window):
    window.root.deiconify()
    window.root.geometry("770x655")
    window.show_page("Vocabulary")
    window.root.update()
    labels = []

    def collect(widget):
        for child in widget.winfo_children():
            if isinstance(child, ttk.Label) and child.cget("text") in {
                "Turn off to keep the model transcript unchanged. Vocabulary replacements and spoken commands are also paused. Speech recognition can still make mistakes.",
                "One replacement per line: spoken = written. For example: utter leaf = Utterleaf",
            }:
                labels.append(child)
            collect(child)

    collect(window.pages["Vocabulary"])
    assert len(labels) == 2
    assert all(label.winfo_height() >= label.winfo_reqheight() for label in labels)
    assert window.canvas.yview()[0] == pytest.approx(0)


def test_tab_order_excludes_hidden_pages_and_reaches_close(window):
    window.root.deiconify()
    window.root.update()
    current = window.nav["Dictation"]
    visited = set()
    for _ in range(100):
        current = current.tk_focusNext()
        if str(current) in visited:
            break
        visited.add(str(current))
    assert str(window.close_button) in visited
    assert str(window.mic_button) in visited
    assert str(window.names) not in visited
    assert str(window.fields["model"]) not in visited


def test_reset_preserves_offline_and_clipboard_preferences(window, monkeypatch):
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.askyesno", lambda *a, **k: True)
    window.vars["allow_network"].set(False)
    window.vars["restore_clipboard"].set(False)
    window.vars["device"].set("gpu")
    window.restore_defaults()
    assert not window.vars["allow_network"].get()
    assert not window.vars["restore_clipboard"].get()
    assert window.vars["device"].get() == "auto"


@pytest.mark.parametrize("geometry,scale", [
    ("770x655", 1.0), ("760x560", 1.0),
    ("770x655", 1.5), ("770x655", 2.0),
])
@pytest.mark.parametrize("error_text", [
    "The selected microphone is disconnected. Reconnect it and refresh devices.",
    "This microphone cannot use the requested audio format. "
    "Choose another input in Settings → Dictation, then try again.",
])
def test_dictation_primary_controls_remain_readable_and_focusable(tk_root, monkeypatch, geometry, scale, error_text):
    monkeypatch.setattr("utterleaf.settings_ui.startup_enabled", lambda: False)
    monkeypatch.setattr("utterleaf.settings_ui.dictionary_text", lambda: "utter leaf = Utterleaf")
    baseline = float(tk_root.tk.call("tk", "scaling"))
    root = tk.Toplevel(tk_root)
    root.tk.call("tk", "scaling", baseline * scale)
    app = SettingsWindow(root, Config(), background=False)
    try:
        root.geometry(geometry)
        root.update()
        app._set_error_details(app.mic_details_button, RuntimeError("Synthetic microphone failure"))
        root.update()
        controls = [app.connection_button, app.model_manage_button,
                    app.hotkey_box, app.hold_mode, app.toggle_mode, app.mic_box,
                    app.mic_button, app.refresh_button, app.mic_details_button, app.output_format_control,
                    app.markdown_control, app.speech_end_toggle]
        left = app.canvas.winfo_rootx()
        right = left + app.canvas.winfo_width()
        for control in controls:
            assert control.winfo_rootx() >= left
            assert control.winfo_rootx() + control.winfo_width() <= right
            assert control.winfo_width() >= control.winfo_reqwidth()
            if str(control.cget("state")) == "disabled":
                continue
            control.event_generate("<FocusIn>")
            root.update()
            top = app.canvas.winfo_rooty()
            bottom = top + app.canvas.winfo_height()
            assert control.winfo_rooty() >= top
            assert control.winfo_rooty() + control.winfo_height() <= bottom
            assert app.close_button.winfo_rooty() >= bottom

        assert app.privacy_label.winfo_height() >= app.privacy_label.winfo_reqheight()
        assert app.privacy_label.winfo_rooty() >= app.nav["Help & diagnostics"].winfo_rooty() + app.nav["Help & diagnostics"].winfo_height()
        assert app.privacy_label.winfo_rooty() + app.privacy_label.winfo_height() <= app.close_button.master.winfo_rooty() - 8

        # Resizing a scrolled page must keep controls readable in either column
        # arrangement, including status text after a failed microphone check.
        app.mic_message.set(error_text)
        root.geometry("960x780")
        root.update()
        root.geometry(geometry)
        root.update()
        for label in app._column_labels:
            if not label.winfo_ismapped():
                continue
            assert label.winfo_width() >= int(label.cget("wraplength"))
            assert label.winfo_height() >= label.winfo_reqheight()
    finally:
        app.closed = True
        root.after_cancel(app.poll_id)
        if app._page_reset is not None:
            root.after_cancel(app._page_reset)
        root.destroy()
        tk_root.tk.call("tk", "scaling", baseline)


def test_compact_microphone_button_starts_stops_and_recovers(window, monkeypatch):
    callbacks = []
    monkeypatch.setattr(window, "_worker", lambda action, done: callbacks.append(done))
    window.mic_button.invoke()
    assert window.mic_button.cget("text") == "Stop"
    assert not window.mic_stop.is_set()
    window.mic_button.invoke()
    assert window.mic_stop.is_set()
    assert len(callbacks) == 1
    callbacks.pop()(0.0)
    assert window.mic_button.cget("text") == "Test"
    window.mic_button.invoke()
    assert not window.mic_stop.is_set()
    callbacks.pop()(RuntimeError("unavailable"))
    assert window.mic_button.cget("text") == "Test"


def test_microphone_feedback_cannot_request_wider_columns(window):
    window.root.deiconify()
    window.root.geometry("770x655")
    window.mic_message.set("Ready.")
    window.root.update()
    widths = {label: label.winfo_reqwidth() for label in window._column_labels}
    window.mic_message.set(
        "The selected microphone is disconnected. Reconnect it and refresh devices. "
        "Choose another input if it is still unavailable."
    )
    for geometry in ("960x780", "760x560", "770x655"):
        window.root.geometry(geometry)
        window.root.update()
        for label, width in widths.items():
            assert label.winfo_reqwidth() == width
            if label.winfo_ismapped():
                assert label.winfo_height() >= label.winfo_reqheight()


@pytest.mark.parametrize("state,expected", [
    ("missing", "Install needed"),
    ("incomplete", "Repair needed"),
    ("installed", "Installed files · loading not checked"),
    ("unsupported", "Choose a supported model and device"),
])
def test_landing_model_summary_tracks_selection_without_claiming_ready(window, monkeypatch, state, expected):
    from types import SimpleNamespace
    monkeypatch.setattr("utterleaf.model_setup.inspect_model", lambda *_: SimpleNamespace(state=state))
    baseline = window.baseline.copy()
    window.vars["model"].set("base")
    assert window.model_summary.get() == f"Base English · {expected}"
    assert window.baseline == baseline
    assert "Unsaved" in window.status.get()
    assert "ready" not in window.model_summary.get().lower()
    window.model_manage_button.invoke()
    assert window.pages["Engine"].grid_info()


def test_landing_presence_check_is_bounded_explicit_and_preserves_edits(window, monkeypatch):
    pending = []
    monkeypatch.setattr(window, "_worker", lambda action, done: pending.append((action, done)))
    monkeypatch.setattr("utterleaf.ipc.send", lambda command, **kwargs:
                        "status-v2:listening:unconfirmed" if command == "status-detail"
                        and kwargs == {"exact_reply": True} else pytest.fail(command))
    window.vars["hotkey"].set("f8")
    snapshot = window._snapshot()
    window.refresh_connection()
    window.refresh_connection()
    assert len(pending) == 1
    assert window.connection.get() == "Checking app…"
    assert str(window.connection_button.cget("state")) == "disabled"
    action, done = pending.pop()
    done(action())
    assert window.connection.get() == ("Listening · speech capture in progress\n"
                                       "Loaded model for applied settings: not confirmed.")
    assert not window.checking_connection
    assert str(window.connection_button.cget("state")) == "normal"
    assert window._snapshot() == snapshot
    assert "Unsaved" in window.status.get()
    window.root.update()
    assert pending == []  # Completion does not schedule another status check.

    window.refresh_connection()
    _, done = pending.pop()
    done(RuntimeError("private diagnostic must not appear"))
    assert window.connection.get() == "Could not check the app · Refresh status to retry"
    assert window._snapshot() == snapshot


def test_presence_failure_does_not_assert_a_stopped_app(window, monkeypatch):
    monkeypatch.setattr("utterleaf.ipc.send", lambda command, **kwargs: None)
    assert window._connection_status() == "App not reached · Start Utterleaf, then refresh status"


@pytest.mark.parametrize("reply,expected", [
    ("status-v2:idle:unconfirmed", "Idle · app is running\nLoaded model for applied settings: not confirmed."),
    ("status-v2:ready:tiny.en", "Ready · applied speech model loaded\nLoaded model for applied settings: Tiny English."),
    ("status-v2:processing:base.en", "Processing · preparing or transcribing speech\nLoaded model for applied settings: Base English."),
    ("status-v2:attention:unconfirmed", "Needs attention · check the tray or open Help\nLoaded model for applied settings: not confirmed."),
    ("unknown", "App is running · detailed status unavailable in this version\nLoaded model details unavailable in this version."),
    ("restart-required", "Restart Utterleaf to check its status"),
    ("status-v1:listening private text", "Could not read app status · restart Utterleaf, then retry"),
])
def test_settings_status_refresh_uses_fixed_copy_and_preserves_drafts(window, monkeypatch, reply, expected):
    calls = []
    monkeypatch.setattr("utterleaf.ipc.send", lambda command, **kwargs: calls.append((command, kwargs)) or reply)
    monkeypatch.setattr(window, "_worker", lambda action, done: done(action()))
    window.vars["model"].set("base")
    snapshot = window._snapshot()
    window.refresh_connection()
    assert calls == ([("status-detail", {"exact_reply": True}), ("status", {})]
                     if reply == "unknown" else [("status-detail", {"exact_reply": True})])
    assert window.connection.get() == expected
    assert window._snapshot() == snapshot
    assert "Unsaved" in window.status.get()
    assert ("ready" in window.connection.get().lower()) == (reply == "status-v2:ready:tiny.en")
    assert "ready" not in window.model_summary.get().lower()


def test_status_callback_does_not_touch_closed_settings(window, monkeypatch):
    callbacks = []
    monkeypatch.setattr(window, "_worker", lambda action, done: callbacks.append(done))
    window.refresh_connection()
    window.close()
    callbacks.pop()("Listening · speech capture in progress")
    window.refresh_connection()
    assert callbacks == []


def test_navigation_shortcuts_keep_staged_edits_and_focus_visible_page(window):
    import sys
    modifier = "Command" if sys.platform == "darwin" else "Alt"
    window.root.deiconify()
    window.root.update()
    window.vars["hotkey"].set("f8")
    snapshot = window._snapshot()
    for index, name in enumerate(window.nav, 1):
        assert window.root.bind(f"<{modifier}-Key-{index}>")
        window.root.focus_force()
        window.root.event_generate(f"<{modifier}-Key-{index}>")
        window.root.update()
        assert window.pages[name].grid_info()
        assert window.root.focus_get() == window.nav[name]
        assert window._snapshot() == snapshot
    assert window.root.bind("<F1>")
    window.navigate("Dictation")
    window.root.event_generate("<F1>")
    window.root.update()
    assert window.pages["Help & diagnostics"].grid_info()
    assert "Unsaved" in window.status.get()


def test_wide_page_width_is_capped_without_clipping_compact_controls(window):
    from utterleaf.settings_ui import MAX_PAGE_WIDTH
    window.root.deiconify()
    for geometry in ("1600x800", "760x560", "1280x800"):
        window.root.geometry(geometry)
        window.root.update()
        cap = round(MAX_PAGE_WIDTH * window.root.winfo_fpixels("1i") / 96)
        available = window.canvas.winfo_width()
        width = window.body.winfo_width()
        assert width == min(available, cap)
        assert window.canvas.coords(window.window_id) == [max(0, (available - width) // 2), 0]
        assert window.model_manage_button.winfo_rootx() >= window.canvas.winfo_rootx()
        assert (window.model_manage_button.winfo_rootx() + window.model_manage_button.winfo_width()
                <= window.canvas.winfo_rootx() + available)


@pytest.mark.parametrize("scale", [1.0, 1.5, 2.0])
def test_reference_page_keyboard_scrolling_preserves_focus_and_drafts(tk_root, monkeypatch, scale):
    monkeypatch.setattr("utterleaf.settings_ui.startup_enabled", lambda: False)
    monkeypatch.setattr("utterleaf.settings_ui.dictionary_text", lambda: "utter leaf = Utterleaf")
    baseline = float(tk_root.tk.call("tk", "scaling"))
    root = tk.Toplevel(tk_root)
    root.tk.call("tk", "scaling", baseline * scale)
    app = SettingsWindow(root, Config(), background=False)
    try:
        root.geometry("760x560")
        app.vars["hotkey"].set("f8")
        app.names.insert("end", "\nlocal term = Local Term")
        app.navigate("Voice commands")
        root.update()
        button = app.nav["Voice commands"]
        calls = []
        button.configure(command=lambda: calls.append("navigation"))
        app.save_button.configure(command=lambda: calls.append("save"))
        app.close_button.configure(command=lambda: calls.append("close"))
        button.focus_force()
        root.update()
        snapshot = app._snapshot()
        assert app.canvas.yview()[0] == pytest.approx(0)
        assert app.canvas.yview()[1] < 1

        # Deliver actual Tk key events: reference pages have no form controls
        # whose focus could otherwise reveal text below the viewport.
        button.event_generate("<Next>")
        root.update()
        assert app.canvas.yview()[0] > 0
        button.event_generate("<Prior>")
        root.update()
        assert app.canvas.yview()[0] == pytest.approx(0)
        button.event_generate("<End>")
        root.update()
        assert app.canvas.yview()[1] == pytest.approx(1)
        button.event_generate("<Next>")
        root.update()
        assert app.canvas.yview()[1] == pytest.approx(1)
        button.event_generate("<Home>")
        root.update()
        assert app.canvas.yview()[0] == pytest.approx(0)
        button.event_generate("<Prior>")
        root.update()
        assert app.canvas.yview()[0] == pytest.approx(0)
        assert root.focus_get() == button
        assert app._snapshot() == snapshot
        assert calls == []
    finally:
        app.closed = True
        root.after_cancel(app.poll_id)
        if app._page_reset is not None:
            root.after_cancel(app._page_reset)
        root.destroy()
        tk_root.tk.call("tk", "scaling", baseline)


def test_page_scroll_keys_keep_native_text_and_entry_editing(window):
    window.root.deiconify()
    window.root.geometry("760x560")
    window.navigate("Vocabulary")
    window.root.update()
    window.names.focus_force()
    window.root.update()
    window.names.mark_set("insert", "1.5")
    before = window.canvas.yview()
    window.names.event_generate("<Home>")
    window.root.update()
    assert window.names.index("insert") == "1.0"
    assert window.canvas.yview() == pytest.approx(before)
    window.names.event_generate("<End>")
    window.root.update()
    assert window.names.index("insert") == window.names.index("1.end")
    assert window.canvas.yview() == pytest.approx(before)

    window.navigate("Engine")
    window.root.update()
    entry = window.fields["model"]
    entry.focus_force()
    window.root.update()
    entry.icursor(2)
    before = window.canvas.yview()
    entry.event_generate("<Home>")
    window.root.update()
    assert entry.index("insert") == 0
    assert window.canvas.yview() == pytest.approx(before)
    entry.event_generate("<End>")
    window.root.update()
    assert entry.index("insert") == len(entry.get())
    assert window.canvas.yview() == pytest.approx(before)


def test_page_scroll_handler_leaves_native_controls_in_charge(window):
    from types import SimpleNamespace
    window.root.deiconify()
    window.root.geometry("760x560")
    window.navigate("Voice commands")
    window.root.update()
    window.canvas.yview_moveto(0.3)
    window.root.update()
    before = window.canvas.yview()
    assert before[0] > 0 and before[1] < 1
    controls = [factory(window.root) for factory in (
        tk.Text, tk.Entry, ttk.Entry, ttk.Combobox, tk.Scale, ttk.Scale,
        tk.Spinbox, ttk.Spinbox, tk.Listbox,
    )]
    try:
        for control in controls:
            event = SimpleNamespace(widget=control, state=0)
            for movement in ("up", "down", "top", "bottom"):
                assert window._scroll_page(event, movement) is None, control.winfo_class()
                assert window.canvas.yview() == pytest.approx(before)
    finally:
        for control in controls:
            control.destroy()


def test_page_scroll_handler_accepts_page_controls_without_invoking_them(window):
    from types import SimpleNamespace
    window.root.deiconify()
    window.root.geometry("760x560")
    window.navigate("Voice commands")
    window.root.update()
    calls = []
    controls = [factory(window.root) for factory in (
        tk.Frame, ttk.Frame, tk.Label, ttk.Label, tk.Button, ttk.Button,
        tk.Checkbutton, ttk.Checkbutton, tk.Radiobutton, ttk.Radiobutton,
        ttk.Scrollbar,
    )]
    try:
        for control in controls:
            if "command" in control.keys():
                control.configure(command=lambda *args: calls.append(args))
        for control in [window.root, window.canvas, *controls]:
            event = SimpleNamespace(widget=control, state=0)
            assert window._scroll_page(event, "top") == "break", control.winfo_class()
            assert window.canvas.yview()[0] == pytest.approx(0)
            assert window._scroll_page(event, "bottom") == "break", control.winfo_class()
            assert window.canvas.yview()[1] == pytest.approx(1)
        assert calls == []
    finally:
        for control in controls:
            control.destroy()


def test_page_scroll_handler_preserves_modified_shortcuts_and_allows_lock_keys(window):
    from types import SimpleNamespace
    window.root.deiconify()
    window.root.geometry("760x560")
    window.navigate("Voice commands")
    window.root.update()
    window.canvas.yview_moveto(0.3)
    before = window.canvas.yview()
    button = window.nav["Voice commands"]
    # Shift, Control, Mod1/Command, Mod3, Mod4, Mod5, and Windows Alt.
    for state in (0x1, 0x4, 0x8, 0x20, 0x40, 0x80, 0x20000, 0x5):
        for movement in ("up", "down", "top", "bottom"):
            assert window._scroll_page(SimpleNamespace(widget=button, state=state), movement) is None
            assert window.canvas.yview() == pytest.approx(before)

    aqua = window.root.tk.call("tk", "windowingsystem") == "aqua"
    if aqua:
        # Aqua's Mod2 is Option: it is not a NumLock state to ignore.
        assert window._scroll_page(SimpleNamespace(widget=button, state=0x10), "bottom") is None
        assert window.canvas.yview() == pytest.approx(before)
    allowed_states = (0, 0x2) if aqua else (0, 0x2, 0x10, 0x12)
    for state in allowed_states:
        event = SimpleNamespace(widget=button, state=state)
        assert window._scroll_page(event, "top") == "break"
        assert window.canvas.yview()[0] == pytest.approx(0)
        assert window._scroll_page(event, "bottom") == "break"
        assert window.canvas.yview()[1] == pytest.approx(1)


def test_page_scroll_handler_ignores_other_windows_closed_ui_and_short_pages(window, monkeypatch):
    from types import SimpleNamespace
    window.root.deiconify()
    window.root.geometry("760x560")
    window.navigate("Voice commands")
    window.root.update()
    before = window.canvas.yview()
    dialog = tk.Toplevel(window.root)
    dialog.withdraw()
    other_button = ttk.Button(dialog)
    try:
        assert window._scroll_page(SimpleNamespace(widget=other_button, state=0), "bottom") is None
        assert window.canvas.yview() == pytest.approx(before)
    finally:
        dialog.destroy()
    event = SimpleNamespace(widget=window.nav["Voice commands"], state=0)
    window.closed = True
    try:
        assert window._scroll_page(event, "bottom") is None
        assert window.canvas.yview() == pytest.approx(before)
    finally:
        window.closed = False
    for bounds in (None, (0, 0, 200, window.canvas.winfo_height())):
        monkeypatch.setattr(window.canvas, "bbox", lambda *args, value=bounds: value)
        assert window._scroll_page(event, "bottom") is None
        assert window.canvas.yview() == pytest.approx(before)


@pytest.mark.parametrize("movement", ["down", "bottom"])
def test_accepted_page_scroll_survives_pending_page_reset(window, movement):
    from types import SimpleNamespace
    window.root.deiconify()
    window.root.geometry("760x560")
    window.root.update()
    window.show_page("Voice commands")
    assert window._page_reset is not None
    event = SimpleNamespace(widget=window.nav["Voice commands"], state=0)
    assert window._scroll_page(event, movement) == "break"
    position = window.canvas.yview()
    assert position[0] > 0
    window.root.update()
    assert window.canvas.yview() == pytest.approx(position)
    assert window._page_reset is None
    if movement == "bottom":
        assert window.canvas.yview()[1] == pytest.approx(1)


@pytest.mark.parametrize("native_control", [False, True])
def test_rejected_page_scroll_preserves_pending_page_reset(window, native_control):
    from types import SimpleNamespace
    window.root.deiconify()
    window.root.geometry("760x560")
    window.root.update()
    window.show_page("Vocabulary")
    pending_reset = window._page_reset
    assert pending_reset is not None
    event = SimpleNamespace(
        widget=window.names if native_control else window.nav["Vocabulary"],
        state=0 if native_control else 0x4,
    )
    assert window._scroll_page(event, "bottom") is None
    assert window._page_reset == pending_reset
    window.root.update()
    assert window._page_reset is None
    assert window.canvas.yview()[0] == pytest.approx(0)


@pytest.fixture(params=[1.0, 1.5, 2.0])
def oversized_text_window(tk_root, monkeypatch, request):
    monkeypatch.setattr("utterleaf.settings_ui.startup_enabled", lambda: False)
    monkeypatch.setattr("utterleaf.settings_ui.dictionary_text", lambda: "utter leaf = Utterleaf")
    baseline = float(tk_root.tk.call("tk", "scaling"))
    root = tk.Toplevel(tk_root)
    root.tk.call("tk", "scaling", baseline * request.param)
    app = SettingsWindow(root, Config(), background=False)
    try:
        root.geometry("760x560")
        app.names.configure(height=40)
        app.names.delete("1.0", "end")
        app.names.insert("1.0", "\n".join(f"w{line} = R{line}" for line in range(1, 81)))
        app.navigate("Vocabulary")
        root.update()
        assert app.names.winfo_height() > app.canvas.winfo_height()
        yield app
    finally:
        app.closed = True
        root.after_cancel(app.poll_id)
        if app._page_reset is not None:
            root.after_cancel(app._page_reset)
        root.destroy()
        tk_root.tk.call("tk", "scaling", baseline)


def assert_text_insert_visible(window, box):
    bounds = box.bbox("insert")
    assert bounds is not None, "The insertion character must be visible inside the Text widget"
    line_top = box.winfo_rooty() + bounds[1]
    viewport_top = window.canvas.winfo_rooty()
    assert line_top >= viewport_top
    assert line_top + bounds[3] <= viewport_top + window.canvas.winfo_height()


def test_oversized_editor_focus_reveals_caret_without_oscillation(oversized_text_window):
    window = oversized_text_window
    box = window.names
    snapshot = window._snapshot()
    box.mark_set("insert", "1.0")
    box.see("insert")
    box.focus_force()
    window.root.update()
    assert_text_insert_visible(window, box)
    position = window.canvas.yview()
    for _ in range(3):
        box.event_generate("<FocusIn>")
        window.root.update()
        assert_text_insert_visible(window, box)
        assert window.canvas.yview() == pytest.approx(position)
    assert window._snapshot() == snapshot


@pytest.mark.parametrize("line", [1, 75])
def test_oversized_editor_validation_reveals_selected_line(oversized_text_window, monkeypatch, line):
    from utterleaf.settings import FormValidationError
    window = oversized_text_window
    snapshot = window._snapshot()
    window.navigate("Help & diagnostics")
    window.root.update()
    window.root.focus_force()
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.showerror", lambda *args, **kwargs: None)
    window._show_invalid_field(FormValidationError("names", f"Check vocabulary line {line}.", line))
    window.root.update()
    assert window.names.index("insert") == f"{line}.0"
    assert window.names.get("sel.first", "sel.last") == f"w{line} = R{line}"
    assert_text_insert_visible(window, window.names)
    assert window._snapshot() == snapshot


def test_oversized_editor_key_and_pointer_events_follow_caret(oversized_text_window):
    window = oversized_text_window
    box = window.names
    snapshot = window._snapshot()
    box.mark_set("insert", "1.0")
    box.see("insert")
    box.focus_force()
    window.root.update()
    # Holding Down repeats KeyPress without a release between movements.
    for _ in range(45):
        box.event_generate("<KeyPress-Down>")
        window.root.update()
        assert_text_insert_visible(window, box)
    box.event_generate("<KeyRelease-Down>")
    window.root.update()
    assert box.index("insert") == "46.0"
    assert window._snapshot() == snapshot
    box.event_generate("<KeyPress-x>")
    box.event_generate("<KeyRelease-x>")
    window.root.update()
    assert box.index("insert") == "46.1"
    assert_text_insert_visible(window, box)
    expected = {**snapshot, "names": snapshot["names"].replace("w46 = R46", "xw46 = R46", 1)}
    assert window._snapshot() == expected

    # A pointer release must also reveal a newly placed cursor, without a
    # background monitor or a second focus transition.
    box.mark_set("insert", "1.0")
    box.see("insert")
    box.event_generate("<ButtonRelease-1>", x=15, y=15)
    window.root.update()
    assert_text_insert_visible(window, box)
    assert window._snapshot() == expected


def test_diagnostic_report_keyboard_focus_is_read_only(oversized_text_window):
    window = oversized_text_window
    window.diagnostic_text.configure(height=40)
    window.navigate("Help & diagnostics")
    window.root.update()
    report = window.diagnostic_text
    original = report.get("1.0", "end-1c")
    snapshot = window._snapshot()
    window.diagnostic_button.focus_force()
    window.root.update()
    window.diagnostic_button.event_generate("<Tab>")
    window.root.update()
    assert window.root.focus_get() == report
    assert str(report.cget("state")) == "disabled"
    assert_text_insert_visible(window, report)
    report.event_generate("<KeyPress-x>")
    report.event_generate("<KeyRelease-x>")
    window.root.update()
    assert report.get("1.0", "end-1c") == original
    next_control = report.tk_focusNext()
    report.event_generate("<Tab>")
    window.root.update()
    assert window.root.focus_get() == next_control
    assert next_control != report
    next_control.event_generate("<Shift-Tab>")
    window.root.update()
    assert window.root.focus_get() == report
    assert report.get("1.0", "end-1c") == original
    assert window._snapshot() == snapshot


def test_oversized_editor_cursor_follow_ignores_stale_focus_and_closed_settings(window, monkeypatch):
    from types import SimpleNamespace
    window.root.deiconify()
    window.root.geometry("760x560")
    window.names.configure(height=40)
    window.navigate("Vocabulary")
    window.root.update()
    assert window.names.winfo_height() > window.canvas.winfo_height()
    window.nav["Vocabulary"].focus_force()
    window.root.update()
    window.canvas.yview_moveto(1)
    before = window.canvas.yview()
    assert window._reveal_text_cursor(SimpleNamespace(widget=window.names)) is None
    assert window.canvas.yview() == pytest.approx(before)
    assert window.root.focus_get() == window.nav["Vocabulary"]

    # A queued local event after close must not consult destroyed Tk state.
    window.closed = True
    monkeypatch.setattr(window.root, "focus_get", lambda: pytest.fail("closed Settings queried focus"))
    try:
        assert window._reveal_text_cursor(SimpleNamespace(widget=object())) is None
    finally:
        window.closed = False


def test_oversized_editor_cursor_follow_leaves_fitting_controls_unchanged(window):
    from types import SimpleNamespace
    window.root.deiconify()
    window.root.geometry("760x560")
    window.navigate("Vocabulary")
    window.root.update()
    assert window.names.winfo_height() < window.canvas.winfo_height()
    window.names.focus_force()
    window.root.update()
    window.canvas.yview_moveto(0)
    before = window.canvas.yview()
    assert window._reveal_text_cursor(SimpleNamespace(widget=window.names)) is None
    assert window.canvas.yview() == pytest.approx(before)
    window.nav["Vocabulary"].focus_force()
    window.root.update()
    assert window._reveal_text_cursor(SimpleNamespace(widget=window.nav["Vocabulary"])) is None
    assert window.canvas.yview() == pytest.approx(before)
