import tkinter as tk

import pytest

from utterleaf.file_decoder_ui import DecoderDialog
from utterleaf import theme


@pytest.fixture(scope="module")
def root():
    try:
        window = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk needs a working display: {exc}")
    window.withdraw()
    yield window
    window.destroy()


@pytest.fixture
def dialog(root, tmp_path, monkeypatch):
    monkeypatch.setattr("utterleaf.file_decoder._settings_path", lambda: tmp_path / "decoder.json")
    value = DecoderDialog(root)
    yield value
    if value.root.winfo_exists():
        value.root.destroy()


def test_download_button_opens_only_official_page(dialog, monkeypatch):
    urls = []
    monkeypatch.setattr("utterleaf.file_decoder_ui.webbrowser.open", lambda url: urls.append(url) or True)
    dialog.download_page()
    assert urls == ["https://ffmpeg.org/download.html"]


def test_declining_executable_selection_does_not_remember_it(dialog, monkeypatch, tmp_path):
    executable = tmp_path / "ffmpeg.exe"
    executable.write_bytes(b"MZ fixture")
    monkeypatch.setattr("utterleaf.file_decoder_ui.filedialog.askopenfilename", lambda **kw: str(executable))
    monkeypatch.setattr("utterleaf.file_decoder_ui.messagebox.askyesno", lambda *a, **kw: False)
    dialog.choose()
    assert not (tmp_path / "decoder.json").exists()
    monkeypatch.setattr("utterleaf.file_decoder_ui.messagebox.askyesno", lambda *a, **kw: True)
    dialog.choose()
    assert (tmp_path / "decoder.json").exists()
    dialog.forget()
    assert executable.exists()
    assert not (tmp_path / "decoder.json").exists()


def test_setup_instructions_and_actions_fit_compact_dialog(dialog):
    dialog.root.geometry("560x500")
    dialog.root.update()
    assert dialog.root.cget("background") == theme.SURFACE
    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)
    for widget in descendants(dialog.root):
        if widget.winfo_class() == "TButton":
            assert widget.winfo_rooty() + widget.winfo_height() <= dialog.root.winfo_rooty() + dialog.root.winfo_height()
            assert widget.winfo_rootx() + widget.winfo_width() <= dialog.root.winfo_rootx() + dialog.root.winfo_width()
