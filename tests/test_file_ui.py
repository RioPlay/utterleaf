"""Real Tk workflow checks, with deterministic local recognition substitutes."""

import threading
import time
import tkinter as tk
import os

import pytest

from utterleaf.config import Config
from utterleaf.file_ui import FileWindow
from utterleaf.transcript import Segment, Transcript


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
def window(tk_root):
    root = tk.Toplevel(tk_root)
    root.withdraw()
    app = FileWindow(root, Config())
    yield app
    app.close()


def pump(window, predicate):
    deadline = time.monotonic() + 3
    while not predicate() and time.monotonic() < deadline:
        window.root.update()
        time.sleep(0.01)
    assert predicate()


def test_cancel_discards_late_success_and_blocks_duplicate_jobs(window, monkeypatch, tmp_path):
    started, release = threading.Event(), threading.Event()
    calls = []
    def recognize(*args, **kwargs):
        calls.append(1)
        started.set()
        release.wait(3)
        return Transcript((Segment(0, 1, "private words"),))
    monkeypatch.setattr("utterleaf.file_ui.transcribe_file", recognize)
    window.path = tmp_path / "voice.wav"
    window.start()
    assert started.wait(1)
    window.start()
    window.cancel()
    release.set()
    pump(window, lambda: not window.busy)
    assert calls == [1]
    assert window.result is None
    assert window.preview.get("1.0", "end").strip() == ""
    assert "Cancelled" in window.status.get()
    assert list(tmp_path.iterdir()) == []


def test_close_discards_queued_result_without_widget_callbacks(window):
    result = Transcript((Segment(0, 1, "private words"),))
    old_events = window.events
    old_events.put(("result", result))
    window.close()
    old_events.put(("result", result))
    window.poll()
    assert window.result is None
    assert window.events.empty()
    assert window.cancel_event.is_set()


def test_export_needs_explicit_replace_and_preserves_preview(window, monkeypatch, tmp_path):
    path = tmp_path / "字幕.vtt"
    path.write_text("keep", encoding="utf-8")
    window.result = Transcript((Segment(0, 1, "東京"),))
    window.format.set("VTT")
    monkeypatch.setattr("utterleaf.file_ui.filedialog.asksaveasfilename", lambda **kwargs: str(path))
    monkeypatch.setattr("utterleaf.file_ui.messagebox.askyesno", lambda *args, **kwargs: False)
    window.export()
    assert path.read_text(encoding="utf-8") == "keep"
    monkeypatch.setattr("utterleaf.file_ui.messagebox.askyesno", lambda *args, **kwargs: True)
    window.export()
    assert path.read_text(encoding="utf-8").startswith("WEBVTT\n\n")
    assert "東京" in path.read_text(encoding="utf-8")
    assert window.result.text == "東京"
    window.discard()
    assert window.result is None
    assert path.exists()


def test_export_never_replaces_selected_media(window, monkeypatch, tmp_path):
    path = tmp_path / "speech.wav"
    path.write_bytes(b"original media")
    window.path = path
    window.result = Transcript((Segment(0, 1, "speech"),))
    monkeypatch.setattr("utterleaf.file_ui.filedialog.asksaveasfilename", lambda **kwargs: str(path))
    window.export()
    assert path.read_bytes() == b"original media"
    assert "preserve the original" in window.status.get()


def test_export_never_replaces_media_hardlink(window, monkeypatch, tmp_path):
    source = tmp_path / "speech.wav"
    source.write_bytes(b"original media")
    alias = tmp_path / "alias.txt"
    os.link(source, alias)
    window.path = source
    window.result = Transcript((Segment(0, 1, "speech"),))
    monkeypatch.setattr("utterleaf.file_ui.filedialog.asksaveasfilename", lambda **kwargs: str(alias))
    window.export()
    assert source.read_bytes() == b"original media"
    assert "preserve the original" in window.status.get()


def test_success_preview_stays_unsaved_and_compact_footer_visible(window, monkeypatch, tmp_path):
    monkeypatch.setattr("utterleaf.file_ui.transcribe_file", lambda *args, **kwargs: Transcript((Segment(0, 1, "scratch that 東京"),)))
    window.path = tmp_path / "speech.wav"
    window.start()
    pump(window, lambda: not window.busy)
    assert window.preview.get("1.0", "end").strip() == "scratch that 東京"
    assert list(tmp_path.iterdir()) == []
    window.root.deiconify()
    window.root.geometry("760x560")
    window.root.update()
    assert window.export_button.winfo_rooty() + window.export_button.winfo_height() <= window.root.winfo_rooty() + window.root.winfo_height()
