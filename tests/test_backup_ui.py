import tkinter as tk

import pytest

from utterleaf import config
from utterleaf.backup import export_backup, inspect_backup
from utterleaf.backup_ui import BackupDialog


@pytest.fixture(scope="module")
def tk_root():
    # Real Tk widgets with synthetic files; no microphone or running-app IPC.
    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk display unavailable: {error}")
    root.withdraw()
    yield root
    root.destroy()


@pytest.fixture
def context(tmp_path, monkeypatch, tk_root):
    root = tk_root
    monkeypatch.setattr(config, "config_path", lambda: tmp_path / "config.toml")
    monkeypatch.setattr(config, "dictionary_path", lambda: tmp_path / "dictionary.txt")
    config.save(config.Config(allow_network=False, beep=True))
    config.dictionary_path().write_text("old = Original\n", encoding="utf-8")
    yield root, tmp_path
    for child in root.winfo_children():
        child.destroy()
    root.withdraw()


def imported_dialog(context, on_applied=lambda _value: None):
    root, _ = context
    plan = inspect_backup(export_backup(config.Config(beep=False), "new = New\n"))
    return BackupDialog(root, config.load(), config.dictionary_path().read_text(),
                        plan=plan, on_applied=on_applied)


def test_import_default_selects_nothing_and_cancel_leaves_files(context):
    before = (config.config_path().read_bytes(), config.dictionary_path().read_bytes())
    dialog = imported_dialog(context)
    assert not any(var.get() for var in dialog.selected.values())
    assert dialog.mode.get() == "keep"
    assert "None selected" in dialog.preview.get("1.0", "end")
    dialog.root.destroy()
    assert (config.config_path().read_bytes(), config.dictionary_path().read_bytes()) == before


def test_declined_confirmation_does_not_apply(context, monkeypatch):
    dialog = imported_dialog(context)
    dialog.selected["beep"].set(True)
    dialog.mode.set("replace")
    dialog.refresh()
    monkeypatch.setattr("utterleaf.backup_ui.messagebox.askyesno", lambda *a, **k: False)
    dialog.confirm_action()
    assert config.load().beep is True
    assert config.dictionary_path().read_text() == "old = Original\n"


def test_confirmed_review_applies_selected_values_and_preserves_privacy(context, monkeypatch):
    applied = []
    dialog = imported_dialog(context, applied.append)
    dialog.selected["beep"].set(True)
    dialog.mode.set("merge")
    dialog.refresh()
    assert "Sound feedback: On → Off" in dialog.preview.get("1.0", "end")
    assert "Imported vocabulary entries: 1" in dialog.preview.get("1.0", "end")
    monkeypatch.setattr("utterleaf.backup_ui.messagebox.askyesno", lambda *a, **k: True)
    dialog.confirm_action()
    assert len(applied) == 1
    assert config.load().beep is False
    assert config.load().allow_network is False
    assert config.load().restore_clipboard is True
    assert config.dictionary_path().read_text() == "old = Original\nnew = New\n"


def test_export_preview_requires_file_selection_and_refuses_overwrite(context, monkeypatch):
    root, tmp_path = context
    target = tmp_path / "export.json"
    dialog = BackupDialog(root, config.load(), "name = Námé\n")
    assert "Námé" in dialog.preview.get("1.0", "end")
    assert not target.exists()
    monkeypatch.setattr("utterleaf.backup_ui.filedialog.asksaveasfilename", lambda **kw: str(target))
    dialog.confirm_action()
    original = target.read_bytes()
    errors = []
    monkeypatch.setattr("utterleaf.backup_ui.messagebox.showerror", lambda *a, **kw: errors.append(a))
    dialog.confirm_action()
    assert target.read_bytes() == original
    assert errors[0][0] == "Choose a new filename"


def test_changed_settings_after_preview_fail_without_implicit_refresh(context, monkeypatch):
    dialog = imported_dialog(context)
    dialog.selected["beep"].set(True)
    dialog.refresh()
    config.save(config.Config(beep=True, allow_network=False, restore_clipboard=False))
    errors = []
    monkeypatch.setattr("utterleaf.backup_ui.messagebox.askyesno", lambda *a, **kw: True)
    monkeypatch.setattr("utterleaf.backup_ui.messagebox.showerror", lambda *a, **kw: errors.append(a))
    dialog.confirm_action()
    assert config.load().beep is True
    assert config.load().restore_clipboard is False
    assert "changed since preview" in errors[0][1]


def test_dialog_actions_and_preview_fit_compact_window_and_tab_order(context):
    context[0].deiconify()
    dialog = imported_dialog(context)
    dialog.root.geometry("480x460")
    dialog.root.update()
    for widget in (dialog.confirm, dialog.preview):
        assert widget.winfo_width() > 20
        assert widget.winfo_height() > 10
        assert widget.winfo_rootx() >= dialog.root.winfo_rootx()
        assert widget.winfo_rootx() + widget.winfo_width() <= dialog.root.winfo_rootx() + dialog.root.winfo_width()
        assert widget.winfo_rooty() + widget.winfo_height() <= dialog.root.winfo_rooty() + dialog.root.winfo_height()
    current = dialog.confirm
    visited = set()
    for _ in range(30):
        current = current.tk_focusNext()
        if str(current) in visited:
            break
        visited.add(str(current))
    assert str(dialog.preview) in visited
    assert str(dialog.confirm) in visited
