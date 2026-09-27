"""Verify the backup capture inventory and its synthetic-only boundaries."""
from contextlib import contextmanager
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import capture_backup
from test_capture_auxiliary import working_tk_display
from utterleaf import backup_store, backup_ui, config, polish
from utterleaf.backup import export_backup, inspect_backup


def test_backup_capture_inventory_is_small_explicit_and_unique():
    assert len(capture_backup.INVENTORY) == 8
    assert len(set(capture_backup.INVENTORY)) == 8
    assert {state for state, _size, _scale in capture_backup.CASES} == {"export", "import", "error"}
    assert {size for _state, size, _scale in capture_backup.CASES} == {(480, 460), (680, 660)}
    assert {scale for _state, _size, scale in capture_backup.CASES} == {1.0, 2.0}


def test_guard_serves_synthetic_originals_to_real_import_preparation():
    with capture_backup.blocked_runtime() as runtime:
        cfg, vocabulary = backup_store.read_current()
        assert cfg == runtime.cfg
        assert vocabulary == capture_backup.VOCABULARY
        plan = inspect_backup(export_backup(config.Config(beep=False), "new = Synthetic\n"))
        review = backup_store.prepare_import(plan, preference_keys=("beep",), vocabulary_mode="merge")
        assert review.preference_changes == (("beep", True, False),)
        assert review.values.config.allow_network is False
        assert review.paths == runtime.paths
        assert review.originals == runtime.originals
        assert not any(path.exists() for path in runtime.paths)
        assert not runtime.violations


def test_guard_rejects_both_backup_io_aliases_and_personal_configuration():
    with capture_backup.blocked_runtime() as runtime:
        for action in (
            lambda: config.load(), lambda: config.save(config.Config()),
            lambda: polish.dictionary_text(), lambda: polish.save_dictionary("synthetic = value"),
            lambda: backup_store.apply_import(None), lambda: backup_ui.apply_import(None),
            lambda: backup_store.write_backup(Path("never-created.json"), "{}"),
            lambda: backup_ui.write_backup(Path("never-created.json"), "{}"),
            lambda: backup_store._atomic_write(Path("never-created.toml"), b""),
            lambda: backup_store._read(Path("non-synthetic.toml"), 100),
        ):
            with pytest.raises(AssertionError, match="Backup capture blocked"):
                action()
        assert len(runtime.violations) == 10


def test_guard_blocks_native_dialogs_clipboard_devices_and_background_work():
    import socket
    import threading
    import tkinter as tk
    from tkinter import filedialog, messagebox
    import sounddevice

    with capture_backup.blocked_runtime() as runtime:
        for action in (
            lambda: filedialog.asksaveasfilename(), lambda: filedialog.askopenfilename(),
            lambda: messagebox.askyesno("Synthetic", "Do not open"),
            lambda: tk.Misc.clipboard_get(None), lambda: tk.Misc.clipboard_append(None, "synthetic"),
            lambda: sounddevice.InputStream(), lambda: socket.socket(),
            lambda: threading.Thread(target=lambda: None).start(),
        ):
            with pytest.raises(AssertionError, match="Backup capture blocked"):
                action()
        assert len(runtime.violations) == 8


@pytest.mark.parametrize("state", ["export", "import", "error"])
def test_staged_backup_dialogs_are_synthetic_and_never_apply(state, working_tk_display):
    with capture_backup.blocked_runtime() as runtime, capture_backup.owned_root() as (owner, errors):
        owner.deiconify()
        owner.update()
        dialog = capture_backup.stage_dialog(owner, runtime, state)
        try:
            owner.update()
            preview = dialog.preview.get("1.0", "end-1c")
            assert preview
            assert str(dialog.preview.cget("state")) == "disabled"
            if state == "error":
                assert "Could not build a safe preview" in preview
                assert str(dialog.confirm.cget("state")) == "disabled"
                assert dialog.payload is dialog.review is None
            elif state == "export":
                assert "Synthetic Term" in preview
                assert dialog.payload == preview
            else:
                assert "Sound feedback: On → Off" in preview
                assert "Decision: merge" in preview
                assert dialog.review.values.config.allow_network is False
            assert not any(path.exists() for path in runtime.paths)
            assert not runtime.violations
            assert not errors
        finally:
            dialog.root.destroy()


