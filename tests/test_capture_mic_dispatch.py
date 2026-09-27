"""Isolation, inventory and framing for synthetic Settings dispatch failures."""
from contextlib import contextmanager
import json
from types import SimpleNamespace

import pytest

import capture_mic_dispatch as captures
from test_capture_auxiliary import working_tk_display


def test_inventory_has_three_checks_at_standard_and_double_text_scale():
    assert len(captures.INVENTORY) == len(set(captures.INVENTORY)) == 6
    for scale in (1.0, 2.0):
        assert {name for name, _size, value in captures.CASES if value == scale} == {
            "refresh_mics", "test_mic", "refresh_connection"}


def test_guard_denies_enumeration_recording_ipc_and_personal_settings():
    from utterleaf import audio, config, ipc

    with captures.blocked_runtime() as runtime:
        for action in (audio.list_input_names, audio.Recorder, config.load, lambda: ipc.send("status")):
            with pytest.raises(AssertionError, match="capture blocked"):
                action()
        assert len(runtime.violations) == 4
        assert runtime.workers == [] and runtime.ipc_commands == []


def test_public_handlers_remain_blocked_outside_saved_staging_references():
    with captures.blocked_runtime() as runtime:
        for name in captures.REAL_METHODS:
            getattr(captures.SettingsWindow, name)(None)
        assert runtime.blocked_actions == list(captures.REAL_METHODS)
        assert runtime.start_attempts == 0


def test_unknown_state_is_rejected_before_touching_any_control():
    with pytest.raises(ValueError, match="Unknown dispatch capture state"):
        captures.stage(None, None, "unknown")


@pytest.mark.parametrize("viewport_height,whole_group_fits", [(300, True), (80, False)])
def test_framing_includes_actual_retry_or_honestly_records_insufficient_space(monkeypatch, viewport_height, whole_group_fits):
    label = SimpleNamespace(winfo_rooty=lambda: 300, winfo_height=lambda: 100)
    retry = SimpleNamespace(winfo_rooty=lambda: 260, winfo_height=lambda: 35)
    positions = []
    window = SimpleNamespace(canvas=SimpleNamespace(
        bbox=lambda *_: (0, 0, 500, 1000), winfo_rooty=lambda: 64,
        winfo_height=lambda: viewport_height, canvasy=lambda *_: 0, yview_moveto=positions.append))
    monkeypatch.setattr(captures, "message_label", lambda *_: label)
    monkeypatch.setattr(captures, "landing_refresh", lambda *_: retry)
    result = captures.align_feedback(window, "refresh_connection")
    assert result == {"group_height": 140, "viewport_height": viewport_height,
                      "whole_group_fits": whole_group_fits}
    assert positions == [(260 - 64 - 12) / 1000 if whole_group_fits else (300 - 64 - 12) / 1000]


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


def test_failed_capture_retains_source_hashed_incomplete_manifest(tmp_path, monkeypatch):
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


@pytest.mark.parametrize("name", captures.REAL_METHODS)
def test_real_handler_dispatch_never_runs_a_probe_or_changes_draft(working_tk_display, name):
    with captures.blocked_runtime() as runtime, captures._window(runtime, visible=False) as window:
        snapshot, baseline = captures.stage(window, runtime, name)
        assert runtime.start_attempts == 1
        assert window._snapshot() == snapshot and window.baseline == baseline
        assert window.events.empty() and not runtime.workers
        assert not runtime.violations and not runtime.blocked_actions
        assert runtime.dialogs == [] and runtime.ipc_commands == []
