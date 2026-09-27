"""Guarded model-management evidence; no model store, download or native consent UI."""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
import hashlib
import json
from pathlib import Path
import sys
import threading
from unittest.mock import patch

from capture_auxiliary import capture, settle
from capture_backup import descendants, guard_input
from capture_diagnostics import bounds
from capture_mic_dispatch import blocked_runtime as guarded_runtime
from capture_settings import _window
from utterleaf.config import Config
from utterleaf.model_inventory import ModelInstallation
from utterleaf.model_inventory_ui import ModelInventoryPanel
from utterleaf.settings_ui import SettingsWindow, enable_dpi_awareness

ROOT = Path(__file__).resolve().parents[1]
ERROR = "Synthetic model operation failure: /synthetic/private/model.bin"
REAL_DOWNLOAD = SettingsWindow.download_model
REAL_REFRESH = ModelInventoryPanel.refresh
DOWNLOAD_STATES = ("start-failure", "cancelled", "failure", "installed", "empty")
INVENTORY_STATES = ("inventory-installed", "inventory-incomplete", "inventory-empty",
                    "inventory-read-error", "inventory-start-failure")
CASES = tuple((state, size, scale) for size, scale in (((960, 780), 1.0), ((760, 560), 2.0))
              for state in DOWNLOAD_STATES + INVENTORY_STATES)
INVENTORY = tuple(f"model-{state}-{size[0]}x{size[1]}-{scale:g}x.png" for state, size, scale in CASES)
SOURCE_NAMES = ("settings_ui.py", "model_setup.py", "model_inventory.py", "model_inventory_ui.py",
                "model_presentation.py", "ui_feedback.py", "ui_layout.py", "theme.py")
HELPER_NAMES = ("capture_settings.py", "capture_mic_dispatch.py", "capture_diagnostics.py", "capture_auxiliary.py", "capture_backup.py")


@contextmanager
def blocked_runtime():
    with guarded_runtime() as runtime, ExitStack() as stack:
        runtime.download_calls = []
        runtime.worker_daemons = []
        runtime.inventory_scan_calls = []

        def deny(name):
            def blocked(*_args, **_kwargs):
                runtime.violations.append(name)
                raise AssertionError(f"Model capture blocked {name}")
            return blocked

        for name in ("utterleaf.config.models_dir", "utterleaf.models.models_dir",
                     "utterleaf.model_inventory.inventory_models"):
            stack.enter_context(patch(name, side_effect=deny(name)))
        stack.enter_context(patch.object(ModelInventoryPanel, "refresh",
            lambda *_args: runtime.blocked_actions.append("inventory_refresh")))
        yield runtime


def stage(window, runtime, state):
    """Exercise real dispatch/worker/completion with one strictly synthetic action."""
    if state not in DOWNLOAD_STATES + INVENTORY_STATES:
        raise ValueError(f"Unknown model capture state: {state}")
    window.vars["model"].set("tiny")
    window.vars["language"].set("en")
    window.vars["device"].set("cpu")
    window.vars["allow_network"].set(False)
    window.vars["beep"].set(not window.vars["beep"].get())
    window.show_page("Engine")
    settle(window.root)
    snapshot, baseline = window._snapshot(), window.baseline.copy()
    if state in INVENTORY_STATES:
        stage_inventory(window, runtime, state)
        if window._snapshot() != snapshot or window.baseline != baseline:
            raise AssertionError("Inventory changed the Settings draft or baseline")
        return snapshot, baseline
    if state == "empty":
        return snapshot, baseline

    def start(thread):
        runtime.start_attempts += 1
        runtime.worker_daemons.append(thread.daemon)
        if state == "start-failure":
            raise RuntimeError(ERROR)
        runtime.workers.append(thread._target)

    def download(name, backend, *, cancel):
        runtime.download_calls.append((name, backend, cancel.is_set()))
        if (name, backend) != ("tiny.en", "ctranslate2"):
            raise AssertionError("The staged download identity changed")
        runtime.model_state = "installed" if state == "installed" else "incomplete"
        if state != "installed":
            raise RuntimeError(ERROR)

    runtime.confirm = True
    try:
        with patch("utterleaf.model_setup.run_download", side_effect=download), \
                patch.object(threading.Thread, "start", start):
            try:
                REAL_DOWNLOAD(window)
            except RuntimeError as exc:
                if str(exc) != ERROR:
                    raise
                runtime.uncaught.append({"type": type(exc).__name__, "message": str(exc)})
    finally:
        runtime.confirm = False
    if state != "start-failure":
        if len(runtime.workers) != 1:
            raise AssertionError("Expected exactly one held model worker")
        if state == "cancelled":
            window.cancel_model_download()
        with patch("utterleaf.model_setup.run_download", side_effect=download):
            runtime.workers.pop()()
        callback, value = window.events.get_nowait()
        callback(value)
        if runtime.download_calls[-1:] != [("tiny.en", "ctranslate2", state == "cancelled")]:
            raise AssertionError("Expected the saved production worker to run the synthetic download")
    if runtime.workers or not window.events.empty():
        raise AssertionError("Unexpected pending model work")
    if window._snapshot() != snapshot or window.baseline != baseline:
        raise AssertionError("Model operation changed the Settings draft or baseline")
    return snapshot, baseline


