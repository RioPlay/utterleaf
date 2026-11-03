"""Synthetic report recovery captures; no hardware probe, export or native dialog."""
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
from capture_backup import guard_input
from capture_settings import _blocked_runtime, _window
from utterleaf.settings_ui import SettingsWindow, enable_dpi_awareness

ROOT = Path(__file__).resolve().parents[1]
REPORT = "Synthetic device report\nSaved configuration: CPU\nNo hardware was probed.\nReview before sharing."
ERROR = "Synthetic report failure: /synthetic/private/device.txt"
REAL_METHODS = {name: getattr(SettingsWindow, name)
                for name in ("diagnostics", "cuda_setup", "export_report")}
CASES = (
    *((state, (960, 780), 1.0) for state in (
        "normal", "success", "error-empty", "error-previous", "gpu-error",
        "save-picker-error", "save-write-error")),
    ("error-previous", (760, 560), 2.0),
    ("save-write-error", (760, 560), 2.0),
)
INVENTORY = tuple(f"report-{state}-{size[0]}x{size[1]}-{scale:g}x.png"
                  for state, size, scale in CASES)
SOURCE_NAMES = ("settings_ui.py", "hardware.py", "ui_feedback.py", "ui_layout.py", "theme.py")
HELPER_NAMES = ("capture_settings.py", "capture_auxiliary.py", "capture_backup.py")


@contextmanager
def blocked_runtime():
    """Extend Settings' synthetic fixture without enabling any public action."""
    with _blocked_runtime() as runtime, ExitStack() as stack:
        runtime.workers = []
        runtime.allow_worker = False
        runtime.result = REPORT
        runtime.probes = []
        runtime.writes = []
        runtime.violations = []
        runtime.uncaught = []

        def deny(name):
            def blocked(*_args, **_kwargs):
                runtime.violations.append(name)
                raise AssertionError(f"Diagnostic capture blocked {name}")
            return blocked

        def hold_worker(thread):
            if not runtime.allow_worker:
                return deny("unexpected worker")()
            runtime.workers.append(thread._target)

        def report(kind):
            def synthetic(*_args, **_kwargs):
                runtime.probes.append(kind)
                if isinstance(runtime.result, Exception):
                    raise runtime.result
                return runtime.result.splitlines() if kind == "gpu" else runtime.result
            return synthetic

        for target in (
            "utterleaf.config.load", "utterleaf.config.save", "utterleaf.config.config_path",
            "utterleaf.config.dictionary_path", "utterleaf.polish.dictionary_text",
            "utterleaf.polish.save_dictionary", "utterleaf.audio.Recorder", "sounddevice.InputStream",
            "sounddevice.query_devices", "socket.socket", "socket.create_connection",
            "subprocess.Popen", "webbrowser.open", "tkinter.Misc.clipboard_get",
            "tkinter.Misc.clipboard_clear", "tkinter.Misc.clipboard_append",
            "utterleaf.hardware.probe", "utterleaf.hardware.cuda_runtime_ok",
        ):
            stack.enter_context(patch(target, side_effect=deny(target)))
        stack.enter_context(patch.object(threading.Thread, "start", hold_worker))
        stack.enter_context(patch("utterleaf.hardware.generate_diagnostic_report", side_effect=report("device")))
        stack.enter_context(patch("utterleaf.hardware.cuda_setup_plan", side_effect=report("gpu")))
        yield runtime


def check(window, runtime, *, gpu=False, error=False):
    """Run the production worker and completion, with only its probe replaced."""
    runtime.result = OSError(ERROR) if error else REPORT
    runtime.allow_worker = True
    try:
        REAL_METHODS["cuda_setup" if gpu else "diagnostics"](window)
    finally:
        runtime.allow_worker = False
    if len(runtime.workers) != 1:
        raise AssertionError("Expected exactly one staged report worker")
    runtime.workers.pop()()
    callback, value = window.events.get_nowait()
    callback(value)


def save_failure(window, runtime, *, picker=False):
    def write(path, content, **kwargs):
        runtime.writes.append((str(path), content, kwargs))
        if str(path) != "synthetic-report.txt" or content != REPORT:
            raise AssertionError("Unexpected report write")
        raise OSError(ERROR)

    with patch("tkinter.filedialog.asksaveasfilename", **(
            {"side_effect": OSError(ERROR)} if picker else {"return_value": "synthetic-report.txt"})), \
            patch.object(Path, "write_text", write):
        try:
            REAL_METHODS["export_report"](window)
        except OSError as exc:
            # The before source leaves picker errors uncaught. Retain that fact,
            # rather than pretending an intercepted exception is a native dialog.
            runtime.uncaught.append({"type": type(exc).__name__, "message": str(exc)})


def stage(window, runtime, state):
    if state not in {case[0] for case in CASES}:
        raise ValueError(f"Unknown report capture state: {state}")
    if state == "normal":
        return
    if state in {"success", "error-previous", "save-picker-error", "save-write-error"}:
        check(window, runtime)
    if state in {"error-empty", "error-previous", "gpu-error"}:
        check(window, runtime, gpu=state == "gpu-error", error=True)
    if state.startswith("save-"):
        save_failure(window, runtime, picker=state == "save-picker-error")


