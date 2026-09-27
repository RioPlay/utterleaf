"""Guarded last-checked loaded-model snapshots, never real IPC or model access."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

from capture_auxiliary import capture, settle
from capture_backup import guard_input
from capture_diagnostics import bounds
from capture_mic_dispatch import landing_refresh, message_label
from capture_model_management import blocked_runtime as guarded_runtime
from capture_settings import _window
from utterleaf.settings_ui import SettingsWindow, enable_dpi_awareness

ROOT = Path(__file__).resolve().parents[1]
REAL_REFRESH = SettingsWindow.refresh_connection
ERROR = "Synthetic status failure /synthetic/private/model.bin"
STATES = ("ready-english", "ready-custom", "listening-unconfirmed", "old-version", "malformed", "error-retry")
SIZES = (((960, 780), 1.0), ((760, 560), 2.0))
CASES = tuple((state, size, scale) for size, scale in SIZES for state in STATES)
SOURCE_NAMES = ("settings_ui.py", "app_status.py", "ipc.py", "model_presentation.py",
                "app.py", "transcribe.py", "theme.py")
HELPER_NAMES = ("capture_settings.py", "capture_model_management.py", "capture_mic_dispatch.py",
                "capture_diagnostics.py", "capture_auxiliary.py", "capture_backup.py")


@contextmanager
def blocked_runtime():
    with guarded_runtime() as runtime:
        runtime.status_calls = []
        yield runtime


def refresh(window, runtime, replies):
    """Run the actual held worker; only the bounded transport reply is synthetic."""
    replies = iter(replies)

    def send(command, **kwargs):
        runtime.status_calls.append((command, kwargs))
        reply = next(replies)
        if isinstance(reply, Exception):
            raise reply
        return reply

    runtime.allow_worker = True
    try:
        REAL_REFRESH(window)
    finally:
        runtime.allow_worker = False
    if len(runtime.workers) != 1:
        raise AssertionError("Expected exactly one held status worker")
    with patch("utterleaf.ipc.send", side_effect=send):
        runtime.workers.pop()()
    callback, value = window.events.get_nowait()
    callback(value)
    if runtime.workers or not window.events.empty():
        raise AssertionError("Unexpected pending status work")


def stage(window, runtime, state):
    if state not in STATES + ("before",):
        raise ValueError(f"Unknown loaded-model capture state: {state}")
    window.vars["beep"].set(not window.vars["beep"].get())
    settle(window.root)
    snapshot, baseline = window._snapshot(), window.baseline.copy()
    replies = {
        "before": ["status-v1:ready"],
        "ready-english": ["status-v2:ready:tiny.en"],
        "ready-custom": ["status-v2:ready:custom"],
        "listening-unconfirmed": ["status-v2:listening:unconfirmed"],
        "old-version": ["unknown", "status-v1:ready"],
        "malformed": ["status-v2:ready:/synthetic/private/model.bin"],
        "error-retry": [RuntimeError(ERROR)],
    }
    if state == "error-retry":
        refresh(window, runtime, ["status-v2:ready:tiny.en"])
    refresh(window, runtime, replies[state])
    if window._snapshot() != snapshot or window.baseline != baseline:
        raise AssertionError("Status refresh changed draft preferences or baseline")
    return snapshot, baseline


def frame_status(window):
    """Include last-checked context when it fits; never claim automatic reveal."""
    label = message_label(window, "refresh_connection")
    words, button = label.master, landing_refresh(window)
    top = min(words.winfo_rooty(), button.winfo_rooty())
    bottom = max(words.winfo_rooty() + words.winfo_height(),
                 button.winfo_rooty() + button.winfo_height())
    fits = bottom - top + 24 <= window.canvas.winfo_height()
    anchor = top if fits else label.winfo_rooty()
    region = window.canvas.bbox("all")
    y = anchor - window.canvas.winfo_rooty() + window.canvas.canvasy(0)
    window.canvas.yview_moveto(max(0, y - 12) / max(1, region[3] - region[1]))
    return {"group_height": bottom - top, "viewport_height": window.canvas.winfo_height(),
            "whole_group_fits": fits, "includes_last_checked_heading": fits}


def capture_all(output, *, before=False):
    output = output.resolve()
    if not output.is_relative_to(ROOT / "artifacts"):
        raise ValueError("Capture output must stay inside this checkout's artifacts directory")
    output.mkdir(parents=True, exist_ok=False)
    cases = tuple(("before", size, scale) for size, scale in SIZES) if before else CASES
    manifest = {"scope": "Synthetic last-checked app snapshots with manual framing; not a live app, active take, screen-reader or physical-DPI certification.",
        "platform": sys.platform, "python": sys.version.split()[0],
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "sources": {name: hashlib.sha256((ROOT / "utterleaf" / name).read_bytes()).hexdigest() for name in SOURCE_NAMES},
        "helpers": {name: hashlib.sha256((ROOT / "tests" / name).read_bytes()).hexdigest() for name in HELPER_NAMES},
        "captures": [], "status": "incomplete"}
    try:
        with blocked_runtime() as runtime:
            for state, size, scale in cases:
                filename = f"loaded-model-{state}-{size[0]}x{size[1]}-{scale:g}x.png"
                with _window(runtime, visible=False, text_scale=scale) as window:
                    errors = []
                    window.root.report_callback_exception = lambda kind, value, trace: errors.append(str(value))
                    guard_input(window.root, errors)
                    window.root.geometry(f"{size[0]}x{size[1]}+70+50")
                    window.root.deiconify()
                    settle(window.root)
                    start = len(runtime.status_calls)
                    snapshot, baseline = stage(window, runtime, state)
                    settle(window.root)
                    framing = frame_status(window)
                    settle(window.root)
                    record = capture(window.root, errors, filename, size, output)
                    record["actions"] = {"refresh_status": bounds(landing_refresh(window), window.root, clip=window.canvas)}
                    record.update(state=state, scale_multiplier=scale, framing=framing,
                        connection=window.connection.get(), checking=window.checking_connection,
                        ipc_calls=runtime.status_calls[start:],
                        message_bounds=bounds(message_label(window, "refresh_connection"), window.root, clip=window.canvas),
                        context_bounds=bounds(message_label(window, "refresh_connection").master, window.root, clip=window.canvas),
                        draft_unchanged=window._snapshot() == snapshot, baseline_unchanged=window.baseline == baseline,
                        footer={key: bounds(getattr(window, key), window.root) for key in ("save_button", "close_button")},
                        navigation={key: bounds(button, window.root, clip=button.master) for key, button in window.nav.items()})
                    manifest["captures"].append(record)
            if runtime.violations or runtime.blocked_actions or runtime.ipc_commands or runtime.workers or runtime.dialogs:
                raise AssertionError("Unexpected action during loaded-model capture")
            manifest["scale_receipts"] = runtime.scale_receipts
        if len(manifest["captures"]) != len(cases):
            raise AssertionError("Loaded-model capture inventory mismatch")
        manifest["status"] = "completed"
    finally:
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Captured {len(manifest['captures'])} synthetic status states in {output}")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--before", action="store_true")
    args = parser.parse_args()
    enable_dpi_awareness()
    capture_all(args.output, before=args.before)
