"""Exercise real Tk widgets without hardware, network, or personal config writes."""
import time
import tkinter as tk
from tkinter import ttk
import pytest

from utterleaf.config import Config
from utterleaf.settings_ui import SettingsWindow


@pytest.fixture(scope="module")
def tk_root():
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk needs a working display: {exc}")
    root.withdraw()
    yield root
    root.destroy()


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
        assert "ready" in window.mic_message.get().lower()
    assert window.mic_button.cget("text") == "Test microphone"


def test_model_status_updates_without_saving_or_downloading(window, tmp_path, monkeypatch):
    monkeypatch.setattr("utterleaf.models.models_dir", lambda: tmp_path)
    monkeypatch.setattr("utterleaf.model_setup.run_download", lambda *a, **k: pytest.fail("Status must not download"))
    window.vars["model"].set("tiny")
    window.vars["language"].set("en")
    window.vars["device"].set("cpu")
    assert "Missing" in window.model_status.get()
    assert "tiny.en" in window.model_status.get()
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
    assert "base.en" in window.model_status.get()
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
    assert str(window.mic_button.cget("text")) == "Test microphone"


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


def test_preview_can_preserve_transcript_without_vocabulary_or_commands(window):
    window.vars["text_cleanup"].set(False)
    window.sample.delete("1.0", "end")
    sample = "um utter leaf, new paragraph, I mean scratch that"
    window.sample.insert("1.0", sample)
    window.preview()
    assert window.preview_result.get() == sample


def test_save_uses_snapshot_and_keeps_later_edits(window, monkeypatch):
    import threading
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


def test_invalid_output_format_returns_to_vocabulary_page(window, monkeypatch):
    from utterleaf.settings import FormValidationError

    pages = []
    monkeypatch.setattr(window, "show_page", pages.append)
    monkeypatch.setattr("utterleaf.settings_ui.messagebox.showerror", lambda *a, **k: None)
    window._show_invalid_field(FormValidationError("output_format", "Choose prose or Markdown output."))
    assert pages == ["Vocabulary"]


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
    assert saved == [Config()]
    assert names == ["utter leaf = Utterleaf"]
    assert startup == [False]
    assert commands == ["reload"]
    assert not window._reset_pending
    assert str(window.save_button.cget("state")) == "disabled"


def test_cuda_report_can_be_exported_and_failure_disables_export(window, monkeypatch):
    monkeypatch.setattr(window, "_worker", lambda action, done: done("GPU setup steps"))
    window.cuda_setup()
    assert window.report == "GPU setup steps"
    assert str(window.export_button.cget("state")) == "normal"
    monkeypatch.setattr(window, "_worker", lambda action, done: done(RuntimeError("probe failed")))
    window.cuda_setup()
    assert window.report == ""
    assert str(window.export_button.cget("state")) == "disabled"


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
    box = window.hotkey_box
    assert window.canvas.yview()[0] == pytest.approx(0)
    box.event_generate("<Button-1>", x=box.winfo_width() - 5, y=box.winfo_height() // 2)
    window.root.update()
    popup = box.tk.call("ttk::combobox::PopdownWindow", str(box))
    assert window.canvas.yview()[0] == pytest.approx(0)
    assert int(box.tk.call("winfo", "rootx", popup)) == box.winfo_rootx()
    assert int(box.tk.call("winfo", "rooty", popup)) == box.winfo_rooty() + box.winfo_height()
    window.root.event_generate("<Escape>")
    window.root.update()


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
    window.canvas.yview_moveto(.25)
    window.root.update()
    assert button.winfo_rooty() >= window.canvas.winfo_rooty()
    button.event_generate("<ButtonPress-1>", x=10, y=10)
    button.event_generate("<ButtonRelease-1>", x=10, y=10)
    window.root.update()
    assert calls == ["mic"]


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
