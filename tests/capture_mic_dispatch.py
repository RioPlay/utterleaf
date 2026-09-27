"""Six guarded Settings check-dispatch states; no worker or external I/O runs."""
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
from capture_diagnostics import blocked_runtime as guarded_runtime, bounds
from capture_settings import _window
from utterleaf.config import Config
from utterleaf.settings_ui import SettingsWindow, enable_dpi_awareness

ROOT = Path(__file__).resolve().parents[1]
ERROR = "Synthetic thread start failure: /synthetic/private/device.txt"
REAL_METHODS = {name: getattr(SettingsWindow, name)
                for name in ("refresh_mics", "test_mic", "refresh_connection")}
CASES = tuple((name, size, scale) for size, scale in (((960, 780), 1.0), ((760, 560), 2.0))
              for name in REAL_METHODS)
INVENTORY = tuple(f"dispatch-{name}-{size[0]}x{size[1]}-{scale:g}x.png" for name, size, scale in CASES)
SOURCE_NAMES = ("settings_ui.py", "audio.py", "app_status.py", "ui_feedback.py", "theme.py")
HELPER_NAMES = ("capture_settings.py", "capture_diagnostics.py", "capture_auxiliary.py", "capture_backup.py")


@contextmanager
def blocked_runtime():
    with guarded_runtime() as runtime, ExitStack() as stack:
        runtime.start_attempts = 0

        def deny(name):
            def blocked(*_args, **_kwargs):
                runtime.violations.append(name)
                raise AssertionError(f"Dispatch capture blocked {name}")
            return blocked

        for name in ("utterleaf.audio.list_input_names", "utterleaf.ipc.send"):
            stack.enter_context(patch(name, side_effect=deny(name)))
        yield runtime


def stage(window, runtime, name):
    if name not in REAL_METHODS:
        raise ValueError(f"Unknown dispatch capture state: {name}")
    window.vars["beep"].set(not window.vars["beep"].get())
    settle(window.root)
    snapshot, baseline = window._snapshot(), window.baseline.copy()
    before = runtime.start_attempts

    def fail_start(_thread):
        runtime.start_attempts += 1
        raise RuntimeError(ERROR)

    with patch.object(threading.Thread, "start", fail_start):
        try:
            REAL_METHODS[name](window)
        except RuntimeError as exc:
            if str(exc) != ERROR:
                raise
            runtime.uncaught.append({"type": type(exc).__name__, "message": str(exc)})
    if runtime.start_attempts != before + 1 or runtime.workers or not window.events.empty():
        raise AssertionError("Expected exactly one failed dispatch and no queued worker result")
    if window._snapshot() != snapshot or window.baseline != baseline:
        raise AssertionError("Check dispatch changed the Settings draft or baseline")
    return snapshot, baseline


def message_label(window, name):
    variable = window.connection if name == "refresh_connection" else window.mic_message
    return next(widget for widget in descendants(window.root)
                if widget.winfo_ismapped() and "textvariable" in widget.keys()
                and str(widget.cget("textvariable")) == str(variable))


def landing_refresh(window):
    return next(widget for widget in descendants(window.pages["Dictation"])
                if widget.winfo_ismapped() and widget.winfo_class() == "TButton"
                and str(widget.cget("text")) == "Refresh status")


def align_feedback(window, name):
    """Synthetic framing only; production focus/reveal behavior is tested separately."""
    label = message_label(window, name)
    group = [label, landing_refresh(window)] if name == "refresh_connection" else [
        label, window.mic_button, window.refresh_button]
    if name != "refresh_connection" and window.mic_details_button.winfo_ismapped():
        group.append(window.mic_details_button)
    top = min(widget.winfo_rooty() for widget in group)
    bottom = max(widget.winfo_rooty() + widget.winfo_height() for widget in group)
    group_fits = bottom - top + 24 <= window.canvas.winfo_height()
    anchor = top if group_fits else label.winfo_rooty()
    region = window.canvas.bbox("all")
    y = anchor - window.canvas.winfo_rooty() + window.canvas.canvasy(0)
    window.canvas.yview_moveto(max(0, y - 12) / max(1, region[3] - region[1]))
    return {"group_height": bottom - top, "viewport_height": window.canvas.winfo_height(),
            "whole_group_fits": group_fits}


