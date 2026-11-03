"""Guards and receipts for the synthetic OBS pairing-dialog baseline."""
from contextlib import contextmanager
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import capture_obs_pairing as captures
from test_capture_auxiliary import working_tk_display
from utterleaf import config, obs_pairing_store


def test_inventory_covers_pairing_busy_failure_recovery_and_large_text():
    assert len(captures.INVENTORY) == len(set(captures.INVENTORY)) == 10
    states = {state for state, _size, scale in captures.CASES if scale == 1.0}
    assert states == {
        "unpaired", "paired", "importing", "cancelling", "file-error",
        "uncertain", "storage-unavailable", "saved-file-kept",
    }
    assert ("file-error", (450, 460), 2.0) in captures.CASES
    assert ("storage-unavailable", (450, 460), 2.0) in captures.CASES


def test_guard_blocks_pairing_store_preferences_network_audio_clipboard_and_dialogs():
    import socket
    import sounddevice
    import tkinter as tk
    from tkinter import filedialog, messagebox

    store = object.__new__(obs_pairing_store.ObsPairingStore)
    with captures.blocked_runtime() as runtime:
        actions = (
            lambda: config.load(), lambda: config.save(config.Config()),
            lambda: store.__enter__(), lambda: store.claim_owner(), lambda: store.load(),
            lambda: store.import_package("synthetic.ulobs", replace=False, cancelled=lambda: False),
            lambda: store.forget(), lambda: socket.socket(), lambda: sounddevice.InputStream(),
            lambda: tk.Misc.clipboard_get(None), lambda: tk.Misc.clipboard_append(None, "synthetic"),
            lambda: filedialog.askopenfilename(),
            lambda: messagebox.askyesno("Synthetic", "Do not open"),
        )
        for action in actions:
            with pytest.raises(AssertionError, match="OBS pairing capture blocked"):
                action()
        assert len(runtime.violations) == len(actions)


def test_only_named_pairing_worker_is_held_and_never_runs():
    import threading

    called = []
    with captures.blocked_runtime() as runtime:
        pairing = threading.Thread(target=lambda: called.append(True), name="obs-pairing-setup")
        pairing.start()
        with pytest.raises(AssertionError, match="unexpected worker"):
            threading.Thread(target=lambda: None, name="other-worker").start()
        assert runtime.workers == [pairing]
        assert called == []


@pytest.mark.parametrize("state", sorted({case[0] for case in captures.CASES}))
def test_staging_uses_only_synthetic_outcomes(state, working_tk_display):
    with captures.blocked_runtime() as runtime, captures.owned_root() as (owner, errors):
        dialog = captures.stage_dialog(owner, state)
        try:
            owner.update()
            assert len(runtime.workers) == 1
            assert not runtime.violations and not errors
            assert "synthetic" not in dialog.status.get().lower()
            if state == "unpaired":
                assert dialog.paired is False and dialog.state.get() == "Not paired"
            elif state == "paired":
                assert dialog.paired is True and dialog.state.get() == "Pairing saved"
            elif state in {"importing", "cancelling"}:
                assert dialog.busy and dialog.cancel_button.winfo_manager() == "pack"
                assert "pairing" in dialog.status.get().lower() or "cancell" in dialog.status.get().lower()
            elif state == "storage-unavailable":
                assert dialog.paired is None and dialog.refresh_button.cget("text") == "Retry"
            elif state == "saved-file-kept":
                assert dialog.paired is True and "file remains" in dialog.status.get()
            else:
                assert dialog.paired is None and dialog.state.get() == "Pairing needs attention"
        finally:
            dialog.root.destroy()


def test_unknown_state_fails_before_building_dialog():
    with pytest.raises(ValueError, match="Unknown OBS pairing capture state"):
        captures.stage_dialog(None, "unknown")


