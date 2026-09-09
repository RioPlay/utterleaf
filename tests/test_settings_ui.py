"""Exercise real Tk widgets without hardware, network, or personal config writes."""
import time
import tkinter as tk
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


def test_mascots_are_loaded_from_package_and_fit_compact_header(window):
    assert set(window.mascots) == {"Dictation", "Vocabulary", "Voice commands", "Help & diagnostics"}
    window.root.deiconify()
    window.root.geometry("760x560")
    for name in window.mascots:
        window.show_page(name)
        window.root.update()
        label = window.mascot_labels[name]
        assert label.winfo_width() >= 104
        assert label.winfo_rootx() >= window.canvas.winfo_rootx()
        assert label.winfo_rootx() + label.winfo_width() <= window.canvas.winfo_rootx() + window.canvas.winfo_width()


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