def capture_all(output):
    output = output.resolve()
    if not output.is_relative_to(ROOT / "artifacts"):
        raise ValueError("Capture output must stay inside this checkout's artifacts directory")
    output.mkdir(parents=True, exist_ok=False)
    manifest = {"scope": "Synthetic dispatch failure with manually framed feedback; no hardware, recording, IPC or native-dialog certification",
        "platform": sys.platform, "python": sys.version.split()[0],
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "sources": {name: hashlib.sha256((ROOT / "utterleaf" / name).read_bytes()).hexdigest() for name in SOURCE_NAMES},
        "helpers": {name: hashlib.sha256((ROOT / "tests" / name).read_bytes()).hexdigest() for name in HELPER_NAMES},
        "captures": [], "status": "incomplete"}
    try:
        with blocked_runtime() as runtime:
            for (name, size, scale), filename in zip(CASES, INVENTORY):
                with _window(runtime, cfg=Config(microphone="Synthetic input"), visible=False, text_scale=scale) as window:
                    errors = []
                    window.root.report_callback_exception = lambda kind, value, trace: errors.append(str(value))
                    guard_input(window.root, errors)
                    window.root.geometry(f"{size[0]}x{size[1]}+70+50")
                    window.root.deiconify()
                    settle(window.root)
                    starts = (len(runtime.uncaught), len(runtime.dialogs))
                    snapshot, baseline = stage(window, runtime, name)
                    settle(window.root)
                    framing = align_feedback(window, name)
                    settle(window.root)
                    record = capture(window.root, errors, filename, size, output)
                    controls = ("refresh_button", "mic_button", "mic_box", "connection_button")
                    record["actions"] = {key: bounds(getattr(window, key), window.root, clip=window.canvas)
                                         for key in controls}
                    record["actions"]["landing_refresh_status"] = bounds(
                        landing_refresh(window), window.root, clip=window.canvas)
                    record.update(operation=name, scale_multiplier=scale, microphone=window.vars["microphone"].get(),
                        draft_unchanged=window._snapshot() == snapshot, baseline_unchanged=window.baseline == baseline,
                        framing=framing, landing_refresh_is_connection_button=landing_refresh(window) is window.connection_button,
                        busy={key: getattr(window, key) for key in ("refreshing_mics", "checking_mic", "checking_connection")},
                        controls={key: str(getattr(window, key).cget("state")) for key in controls},
                        test_caption=str(window.mic_button.cget("text")),
                        mic_message=window.mic_message.get(), connection=window.connection.get(),
                        message_bounds=bounds(message_label(window, name), window.root, clip=window.canvas),
                        details=bounds(window.mic_details_button, window.root, clip=window.canvas),
                        footer={key: bounds(getattr(window, key), window.root) for key in ("save_button", "close_button")},
                        intercepted_uncaught=runtime.uncaught[starts[0]:], intercepted_dialogs=runtime.dialogs[starts[1]:])
                    manifest["captures"].append(record)
            if runtime.violations or runtime.blocked_actions or runtime.ipc_commands or runtime.workers:
                raise AssertionError("Unexpected action during dispatch capture")
            manifest["scale_receipts"] = runtime.scale_receipts
            manifest["thread_start_attempts"] = runtime.start_attempts
        if tuple(record["file"] for record in manifest["captures"]) != INVENTORY:
            raise AssertionError("Dispatch capture inventory mismatch")
        manifest["status"] = "completed"
    finally:
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Captured {len(manifest['captures'])} synthetic dispatch states in {output}")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    enable_dpi_awareness()
    capture_all(args.output)
