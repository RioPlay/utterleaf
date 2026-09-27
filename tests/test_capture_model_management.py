"""Isolation and auditable receipts for model-management captures."""
from contextlib import contextmanager
import json

import pytest

import capture_model_management as captures
from test_capture_auxiliary import working_tk_display


def test_inventory_is_explicit_and_unique_at_standard_and_double_scale():
    assert len(captures.INVENTORY) == len(set(captures.INVENTORY)) == 20
    for scale in (1.0, 2.0):
        assert {state for state, _size, value in captures.CASES if value == scale} == set(
            captures.DOWNLOAD_STATES + captures.INVENTORY_STATES)


def test_guard_denies_real_store_scan_audio_ipc_and_preferences():
    from utterleaf import audio, config, ipc, model_inventory, models

    with captures.blocked_runtime() as runtime:
        for action in (config.models_dir, models.models_dir, model_inventory.inventory_models,
                       audio.Recorder, config.load, lambda: ipc.send("reload")):
            with pytest.raises(AssertionError, match="capture blocked"):
                action()
        assert len(runtime.violations) == 6
        assert runtime.download_calls == [] and runtime.workers == []
        assert runtime.ipc_commands == []


def test_public_download_remains_blocked_outside_saved_staging_reference():
    with captures.blocked_runtime() as runtime:
        captures.SettingsWindow.download_model(None)
        captures.ModelInventoryPanel.refresh(None)
        assert runtime.blocked_actions == ["download_model", "inventory_refresh"]
        assert runtime.start_attempts == 0 and runtime.download_calls == []


def test_unknown_state_rejected_before_touching_window():
    with pytest.raises(ValueError, match="Unknown model capture state"):
        captures.stage(None, None, "unknown")


def test_output_is_exclusive_and_artifacts_only(tmp_path, monkeypatch):
    monkeypatch.setattr(captures, "ROOT", tmp_path)
    output = tmp_path / "artifacts" / "existing"
    output.mkdir(parents=True)
    sentinel = output / "keep.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    with pytest.raises(FileExistsError):
        captures.capture_all(output)
    assert sentinel.read_text(encoding="utf-8") == "preserve"
    assert list(output.iterdir()) == [sentinel]
    with pytest.raises(ValueError, match="artifacts"):
        captures.capture_all(tmp_path / "outside")


def test_failed_window_retains_incomplete_source_hashed_receipt(tmp_path, monkeypatch):
    monkeypatch.setattr(captures, "ROOT", tmp_path)
    for folder, names in (("utterleaf", captures.SOURCE_NAMES), ("tests", captures.HELPER_NAMES)):
        parent = tmp_path / folder
        parent.mkdir()
        for name in names:
            (parent / name).write_text("synthetic fixture", encoding="utf-8")

    @contextmanager
    def fail_window(*_args, **_kwargs):
        raise RuntimeError("Synthetic window failure")
        yield  # pragma: no cover - contextmanager generator

    monkeypatch.setattr(captures, "_window", fail_window)
    output = tmp_path / "artifacts" / "new"
    with pytest.raises(RuntimeError, match="Synthetic window failure"):
        captures.capture_all(output)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "incomplete" and manifest["captures"] == []
    assert set(manifest["sources"]) == set(captures.SOURCE_NAMES)
    assert set(manifest["helpers"]) == set(captures.HELPER_NAMES)
    assert all(len(digest) == 64 for digest in (
        manifest["harness_sha256"], *manifest["sources"].values(), *manifest["helpers"].values()))


@pytest.mark.parametrize("state", captures.DOWNLOAD_STATES)
def test_staging_runs_saved_real_worker_and_preserves_draft_without_external_io(working_tk_display, state):
    with captures.blocked_runtime() as runtime, captures._window(runtime, visible=False) as window:
        snapshot, baseline = captures.stage(window, runtime, state)
        assert window._snapshot() == snapshot and window.baseline == baseline
        assert window.events.empty() and runtime.workers == []
        assert runtime.violations == runtime.blocked_actions == runtime.ipc_commands == []
        assert runtime.start_attempts == (0 if state == "empty" else 1)
        assert runtime.worker_daemons == ([] if state == "empty" else [False])
        if state in {"cancelled", "failure", "installed"}:
            assert runtime.download_calls == [("tiny.en", "ctranslate2", state == "cancelled")]
        else:
            assert runtime.download_calls == []
        assert len(runtime.dialogs) == (0 if state == "empty" else 1)
        assert all(kind == "question" for kind, _title, _message in runtime.dialogs)
        assert runtime.uncaught == []
        assert not window.model_downloading
        if state == "installed":
            assert "Tiny English installed" in window.model_action_status.get()
        elif state == "cancelled":
            assert "cancelled" in window.model_action_status.get().lower()
        elif state == "failure":
            assert "did not finish" in window.model_action_status.get().lower()
            assert captures.ERROR not in window.model_action_status.get()


@pytest.mark.parametrize("state", captures.INVENTORY_STATES)
def test_inventory_capture_uses_held_real_worker_without_store_or_preference_access(working_tk_display, state):
    with captures.blocked_runtime() as runtime, captures._window(runtime, visible=False) as window:
        assert runtime.inventory_scan_calls == []
        snapshot, baseline = captures.stage(window, runtime, state)
        panel = window.model_inventory
        assert window._snapshot() == snapshot and window.baseline == baseline
        assert window.events.empty() and runtime.workers == []
        assert runtime.violations == runtime.blocked_actions == runtime.ipc_commands == []
        assert runtime.uncaught == runtime.dialogs == runtime.download_calls == []
        assert runtime.start_attempts == 1 and runtime.worker_daemons == [True]
        assert panel._operation is None
        assert str(panel.refresh_button.cget("state")) == "normal"
        assert captures.ERROR not in panel.status.get() + panel.selected_text.get() + panel.size_text.get()
        if state == "inventory-start-failure":
            assert runtime.inventory_scan_calls == [] and panel.entries == ()
            assert "could not start" in panel.status.get()
            assert panel.feedback.details
        else:
            assert runtime.inventory_scan_calls == [state]
            if state == "inventory-empty":
                assert panel.entries == () and "No guided local installations" in panel.status.get()
            else:
                assert len(panel.entries) == 1
                expected = "error" if state == "inventory-read-error" else state.removeprefix("inventory-")
                assert panel.entries[0].state == expected
                if expected == "error":
                    assert panel.feedback.details and "unknown" in panel.size_text.get()
                else:
                    assert not panel.feedback.details and "Setup file size" in panel.size_text.get()
