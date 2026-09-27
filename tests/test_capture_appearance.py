"""Synthetic-only artwork capture inventory, export workers and I/O guards."""
from contextlib import contextmanager
import json
import threading
from types import SimpleNamespace

import pytest

import capture_appearance
from test_capture_auxiliary import working_tk_display
from utterleaf import brand_export, config, polish


def test_artwork_inventory_covers_five_tabs_compact_wordmark_and_failure():
    assert len(capture_appearance.INVENTORY) == len(set(capture_appearance.INVENTORY)) == 9
    assert {tab for tab, _size, scale, error in capture_appearance.CASES if scale == 1.0} == set(
        capture_appearance.TABS)
    assert ("Wordmark", (720, 540), 2.0, False) in capture_appearance.CASES
    assert ("Wordmark", (720, 540), 2.0, True) in capture_appearance.CASES


def test_guard_blocks_personal_preferences_and_unstaged_exports():
    with capture_appearance.blocked_runtime() as runtime:
        for action in (
            lambda: config.load(), lambda: config.save(config.Config()),
            lambda: config.config_path(), lambda: config.dictionary_path(),
            lambda: polish.dictionary_text(), lambda: polish.save_dictionary("synthetic = data"),
            lambda: brand_export.export_pack("never-created.zip"),
        ):
            with pytest.raises(AssertionError, match="Artwork capture blocked"):
                action()
        assert len(runtime.violations) == 7


def test_guard_holds_only_expected_workers_and_intercepts_export_without_writing():
    ran = []
    with capture_appearance.blocked_runtime() as runtime:
        with pytest.raises(AssertionError, match="unexpected worker"):
            threading.Thread(target=lambda: ran.append(True)).start()
        runtime.allow_worker = True
        threading.Thread(target=lambda: ran.append(True)).start()
        runtime.allow_worker = False
        assert not ran
        runtime.workers.pop()()
        assert ran == [True]
        runtime.save_path = "synthetic-artwork.zip"
        runtime.export_error = OSError("Synthetic failure")
        with pytest.raises(OSError, match="Synthetic failure"):
            brand_export.export_pack(runtime.save_path)
        assert runtime.exports == ["synthetic-artwork.zip"]


def test_guard_intercepts_native_dialogs_and_blocks_devices_network_and_clipboard():
    import socket
    import tkinter as tk
    from tkinter import filedialog, messagebox
    import sounddevice

    with capture_appearance.blocked_runtime() as runtime:
        assert filedialog.asksaveasfilename() == ""
        messagebox.showerror("Synthetic error", "No native modal")
        assert runtime.dialogs == [("showerror", ("Synthetic error", "No native modal"))]
        for action in (
            lambda: filedialog.askopenfilename(), lambda: messagebox.askyesno("Synthetic", "No dialog"),
            lambda: sounddevice.InputStream(), lambda: socket.socket(),
            lambda: tk.Misc.clipboard_get(None), lambda: tk.Misc.clipboard_append(None, "synthetic"),
        ):
            with pytest.raises(AssertionError, match="Artwork capture blocked"):
                action()
        assert len(runtime.violations) == 6


def test_guarded_export_uses_real_worker_target_and_result_queue(working_tk_display):
    with capture_appearance.blocked_runtime() as runtime, capture_appearance.owned_root() as (owner, errors):
        owner.deiconify()
        owner.update()
        guide = capture_appearance.AppearanceGuide(owner)
        try:
            capture_appearance.start_export(guide, runtime)
            assert len(runtime.workers) == 1
            assert not runtime.exports
            assert guide.export_poll is not None
            assert str(guide.export_button.cget("state")) == "disabled"
            capture_appearance.finish_export(guide, runtime, OSError(capture_appearance.SYNTHETIC_ERROR))
            owner.update()
            assert not runtime.workers
            assert runtime.exports == ["synthetic-artwork.zip"]
            assert guide.export_poll is None
            assert str(guide.export_button.cget("state")) == "normal"
            assert not errors and not runtime.violations
        finally:
            guide.close()


def test_output_is_exclusive_and_stays_in_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(capture_appearance, "ROOT", tmp_path)
    existing = tmp_path / "artifacts" / "keep"
    existing.mkdir(parents=True)
    sentinel = existing / "before.txt"
    sentinel.write_text("before", encoding="utf-8")
    with pytest.raises(FileExistsError):
        capture_appearance.capture_all(existing)
    assert sentinel.read_text(encoding="utf-8") == "before"
    assert list(existing.iterdir()) == [sentinel]
    with pytest.raises(ValueError, match="artifacts"):
        capture_appearance.capture_all(tmp_path / "outside")
    assert not (tmp_path / "outside").exists()


@pytest.mark.parametrize("failed", [False, True])
def test_manifest_tracks_inventory_hashes_and_early_input_guard(tmp_path, monkeypatch, failed):
    monkeypatch.setattr(capture_appearance, "ROOT", tmp_path)
    source = tmp_path / "utterleaf"
    source.mkdir()
    for name in capture_appearance.SOURCE_NAMES:
        (source / name).write_text("synthetic source", encoding="utf-8")
    helpers = tmp_path / "tests"
    helpers.mkdir()
    for name in ("capture_auxiliary.py", "capture_backup.py"):
        (helpers / name).write_text("synthetic helper", encoding="utf-8")

    def root():
        return SimpleNamespace(geometry=lambda *_: None, deiconify=lambda: None)

    @contextmanager
    def fake_owner(scale):
        yield root(), []

    def settle(widget):
        assert widget.guarded, "Input protection must exist before first event processing"

    def capture(widget, errors, filename, size, output):
        assert widget.guarded
        if failed:
            raise RuntimeError("Synthetic capture failure")
        return {"file": filename, "requested_size": list(size), "actual_size": list(size),
                "actions": [], "synthetic": True}

    monkeypatch.setattr(capture_appearance, "owned_root", fake_owner)
    monkeypatch.setattr(capture_appearance, "AppearanceGuide", lambda *_: SimpleNamespace(
        root=root(), close=lambda: None,
        canvases={name: SimpleNamespace(winfo_width=lambda: 680, winfo_height=lambda: 240)
                  for name in capture_appearance.TABS}))
    monkeypatch.setattr(capture_appearance, "guard_input", lambda widget, _: setattr(widget, "guarded", True))
    monkeypatch.setattr(capture_appearance, "settle", settle)
    monkeypatch.setattr(capture_appearance, "select_tab", lambda *_: None)
    monkeypatch.setattr(capture_appearance, "start_export", lambda *_: None)
    monkeypatch.setattr(capture_appearance, "finish_export", lambda *_: None)
    monkeypatch.setattr(capture_appearance, "content_bounds", lambda *_: [])
    monkeypatch.setattr(capture_appearance, "tab_bounds", lambda *_: [])
    monkeypatch.setattr(capture_appearance, "capture", capture)
    output = tmp_path / "artifacts" / "new-artwork"
    if failed:
        with pytest.raises(RuntimeError, match="Synthetic capture failure"):
            capture_appearance.capture_all(output)
    else:
        capture_appearance.capture_all(output)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == ("incomplete" if failed else "completed")
    assert "Synthetic" in manifest["scope"]
    assert set(manifest["sources"]) == set(capture_appearance.SOURCE_NAMES)
    assert set(manifest["helpers"]) == {"capture_auxiliary.py", "capture_backup.py"}
    assert all(len(digest) == 64 for digest in (*manifest["sources"].values(), *manifest["helpers"].values()))
    assert tuple(row["file"] for row in manifest["captures"]) == (() if failed else capture_appearance.INVENTORY)