def bounds(widget, root, *, clip=None):
    x = widget.winfo_rootx() - root.winfo_rootx()
    y = widget.winfo_rooty() - root.winfo_rooty()
    width, height = widget.winfo_width(), widget.winfo_height()
    mapped = bool(widget.winfo_ismapped())
    clip = root if clip is None else clip
    clip_x = widget.winfo_rootx() - clip.winfo_rootx()
    clip_y = widget.winfo_rooty() - clip.winfo_rooty()
    return {"bounds": [x, y, width, height],
            "requested": [widget.winfo_reqwidth(), widget.winfo_reqheight()], "mapped": mapped,
            "fits_window": mapped and 0 <= x and 0 <= y
            and x + width <= root.winfo_width() and y + height <= root.winfo_height(),
            "fits_viewport": mapped and 0 <= clip_x and 0 <= clip_y
            and clip_x + width <= clip.winfo_width() and clip_y + height <= clip.winfo_height(),
            "natural_width": width >= widget.winfo_reqwidth(),
            "natural_height": height >= widget.winfo_reqheight()}


def position_report(window):
    """Align the report area for a synthetic viewport, without changing focus."""
    target = window.diagnostic_button
    if hasattr(window, "report_feedback") and window.report_status.get():
        target = window.report_feedback.label
    canvas = window.canvas
    region = canvas.bbox("all")
    y = target.winfo_rooty() - canvas.winfo_rooty() + canvas.canvasy(0)
    canvas.yview_moveto(max(0, y - 16) / max(1, region[3] - region[1]))


def capture_all(output):
    output = output.resolve()
    if not output.is_relative_to(ROOT / "artifacts"):
        raise ValueError("Capture output must stay inside this checkout's artifacts directory")
    output.mkdir(parents=True, exist_ok=False)
    manifest = {"scope": "Synthetic report presentation; native dialogs, real probes/exports and accessibility are not certified",
                "platform": sys.platform, "python": sys.version.split()[0],
                "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "helpers": {name: hashlib.sha256((ROOT / "tests" / name).read_bytes()).hexdigest()
                            for name in HELPER_NAMES},
                "sources": {name: hashlib.sha256((ROOT / "utterleaf" / name).read_bytes()).hexdigest()
                            for name in SOURCE_NAMES}, "captures": [], "status": "incomplete"}
    try:
        with blocked_runtime() as runtime:
            for (state, size, scale), filename in zip(CASES, INVENTORY):
                with _window(runtime, visible=False, text_scale=scale) as window:
                    errors = []
                    window.root.report_callback_exception = lambda kind, value, trace: errors.append(str(value))
                    guard_input(window.root, errors)
                    window.root.geometry(f"{size[0]}x{size[1]}+70+50")
                    window.show_page("Help & diagnostics")
                    window.root.deiconify()
                    settle(window.root)
                    snapshot = window._snapshot()
                    dialog_start, uncaught_start = len(runtime.dialogs), len(runtime.uncaught)
                    stage(window, runtime, state)
                    settle(window.root)
                    position_report(window)
                    settle(window.root)
                    record = capture(window.root, errors, filename, size, output)
                    record["actions"] = {name: bounds(getattr(window, name), window.root,
                        clip=window.canvas if name in {"diagnostic_button", "export_button", "cuda_button"} else None) for name in (
                        "diagnostic_button", "export_button", "cuda_button", "save_button", "close_button")}
                    record.update(state=state, scale_multiplier=scale, report_preserved=window.report == REPORT,
                                  viewport_position="Synthetic report alignment; automatic reveal is tested separately",
                                  preview=window.diagnostic_text.get("1.0", "end-1c"),
                                  intercepted_dialogs=runtime.dialogs[dialog_start:],
                                  intercepted_uncaught=runtime.uncaught[uncaught_start:])
                    if hasattr(window, "report_feedback"):
                        record["feedback"] = {"primary": window.report_status.get(),
                            "label": bounds(window.report_feedback.label, window.root, clip=window.canvas),
                            "details": bounds(window.report_feedback.details_button, window.root, clip=window.canvas)}
                    manifest["captures"].append(record)
                    if window._snapshot() != snapshot:
                        raise AssertionError("Report capture changed the Settings draft")
            if runtime.violations or runtime.blocked_actions or runtime.workers:
                raise AssertionError("Unexpected action in diagnostic capture")
            manifest["scale_receipts"] = runtime.scale_receipts
        if tuple(record["file"] for record in manifest["captures"]) != INVENTORY:
            raise AssertionError("Report capture inventory mismatch")
        manifest["status"] = "completed"
    finally:
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Captured {len(manifest['captures'])} synthetic report states in {output}")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    enable_dpi_awareness()
    capture_all(args.output)