@pytest.mark.parametrize("state", ["file-error", "storage-unavailable"])
def test_compact_large_text_keeps_footer_actions_visible(state, working_tk_display):
    with captures.blocked_runtime(), captures.owned_root(2.0) as (owner, errors):
        owner.geometry("1x1+5+5")
        owner.deiconify()
        dialog = captures.stage_dialog(owner, state)
        try:
            dialog.root.geometry("450x460")
            dialog.root.deiconify()
            captures.settle(dialog.root)
            assert not errors
            root_right = dialog.root.winfo_rootx() + dialog.root.winfo_width()
            root_bottom = dialog.root.winfo_rooty() + dialog.root.winfo_height()
            for button in (dialog.refresh_button, dialog.forget_button, dialog.close_button):
                assert button.winfo_ismapped()
                assert button.winfo_rootx() >= dialog.root.winfo_rootx()
                assert button.winfo_rootx() + button.winfo_width() <= root_right
                assert button.winfo_rooty() + button.winfo_height() <= root_bottom
            assert dialog.canvas.winfo_height() >= 64
        finally:
            dialog.root.destroy()


def test_output_is_exclusive_and_inside_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(captures, "ROOT", tmp_path)
    existing = tmp_path / "artifacts" / "keep"
    existing.mkdir(parents=True)
    sentinel = existing / "original.txt"
    sentinel.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        captures.capture_all(existing)
    assert sentinel.read_text(encoding="utf-8") == "keep"
    assert list(existing.iterdir()) == [sentinel]
    with pytest.raises(ValueError, match="artifacts"):
        captures.capture_all(tmp_path / "outside")
    assert not (tmp_path / "outside").exists()


@pytest.mark.parametrize("failed", [False, True])
def test_manifest_preserves_receipts_and_complete_or_incomplete_inventory(
        tmp_path, monkeypatch, failed):
    monkeypatch.setattr(captures, "ROOT", tmp_path)
    for folder, names in (("utterleaf", captures.SOURCE_NAMES), ("tests", captures.HELPER_NAMES)):
        parent = tmp_path / folder
        parent.mkdir()
        for name in names:
            (parent / name).write_text("synthetic source", encoding="utf-8")

    @contextmanager
    def fake_root(scale=1.0):
        root = SimpleNamespace(
            scale=scale, geometry=lambda *_: None, deiconify=lambda: None,
            destroy=lambda: None,
        )
        yield root, []

    class FakeDialog:
        root = SimpleNamespace(
            geometry=lambda *_: None, deiconify=lambda: None, destroy=lambda: None
        )
        status_label = object()
        state = SimpleNamespace(get=lambda: "Synthetic state")
        status = SimpleNamespace(get=lambda: "Synthetic status")
        _reveal = lambda *_: None

    monkeypatch.setattr(captures, "owned_root", fake_root)
    monkeypatch.setattr(captures, "settle", lambda *_: None)
    monkeypatch.setattr(captures, "guard_input", lambda *_: None)
    monkeypatch.setattr(captures, "stage_dialog", lambda *_: FakeDialog())
    monkeypatch.setattr(captures, "action_receipt", lambda *_: {})

    calls = []
    def fake_capture(root, errors, filename, size, output):
        if failed:
            raise RuntimeError("Synthetic capture failure")
        calls.append(filename)
        return {"file": filename, "requested_size": list(size), "synthetic": True}
    monkeypatch.setattr(captures, "capture", fake_capture)

    class Workers(list):
        def __len__(self):
            return len(captures.CASES)

    @contextmanager
    def fake_runtime():
        yield SimpleNamespace(violations=[], workers=Workers())
    monkeypatch.setattr(captures, "blocked_runtime", fake_runtime)

    output = tmp_path / "artifacts" / "new"
    if failed:
        with pytest.raises(RuntimeError, match="Synthetic capture failure"):
            captures.capture_all(output)
    else:
        captures.capture_all(output)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == ("incomplete" if failed else "completed")
    assert "no pairing store" in manifest["scope"]
    assert set(manifest["sources"]) == set(captures.SOURCE_NAMES)
    assert set(manifest["helpers"]) == set(captures.HELPER_NAMES)
    assert all(len(digest) == 64 for digest in (
        manifest["harness_sha256"], *manifest["sources"].values(), *manifest["helpers"].values()
    ))
    assert tuple(calls) == (() if failed else captures.INVENTORY)
