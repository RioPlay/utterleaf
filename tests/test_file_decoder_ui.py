import gc
import tkinter as tk
from types import SimpleNamespace

import pytest

from utterleaf.file_decoder_ui import DecoderDialog
from utterleaf import theme


@pytest.fixture(scope="module")
def root():
    failure = None
    try:
        window = tk.Tk()
    except tk.TclError as exc:
        failure = str(exc)
    if failure is not None:
        gc.collect()
        pytest.skip(f"Tk needs a working display: {failure}")
    window.withdraw()
    yield window
    window.destroy()
    del window
    gc.collect()


@pytest.fixture
def dialog(root, tmp_path, monkeypatch, request):
    monkeypatch.setattr("utterleaf.file_decoder._settings_path", lambda: tmp_path / "decoder.json")
    monkeypatch.setattr("utterleaf.file_probe._settings_path", lambda: tmp_path / "probe.json")
    if hasattr(request, "param"):
        monkeypatch.setattr("utterleaf.file_decoder_ui.sys", SimpleNamespace(platform=request.param))
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


@pytest.mark.parametrize("selected", (False, True))
@pytest.mark.parametrize("dialog", ("win32", "darwin", "linux"), indirect=True)
def test_setup_instructions_and_actions_fit_compact_dialog(dialog, monkeypatch, selected):
    if selected:
        prefix = "/" + "long selected installation folder/" * 24
        monkeypatch.setattr("utterleaf.file_decoder_ui.decoder_selection", lambda: {"path": prefix + "ffmpeg.exe"})
        monkeypatch.setattr("utterleaf.file_decoder_ui.probe_selection", lambda: {"path": prefix + "ffprobe.exe"})
        dialog.refresh()
    dialog.root.master.deiconify()
    dialog.root.deiconify()
    dialog.root.geometry("560x500")
    dialog.root.update_idletasks()
    dialog.root.update()
    assert dialog.root.cget("background") == theme.SURFACE
    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)
    for widget in descendants(dialog.root):
        if widget.winfo_class() in ("TButton", "TEntry"):
            assert widget.winfo_ismapped()
            root_bottom = dialog.root.winfo_rooty() + dialog.root.winfo_height()
            root_right = dialog.root.winfo_rootx() + dialog.root.winfo_width()
            assert widget.winfo_rooty() + widget.winfo_height() <= root_bottom
            assert widget.winfo_rootx() + widget.winfo_width() <= root_right
    dialog.root.master.withdraw()


def test_probe_selection_decline_then_select_and_forget_preserves_executable(dialog, monkeypatch, tmp_path):
    executable = tmp_path / "ffprobe.exe"
    executable.write_bytes(b"MZ fixture")
    monkeypatch.setattr("utterleaf.file_decoder_ui.filedialog.askopenfilename", lambda **kw: str(executable))
    monkeypatch.setattr("utterleaf.file_decoder_ui.messagebox.askyesno", lambda *a, **kw: False)
    dialog.choose_probe()
    assert not (tmp_path / "probe.json").exists()
    monkeypatch.setattr("utterleaf.file_decoder_ui.messagebox.askyesno", lambda *a, **kw: True)
    dialog.choose_probe()
    assert (tmp_path / "probe.json").exists()
    dialog.forget_probe()
    assert executable.exists()
    assert not (tmp_path / "probe.json").exists()


def test_refresh_reports_both_tool_states(dialog):
    assert "FFmpeg" not in dialog.ffmpeg_status.get()
    assert "PCM WAV inspection works" in dialog.ffprobe_status.get()


def test_long_setup_instructions_scroll_without_displacing_tool_actions(dialog):
    dialog.root.master.deiconify()
    dialog.root.deiconify()
    dialog.root.geometry("560x500")
    dialog.instructions.configure(state="normal")
    dialog.instructions.insert("end", "\n" + "Additional installation guidance.\n" * 40)
    dialog.instructions.configure(state="disabled")
    dialog.root.update()
    assert str(dialog.instructions.cget("state")) == "disabled"
    assert dialog.instructions.yview()[1] < 1
    dialog.instructions.yview_moveto(1)
    assert dialog.instructions.yview()[1] == 1
    assert dialog.instructions.winfo_height() > 30
    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from descendants(child)
    for widget in descendants(dialog.root):
        if widget.winfo_class() in ("TButton", "TEntry"):
            assert widget.winfo_ismapped()
            assert widget.winfo_rooty() + widget.winfo_height() <= dialog.root.winfo_rooty() + dialog.root.winfo_height()
    dialog.root.master.withdraw()