def test_unknown_stage_rejects_before_building_a_dialog():
    with pytest.raises(ValueError, match="unknown"):
        capture_backup.stage_dialog(None, None, "unknown")


def test_input_guard_blocks_native_keys_and_tcl_clipboard_before_mapping(working_tk_display):
    import tkinter as tk

    with capture_backup.owned_root() as (root, errors):
        editor = tk.Text(root)
        editor.pack()
        editor.insert("1.0", "Synthetic input")
        editor.tag_add("sel", "1.0", "1.9")
        capture_backup.guard_input(root, errors)
        calls = []
        root.tk.call("rename", "clipboard", "BackupOriginalClipboard")
        root.tk.createcommand("clipboard", lambda *args: calls.append(args) or "")
        try:
            root.deiconify()
            editor.focus_force()
            root.update()
            for event in ("<KeyPress-x>", "<<Copy>>", "<<Paste>>", "<ButtonPress-1>"):
                editor.event_generate(event)
                root.update()
            assert editor.get("1.0", "end-1c") == "Synthetic input"
            assert not calls
            assert errors == ["Unexpected input during backup capture"] * 4
        finally:
            root.tk.deletecommand("clipboard")
            root.tk.call("rename", "BackupOriginalClipboard", "clipboard")


def test_capture_refuses_existing_and_outside_output_without_modification(tmp_path, monkeypatch):
    monkeypatch.setattr(capture_backup, "ROOT", tmp_path)
    existing = tmp_path / "artifacts" / "keep"
    existing.mkdir(parents=True)
    sentinel = existing / "original.txt"
    sentinel.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        capture_backup.capture_all(existing)
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert list(existing.iterdir()) == [sentinel]
    outside = tmp_path / "outside"
    with pytest.raises(ValueError, match="artifacts"):
        capture_backup.capture_all(outside)
    assert not outside.exists()


@pytest.mark.parametrize("failed", [False, True])
def test_manifest_keeps_source_receipt_and_complete_or_incomplete_inventory(tmp_path, monkeypatch, failed):
    monkeypatch.setattr(capture_backup, "ROOT", tmp_path)
    source = tmp_path / "utterleaf"
    source.mkdir()
    for name in capture_backup.SOURCE_NAMES:
        (source / name).write_text("synthetic source", encoding="utf-8")
    helper = tmp_path / "tests" / "capture_auxiliary.py"
    helper.parent.mkdir()
    helper.write_text("synthetic helper", encoding="utf-8")

    @contextmanager
    def fake_root(scale=1.0):
        root = SimpleNamespace(scale=scale, geometry=lambda *_: None,
                               deiconify=lambda: None, destroy=lambda: None)
        yield root, []

    def fake_capture(root, errors, filename, size, output):
        if failed:
            raise RuntimeError("Synthetic capture failure")
        return {"file": filename, "requested_size": list(size), "actual_size": list(size),
                "tk_scaling": root.scale, "actions": [], "synthetic": True}

    monkeypatch.setattr(capture_backup, "owned_root", fake_root)
    monkeypatch.setattr(capture_backup, "settle", lambda *_: None)
    monkeypatch.setattr(capture_backup, "guard_input", lambda *_: None)
    monkeypatch.setattr(capture_backup, "stage_dialog", lambda owner, *_: SimpleNamespace(root=owner))
    monkeypatch.setattr(capture_backup, "choice_bounds", lambda *_: [])
    monkeypatch.setattr(capture_backup, "capture", fake_capture)
    output = tmp_path / "artifacts" / "new-backup"
    if failed:
        with pytest.raises(RuntimeError, match="Synthetic capture failure"):
            capture_backup.capture_all(output)
    else:
        capture_backup.capture_all(output)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == ("incomplete" if failed else "completed")
    assert "Synthetic" in manifest["scope"]
    assert set(manifest["sources"]) == set(capture_backup.SOURCE_NAMES)
    assert all(len(value) == 64 for value in manifest["sources"].values())
    assert len(manifest["capture_helper_sha256"]) == 64
    assert tuple(record["file"] for record in manifest["captures"]) == (() if failed else capture_backup.INVENTORY)