def stage_inventory(window, runtime, state):
    """Keep the panel's real worker/result path; replace only its filesystem probe."""
    def start(thread):
        runtime.start_attempts += 1
        runtime.worker_daemons.append(thread.daemon)
        if state == "inventory-start-failure":
            raise RuntimeError(ERROR)
        runtime.workers.append(thread._target)

    def scan():
        runtime.inventory_scan_calls.append(state)
        rows = {
            "inventory-installed": (ModelInstallation("tiny.en", "ctranslate2", "installed", 75_123_456),),
            "inventory-incomplete": (ModelInstallation("tiny.en", "ctranslate2", "incomplete", 12_345),),
            "inventory-empty": (),
            "inventory-read-error": (ModelInstallation("tiny.en", "ctranslate2", "error", None, ERROR),),
        }
        return rows[state]

    before = len(runtime.inventory_scan_calls)
    with patch("utterleaf.model_inventory.inventory_models", side_effect=scan), \
            patch.object(threading.Thread, "start", start):
        REAL_REFRESH(window.model_inventory)
        if state != "inventory-start-failure":
            if len(runtime.workers) != 1:
                raise AssertionError("Expected exactly one held inventory worker")
            runtime.workers.pop()()
            callback, value = window.events.get_nowait()
            callback(value)
    if len(runtime.inventory_scan_calls) != before + (state != "inventory-start-failure"):
        raise AssertionError("Expected the synthetic inventory probe only after successful dispatch")
    if runtime.workers or not window.events.empty():
        raise AssertionError("Unexpected pending inventory work")


def variable_label(window, variable):
    return next(widget for widget in descendants(window.pages["Engine"])
                if "textvariable" in widget.keys() and str(widget.cget("textvariable")) == str(variable))


def frame_model(window, state):
    """Manual screenshot framing, not evidence of automatic focus/reveal."""
    if state in INVENTORY_STATES:
        panel = window.model_inventory
        label = panel.selected_label if state in {"inventory-installed", "inventory-incomplete"} else panel.feedback
        group = [getattr(panel, key) for key in ("refresh_button", "model_picker", "selected_label", "size_label",
                 "size_hint", "reason_label", "use_button", "feedback") if getattr(panel, key).winfo_ismapped()]
    else:
        label = variable_label(window, window.model_action_status)
        group = [label, window.model_download_button, window.model_cancel_button]
        if window.model_details_button.winfo_ismapped():
            group.append(window.model_details_button)
        if not window.model_action_status.get():
            group.append(variable_label(window, window.model_status))
    top = min(widget.winfo_rooty() for widget in group)
    bottom = max(widget.winfo_rooty() + widget.winfo_height() for widget in group)
    fits = bottom - top + 24 <= window.canvas.winfo_height()
    anchor = top if fits else label.winfo_rooty()
    region = window.canvas.bbox("all")
    y = anchor - window.canvas.winfo_rooty() + window.canvas.canvasy(0)
    window.canvas.yview_moveto(max(0, y - 12) / max(1, region[3] - region[1]))
    return {"group_height": bottom - top, "viewport_height": window.canvas.winfo_height(), "whole_group_fits": fits}


