"""Guard coverage and receipt checks for last-checked model snapshots."""
from contextlib import contextmanager
import json
from types import SimpleNamespace

import pytest

import capture_loaded_model as captures
from test_capture_auxiliary import working_tk_display


def test_inventory_has_six_states_at_standard_and_double_scale():
    assert len(captures.CASES) == 12
    assert len(set(captures.CASES)) == 12
    for scale in (1.0, 2.0):
        assert {state for state, _size, value in captures.CASES if value == scale} == set(captures.STATES)


def test_guard_blocks_live_ipc_model_inventory_microphone_and_preferences():
    from utterleaf import audio, config, ipc, model_inventory

    with captures.blocked_runtime() as runtime:
        for action in (lambda: ipc.send("status-detail", exact_reply=True), model_inventory.inventory_models,
                       audio.Recorder, config.load):
            with pytest.raises(AssertionError, match="capture blocked"):
                action()
        assert len(runtime.violations) == 4
        assert runtime.status_calls == runtime.workers == []


def test_public_refresh_remains_blocked_outside_saved_real_reference():
    with captures.blocked_runtime() as runtime:
        captures.SettingsWindow.refresh_connection(None)
        assert runtime.blocked_actions == ["refresh_connection"]
        assert runtime.status_calls == []


def test_unknown_capture_state_rejected_before_touching_controls():
    with pytest.raises(ValueError, match="Unknown loaded-model capture state"):
        captures.stage(None, None, "unknown")


def test_manual_framing_includes_last_checked_heading_and_action_when_they_fit(monkeypatch):
    words = SimpleNamespace(winfo_rooty=lambda: 200, winfo_height=lambda: 160)
    label = SimpleNamespace(master=words, winfo_rooty=lambda: 240)
    button = SimpleNamespace(winfo_rooty=lambda: 370, winfo_height=lambda: 55)
    positions = []
    window = SimpleNamespace(canvas=SimpleNamespace(winfo_height=lambda: 414, winfo_rooty=lambda: 64,
        canvasy=lambda *_: 0, bbox=lambda *_: (0, 0, 500, 1000), yview_moveto=positions.append))
    monkeypatch.setattr(captures, "message_label", lambda *_: label)
    monkeypatch.setattr(captures, "landing_refresh", lambda *_: button)
    assert captures.frame_status(window) == {"group_height": 225, "viewport_height": 414,
        "whole_group_fits": True, "includes_last_checked_heading": True}
    assert positions == [(200 - 64 - 12) / 1000]


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


def test_failed_capture_keeps_incomplete_hashed_receipt(tmp_path, monkeypatch):
    monkeypatch.setattr(captures, "ROOT", tmp_path)
    for folder, names in (("utterleaf", captures.SOURCE_NAMES), ("tests", captures.HELPER_NAMES)):
        parent = tmp_path / folder
        parent.mkdir()
        for name in names:
            (parent / name).write_text("synthetic fixture", encoding="utf-8")

    @contextmanager
    def fail_window(*_args, **_kwargs):
        raise RuntimeError("Synthetic window failure")
        yield  # pragma: no cover

    monkeypatch.setattr(captures, "_window", fail_window)
    output = tmp_path / "artifacts" / "new"
    with pytest.raises(RuntimeError, match="Synthetic window failure"):
        captures.capture_all(output)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "incomplete" and manifest["captures"] == []
    assert set(manifest["sources"]) == set(captures.SOURCE_NAMES)
    assert set(manifest["helpers"]) == set(captures.HELPER_NAMES)
    assert all(len(value) == 64 for value in (
        manifest["harness_sha256"], *manifest["sources"].values(), *manifest["helpers"].values()))


@pytest.mark.parametrize("state", captures.STATES)
def test_saved_real_worker_staging_is_bounded_safe_and_draft_preserving(working_tk_display, state):
    with captures.blocked_runtime() as runtime, captures._window(runtime, visible=False) as window:
        snapshot, baseline = captures.stage(window, runtime, state)
        expected = [("status-detail", {"exact_reply": True})]
        if state == "old-version":
            expected.append(("status", {}))
        elif state == "error-retry":
            expected *= 2
        assert runtime.status_calls == expected
        assert window._snapshot() == snapshot and window.baseline == baseline
        assert not window.checking_connection and not window.connection_button.instate(["disabled"])
        assert runtime.violations == runtime.blocked_actions == runtime.ipc_commands == runtime.dialogs == []
        assert window.events.empty() and runtime.workers == []
        text = window.connection.get()
        assert "/synthetic/private" not in text and "status-v2" not in text
        if state == "ready-english":
            assert "Tiny English" in text
        elif state == "ready-custom":
            assert "Custom model" in text
        elif state == "listening-unconfirmed":
            assert "Listening" in text and "not confirmed" in text
        elif state == "old-version":
            assert "Ready" in text and "unavailable in this version" in text
        else:
            assert "Tiny English" not in text and "retry" in text.lower()
