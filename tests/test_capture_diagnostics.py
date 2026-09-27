"""Guards and receipts for synthetic diagnostic-report captures."""
from contextlib import contextmanager
import json
from pathlib import Path
import queue
import threading
from types import SimpleNamespace

import pytest

import capture_diagnostics as captures
from test_capture_auxiliary import working_tk_display
from utterleaf import config, hardware, polish


def test_inventory_covers_empty_previous_gpu_picker_write_and_large_text():
    assert len(captures.INVENTORY) == len(set(captures.INVENTORY)) == 9
    assert {state for state, _size, scale in captures.CASES if scale == 1.0} == {
        "normal", "success", "error-empty", "error-previous", "gpu-error",
        "save-picker-error", "save-write-error"}
    assert ("error-previous", (760, 560), 2.0) in captures.CASES
    assert ("save-write-error", (760, 560), 2.0) in captures.CASES


def test_runtime_blocks_personal_data_real_probes_network_audio_and_clipboard():
    import socket
    import sounddevice
    import tkinter as tk

    with captures.blocked_runtime() as runtime:
        actions = (
            lambda: config.load(), lambda: config.save(config.Config()),
            lambda: config.config_path(), lambda: config.dictionary_path(),
            lambda: polish.dictionary_text(), lambda: polish.save_dictionary("synthetic = value"),
            lambda: hardware.probe(), lambda: hardware.cuda_runtime_ok(),
            lambda: sounddevice.InputStream(), lambda: sounddevice.query_devices(),
            lambda: socket.socket(), lambda: tk.Misc.clipboard_get(None),
            lambda: tk.Misc.clipboard_append(None, "synthetic"),
        )
        for action in actions:
            with pytest.raises(AssertionError, match="Diagnostic capture blocked"):
                action()
        assert len(runtime.violations) == len(actions)


def test_unexpected_worker_is_blocked_and_expected_real_worker_is_held():
    completed = []
    window = SimpleNamespace(events=queue.Queue())
    with captures.blocked_runtime() as runtime:
        with pytest.raises(AssertionError, match="unexpected worker"):
            threading.Thread(target=lambda: completed.append("unexpected")).start()
        runtime.allow_worker = True
        captures.SettingsWindow._worker(window, lambda: "synthetic", completed.append)
        runtime.allow_worker = False
        assert len(runtime.workers) == 1
        assert completed == [] and window.events.empty()
        runtime.workers.pop()()
        callback, result = window.events.get_nowait()
        callback(result)
        assert completed == ["synthetic"]


def test_public_actions_and_native_dialogs_remain_intercepted():
    from tkinter import filedialog, messagebox

    with captures.blocked_runtime() as runtime:
        for name in captures.REAL_METHODS:
            getattr(captures.SettingsWindow, name)(None)
        assert runtime.blocked_actions == list(captures.REAL_METHODS)
        assert filedialog.askopenfilename() == ""
        assert filedialog.asksaveasfilename() == ""
        messagebox.showerror("Synthetic error", "No native modal")
        assert runtime.dialogs == [("error", "Synthetic error", "No native modal")]