def capture_all(output):
    output = output.resolve()
    if not output.is_relative_to(ROOT / "artifacts"):
        raise ValueError("Capture output must stay inside this checkout's artifacts directory")
    output.mkdir(parents=True, exist_ok=False)
    manifest = {"scope": "Synthetic model operation; manually framed. Consent dialogs intercepted, not visually certified. No local store or network access.",
        "platform": sys.platform, "python": sys.version.split()[0],
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "sources": {name: hashlib.sha256((ROOT / "utterleaf" / name).read_bytes()).hexdigest() for name in SOURCE_NAMES},
        "helpers": {name: hashlib.sha256((ROOT / "tests" / name).read_bytes()).hexdigest() for name in HELPER_NAMES},
        "captures": [], "status": "incomplete"}
    try:
        with blocked_runtime() as runtime:
            for (state, size, scale), filename in zip(CASES, INVENTORY):
                with _window(runtime, cfg=Config(), visible=False, text_scale=scale) as window:
                    errors = []
                    window.root.report_callback_exception = lambda kind, value, trace: errors.append(str(value))
                    guard_input(window.root, errors)
                    window.root.geometry(f"{size[0]}x{size[1]}+70+50")
                    window.root.deiconify()
                    settle(window.root)
                    starts = len(runtime.uncaught), len(runtime.dialogs), len(runtime.download_calls), len(runtime.worker_daemons)
                    snapshot, baseline = stage(window, runtime, state)
                    settle(window.root)
                    framing = frame_model(window, state)
                    settle(window.root)
                    record = capture(window.root, errors, filename, size, output)
                    keys = ("model_download_button", "model_cancel_button", "model_info_button", "model_details_button")
                    record["actions"] = {key: bounds(getattr(window, key), window.root, clip=window.canvas) for key in keys}
                    if state in INVENTORY_STATES:
                        panel = window.model_inventory
                        record["inventory"] = {
                            "entries": [vars(entry) for entry in panel.entries],
                            "selected_text": panel.selected_text.get(), "size_text": panel.size_text.get(),
                            "status": panel.status.get(), "details": panel.feedback.details,
                            "operation_pending": panel._operation is not None,
                            "bounds": {key: bounds(getattr(panel, key), window.root, clip=window.canvas)
                                for key in ("refresh_button", "model_picker", "selected_label", "size_label",
                                            "size_hint", "reason_label", "use_button", "feedback")},
                            "details_bounds": bounds(panel.feedback.details_button, window.root, clip=window.canvas),
                        }
                    record.update(state=state, scale_multiplier=scale, framing=framing,
                        inventory_panel_present=hasattr(window, "model_inventory"),
                        draft_unchanged=window._snapshot() == snapshot, baseline_unchanged=window.baseline == baseline,
                        model_downloading=window.model_downloading, cancel_requested=window.model_download_cancel.is_set(),
                        controls={key: str(getattr(window, key).cget("state")) for key in keys},
                        model_status=window.model_status.get(), action_status=window.model_action_status.get(),
                        message_bounds=bounds(variable_label(window, window.model_action_status), window.root, clip=window.canvas),
                        footer={key: bounds(getattr(window, key), window.root) for key in ("save_button", "close_button")},
                        navigation={key: bounds(button, window.root, clip=button.master) for key, button in window.nav.items()},
                        intercepted_uncaught=runtime.uncaught[starts[0]:], intercepted_dialogs=runtime.dialogs[starts[1]:],
                        synthetic_download_calls=runtime.download_calls[starts[2]:], worker_daemons=runtime.worker_daemons[starts[3]:])
                    manifest["captures"].append(record)
            if runtime.violations or runtime.blocked_actions or runtime.ipc_commands or runtime.workers:
                raise AssertionError("Unexpected action during model capture")
            manifest["scale_receipts"] = runtime.scale_receipts
            manifest["thread_start_attempts"] = runtime.start_attempts
            manifest["inventory_scan_calls"] = runtime.inventory_scan_calls
        if tuple(record["file"] for record in manifest["captures"]) != INVENTORY:
            raise AssertionError("Model capture inventory mismatch")
        manifest["status"] = "completed"
    finally:
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Captured {len(manifest['captures'])} synthetic model states in {output}")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    enable_dpi_awareness()
    capture_all(args.output)
