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
