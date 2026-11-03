"""Inventory, isolation and receipts for synthetic Settings-save captures."""
from contextlib import contextmanager
import json
import threading

import pytest

import capture_save_recovery as captures
from test_capture_auxiliary import working_tk_display
from utterleaf import config, settings, startup


def test_inventory_covers_all_save_stages_and_compact_partial_unknown_states():
    assert len(captures.INVENTORY) == len(set(captures.INVENTORY)) == 10
    assert {state for state, _size, scale in captures.CASES if scale == 1.0} == set(captures.STATES)
    assert ("vocabulary-failure", (760, 560), 2.0) in captures.CASES
    assert ("unknown-failure", (760, 560), 2.0) in captures.CASES
    assert all(name.endswith("-post-alert.png") for name in captures.INVENTORY)


@pytest.mark.parametrize("state,saved,failed,pending", [
    ("config-failure", (), "dictation settings", ("vocabulary", "start at login")),
    ("vocabulary-failure", ("dictation settings",), "vocabulary", ("start at login",)),
    ("startup-failure", ("dictation settings", "vocabulary"), "start at login", ()),
    ("partial-reload-failure", ("dictation settings",), "vocabulary", ("start at login",)),
])
def test_structured_fixtures_retain_exact_durable_stage_facts(state, saved, failed, pending):
    error = captures.failure_for(state)
    assert isinstance(error, settings.SettingsSaveError)
    assert (error.saved, error.failed, error.pending) == (saved, failed, pending)
    assert captures.ERROR in str(error)


def test_runtime_blocks_real_persistence_aliases_and_personal_config():
    with captures.blocked_runtime() as runtime:
        actions = (
            lambda: config.load(), lambda: config.save(config.Config()),
            lambda: settings.save(config.Config()), lambda: settings.save_dictionary("synthetic = value"),
            lambda: settings.set_startup(True), lambda: startup.set_enabled(True),
        )
        for action in actions:
            with pytest.raises(AssertionError, match="capture blocked"):
                action()
        assert len(runtime.violations) == len(actions)


def test_public_save_stays_blocked_and_unexpected_workers_never_start():
    completed = []
    with captures.blocked_runtime() as runtime:
        captures.SettingsWindow.save(None)
        assert runtime.blocked_actions == ["save"]
        with pytest.raises(AssertionError, match="unexpected worker"):
            threading.Thread(target=lambda: completed.append(True)).start()
        assert completed == [] and runtime.workers == []


def test_all_native_save_alert_types_are_intercepted():
    from tkinter import messagebox

    with captures.blocked_runtime() as runtime:
        messagebox.showerror("Synthetic error", "No native dialog")
        messagebox.showwarning("Synthetic warning", "No native dialog")
        messagebox.showinfo("Synthetic details", "No native dialog")
        assert runtime.dialogs == [
            ("error", "Synthetic error", "No native dialog"),
            ("warning", "Synthetic warning", "No native dialog"),
            ("info", "Synthetic details", "No native dialog"),
        ]


def test_unknown_capture_state_fails_before_touching_window():
    with pytest.raises(ValueError, match="Unknown save capture state"):
        captures.stage(None, None, "not-a-save-state")


def test_output_is_exclusive_and_inside_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(captures, "ROOT", tmp_path)
    output = tmp_path / "artifacts" / "before"
    output.mkdir(parents=True)
    sentinel = output / "preserve.txt"
    sentinel.write_text("existing receipt", encoding="utf-8")
    with pytest.raises(FileExistsError):
        captures.capture_all(output)
    assert sentinel.read_text(encoding="utf-8") == "existing receipt"
    assert list(output.iterdir()) == [sentinel]
    with pytest.raises(ValueError, match="artifacts"):
        captures.capture_all(tmp_path / "outside")
    assert not (tmp_path / "outside").exists()


def test_failed_capture_retains_hashed_incomplete_receipt(tmp_path, monkeypatch):
    monkeypatch.setattr(captures, "ROOT", tmp_path)
    for folder, names in (("utterleaf", (*captures.SOURCE_NAMES, "save_presentation.py")),
                          ("tests", captures.HELPER_NAMES)):
        parent = tmp_path / folder
        parent.mkdir()
        for name in names:
            (parent / name).write_text("synthetic fixture", encoding="utf-8")

    @contextmanager
    def fail_window(*_args, **_kwargs):
        raise RuntimeError("Synthetic creation failure")
        yield  # pragma: no cover - contextmanager generator

    monkeypatch.setattr(captures, "_window", fail_window)
    output = tmp_path / "artifacts" / "new"
    with pytest.raises(RuntimeError, match="Synthetic creation failure"):
        captures.capture_all(output)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "incomplete" and not manifest["captures"]
    assert "not certified" in manifest["scope"]
    assert set(manifest["sources"]) == {*captures.SOURCE_NAMES, "save_presentation.py"}
    assert set(manifest["helpers"]) == set(captures.HELPER_NAMES)
    assert all(len(digest) == 64 for digest in (
        manifest["harness_sha256"], *manifest["sources"].values(), *manifest["helpers"].values()))


@pytest.mark.parametrize("state", ["vocabulary-failure", "full-reload-failure"])
def test_staging_uses_real_held_save_worker_without_mutating_draft(working_tk_display, state):
    with captures.blocked_runtime() as runtime, captures._window(runtime, visible=False) as window:
        original_beep = window.vars["beep"].get()
        draft = captures.stage(window, runtime, state)
        assert window.vars["beep"].get() is not original_beep
        assert window._snapshot() == draft
        assert runtime.apply_calls == [draft]
        assert runtime.ipc_commands == ["reload"]
        assert window.events.empty() and not runtime.workers
        assert not window.saving
        assert not runtime.violations and not runtime.blocked_actions
        assert len(runtime.dialogs) == 1