@pytest.mark.parametrize("picker", [False, True])
def test_save_failure_uses_synthetic_picker_and_never_writes(tmp_path, monkeypatch, picker):
    from tkinter import filedialog

    destination = tmp_path / "synthetic-report.txt"

    def exporter(_window):
        path = filedialog.asksaveasfilename()
        Path(path).write_text(captures.REPORT, encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(captures.REAL_METHODS, "export_report", exporter)
    with captures.blocked_runtime() as runtime:
        captures.save_failure(None, runtime, picker=picker)
        assert runtime.uncaught == [{"type": "OSError", "message": captures.ERROR}]
        assert len(runtime.writes) == (0 if picker else 1)
        assert not destination.exists()
        assert not runtime.dialogs


def test_unknown_state_fails_before_touching_any_window_or_action():
    with pytest.raises(ValueError, match="Unknown report capture state"):
        captures.stage(None, None, "not-a-state")


def test_bounds_distinguish_viewport_clipping_and_natural_size():
    def widget(x, y, width, height, requested=(100, 30)):
        return SimpleNamespace(winfo_rootx=lambda: x, winfo_rooty=lambda: y,
            winfo_width=lambda: width, winfo_height=lambda: height,
            winfo_reqwidth=lambda: requested[0], winfo_reqheight=lambda: requested[1],
            winfo_ismapped=lambda: True)

    root = widget(0, 0, 760, 560)
    viewport = widget(290, 64, 430, 368)
    behind_footer = captures.bounds(widget(306, 420, 200, 55), root, clip=viewport)
    assert behind_footer["fits_window"] and not behind_footer["fits_viewport"]
    clipped_label = captures.bounds(widget(306, 80, 200, 55, (220, 70)), root, clip=viewport)
    assert clipped_label["fits_viewport"]
    assert not clipped_label["natural_width"] and not clipped_label["natural_height"]


def test_output_is_exclusive_and_inside_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(captures, "ROOT", tmp_path)
    output = tmp_path / "artifacts" / "existing"
    output.mkdir(parents=True)
    sentinel = output / "before.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    with pytest.raises(FileExistsError):
        captures.capture_all(output)
    assert sentinel.read_text(encoding="utf-8") == "preserve"
    assert list(output.iterdir()) == [sentinel]
    with pytest.raises(ValueError, match="artifacts"):
        captures.capture_all(tmp_path / "outside")
    assert not (tmp_path / "outside").exists()


def test_incomplete_manifest_preserves_source_receipt_when_window_creation_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(captures, "ROOT", tmp_path)
    for folder, names in (("utterleaf", captures.SOURCE_NAMES), ("tests", captures.HELPER_NAMES)):
        parent = tmp_path / folder
        parent.mkdir()
        for name in names:
            (parent / name).write_text("synthetic fixture", encoding="utf-8")

    @contextmanager
    def fail_window(*_args, **_kwargs):
        raise RuntimeError("Synthetic window failure")
        yield  # pragma: no cover - keep the contextmanager generator-shaped

    monkeypatch.setattr(captures, "_window", fail_window)
    output = tmp_path / "artifacts" / "new"
    with pytest.raises(RuntimeError, match="Synthetic window failure"):
        captures.capture_all(output)
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "incomplete" and manifest["captures"] == []
    assert "not certified" in manifest["scope"]
    assert set(manifest["sources"]) == set(captures.SOURCE_NAMES)
    assert set(manifest["helpers"]) == set(captures.HELPER_NAMES)
    assert all(len(digest) == 64 for digest in (
        manifest["harness_sha256"], *manifest["sources"].values(), *manifest["helpers"].values()))


def test_staging_runs_real_report_callbacks_without_hardware_or_draft_changes(working_tk_display):
    with captures.blocked_runtime() as runtime, captures._window(runtime, visible=False) as window:
        before = window._snapshot()
        captures.stage(window, runtime, "success")
        assert window.report == captures.REPORT
        assert window.diagnostic_text.get("1.0", "end-1c") == captures.REPORT
        assert str(window.diagnostic_text.cget("state")) == "disabled"
        assert runtime.probes == ["device"]
        assert runtime.workers == [] and window.events.empty()
        assert window._snapshot() == before
        assert runtime.writes == [] and runtime.dialogs == [] and runtime.violations == []


def test_input_guard_prevents_tcl_copy_and_native_editor_changes(working_tk_display):
    with captures.blocked_runtime() as runtime, captures._window(runtime, visible=False) as window:
        errors = []
        captures.guard_input(window.root, errors)
        window.root.deiconify()
        window.show_page("Help & diagnostics")
        window.root.update()
        captures.stage(window, runtime, "success")
        window.diagnostic_text.focus_force()
        window.root.update()
        before = window.diagnostic_text.get("1.0", "end-1c")
        window.diagnostic_text.tag_add("sel", "1.0", "end-1c")
        window.diagnostic_text.event_generate("<<Copy>>")
        window.diagnostic_text.event_generate("<KeyPress>", keysym="x")
        window.root.update()
        assert len(errors) == 2
        assert window.diagnostic_text.get("1.0", "end-1c") == before
        assert not runtime.violations
