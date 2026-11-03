"""Guarded, synthetic baseline for file/decoder/review windows; no real work.

Run from the desktop checkout. A new output directory is required so before-state
evidence cannot be silently overwritten. Native file/confirmation dialogs are
intercepted, not visually certified. Screenshots demonstrate presentation only.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
import hashlib
import io
import json
from pathlib import Path
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import ImageGrab
from utterleaf.config import Config
from utterleaf import file_ui, file_decoder_ui, review_ui
from utterleaf.settings_ui import enable_dpi_awareness
from utterleaf.transcript import Segment, Transcript

SAMPLE_TEXT = "Synthetic review sample. Café notes stay local; nothing has been inserted or exported."
SAMPLE_RESULT = Transcript((Segment(0, 4, SAMPLE_TEXT),), "en")
FILE_STATES = ("empty", "selected", "opening", "recognizing", "cancelling",
               "cancelled", "result", "no-speech", "error", "export-error")
INVENTORY = (
    *(f"file-{state}.png" for state in FILE_STATES),
    "file-result-compact-text-2x.png",
    "decoder-none.png", "decoder-selected.png", "decoder-error.png",
    "decoder-compact-text-2x.png",
    "review-insert.png", "review-copy-only.png", "review-compact.png",
    "review-compact-text-2x.png",
    "file-error-compact-text-2x.png", "decoder-error-compact-text-2x.png",
)


@contextmanager
def blocked_runtime():
    """Intercept both imported aliases and underlying I/O boundaries."""
    runtime = SimpleNamespace(open_path="", save_path="", confirm=False,
                              decoder=None, export_error=None, threads=[],
                              dialogs=[], exports=[], violations=[])

    def deny(name):
        def blocked(*_args, **_kwargs):
            runtime.violations.append(name)
            raise AssertionError(f"Auxiliary capture blocked {name}")
        return blocked

    def hold_thread(thread):
        if thread.name not in {"utterleaf-file", "utterleaf-review-control"}:
            return deny("unexpected worker")()
        runtime.threads.append(thread.name)  # Never execute its target.

    def decoder_selection():
        if isinstance(runtime.decoder, Exception):
            raise runtime.decoder
        return runtime.decoder

    def export(*args, **kwargs):
        runtime.exports.append((args, kwargs))
        if runtime.export_error is None:
            return deny("unstaged export")()
        raise runtime.export_error

    with ExitStack() as stack:
        for target in (
            "utterleaf.file_ui.transcribe_file", "utterleaf.file_ui._work",
            "utterleaf.file_transcription.transcribe_file",
            "utterleaf.transcript.export_transcript",
            "utterleaf.file_decoder.decoder_selection",
            "utterleaf.file_decoder.select_decoder", "utterleaf.file_decoder.forget_decoder",
            "utterleaf.file_decoder_ui.select_decoder", "utterleaf.file_decoder_ui.forget_decoder",
            "utterleaf.config.load", "utterleaf.config.save", "utterleaf.settings.launch_settings",
            "subprocess.Popen", "webbrowser.open", "socket.socket", "socket.create_connection",
            "tkinter.Misc.clipboard_clear", "tkinter.Misc.clipboard_append",
        ):
            stack.enter_context(patch(target, side_effect=deny(target)))
        stack.enter_context(patch.object(threading.Thread, "start", hold_thread))
        stack.enter_context(patch.object(file_ui, "export_transcript", side_effect=export))
        stack.enter_context(patch.object(file_decoder_ui, "decoder_selection", side_effect=decoder_selection))
        stack.enter_context(patch.object(filedialog, "askopenfilename", side_effect=lambda **_: runtime.open_path))
        stack.enter_context(patch.object(filedialog, "asksaveasfilename", side_effect=lambda **_: runtime.save_path))
        stack.enter_context(patch.object(messagebox, "askyesno", side_effect=lambda *a, **k: runtime.confirm))
        for name in ("showinfo", "showerror", "showwarning"):
            stack.enter_context(patch.object(messagebox, name,
                side_effect=lambda *a, **k: runtime.dialogs.append(a)))
        yield runtime


@contextmanager
def owned_root(scale=1.0):
    root = tk.Tk()
    root.withdraw()
    errors = []
    root.report_callback_exception = lambda kind, value, trace: errors.append(f"{kind.__name__}: {value}")
    baseline = float(root.tk.call("tk", "scaling"))
    root.tk.call("tk", "scaling", baseline * scale)
    try:
        yield root, errors
    finally:
        try:
            for timer in root.tk.call("after", "info"):
                root.tk.call("after", "cancel", timer)
            root.tk.call("tk", "scaling", baseline)
            root.destroy()
        except tk.TclError:
            pass


def settle(root):
    for _ in range(4):
        root.update()
        time.sleep(0.035)


def file_events(window):
    # Drain via production code without creating a second queue-poll timer.
    window.root.after_cancel(window.poll_id)
    window.poll()


def stage_file(window, runtime, state):
    if state not in FILE_STATES:
        raise ValueError(state)
    if state == "empty":
        return
    runtime.open_path = "Synthetic meeting.wav"
    window.choose()
    if state == "selected":
        return
    window.start()  # The production worker start is held by blocked_runtime.
    if state == "opening":
        return
    if state == "recognizing":
        window.events.put(("progress", ("recognizing", 0.4)))
    elif state in {"cancelling", "cancelled"}:
        window.cancel()
        if state == "cancelled":
            window.events.put(("cancelled", None))
    elif state == "error":
        window.events.put(("error", "Synthetic failure: the selected media could not be decoded."))
    else:
        result = Transcript(()) if state == "no-speech" else SAMPLE_RESULT
        window.events.put(("result", result))
    file_events(window)
    if state == "export-error":
        runtime.save_path = "Synthetic transcript.txt"
        runtime.export_error = OSError("Synthetic destination is not writable")
        window.export()


def render_review(root, allow_insert, visit):
    """Use the real entrypoint, but keep its IPC and event loop inside this test."""
    request = io.StringIO(json.dumps({"text": SAMPLE_TEXT, "allow_insert": allow_insert}) + "\n")
    response = io.StringIO()
    with patch.object(review_ui.sys, "stdin", request), patch.object(review_ui.sys, "stdout", response), \
            patch.object(tk, "Tk", return_value=root), patch.object(root, "mainloop", side_effect=visit):
        result = review_ui.run_review()
    if result != 0:
        raise AssertionError(f"Review renderer returned {result}")
    return response.getvalue()


def capture(root, errors, filename, size, output):
    # Reject physical input before widget/class bindings can copy or paste.
    def reject_input(_event):
        errors.append("Unexpected input during capture")
        return "break"
    tag = "AuxiliaryCaptureInputGuard"
    for event in ("<KeyPress>", "<KeyRelease>", "<ButtonPress>", "<ButtonRelease>",
                  "<B1-Motion>", "<B2-Motion>", "<MouseWheel>",
                  "<<Copy>>", "<<Cut>>", "<<Paste>>", "<<PasteSelection>>"):
        root.bind_class(tag, event, reject_input)
    pending = [root]
    buttons = []
    while pending:
        widget = pending.pop()
        widget.bindtags((tag, *widget.bindtags()))
        pending.extend(widget.winfo_children())
        if widget.winfo_class() == "TButton":
            buttons.append(widget)
    root.geometry(f"{size[0]}x{size[1]}+70+50")
    root.deiconify()
    root.attributes("-topmost", True)
    settle(root)
    actual = [root.winfo_width(), root.winfo_height()]
    if errors or actual != list(size):
        raise AssertionError(f"{filename}: requested {size}, actual {actual}, callback errors {errors}")
    if sys.platform == "win32":
        picture = ImageGrab.grab(window=root.winfo_id())
    else:
        x, y = root.winfo_rootx(), root.winfo_rooty()
        picture = ImageGrab.grab(bbox=(x, y, x + actual[0], y + actual[1]))
    picture.save(output / filename)
    action_bounds = []
    for button in buttons:
        x = button.winfo_rootx() - root.winfo_rootx()
        y = button.winfo_rooty() - root.winfo_rooty()
        width, height = button.winfo_width(), button.winfo_height()
        action_bounds.append({
            "label": str(button.cget("text")), "bounds": [x, y, width, height],
            "requested": [button.winfo_reqwidth(), button.winfo_reqheight()],
            "mapped": bool(button.winfo_ismapped()),
            "fits_window": (bool(button.winfo_ismapped()) and x >= 0 and y >= 0
                            and x + width <= actual[0] and y + height <= actual[1]
                            and width >= button.winfo_reqwidth() and height >= button.winfo_reqheight()),
        })
    return {"file": filename, "requested_size": list(size), "actual_size": actual,
            "tk_scaling": float(root.tk.call("tk", "scaling")),
            "tk_version": str(root.tk.call("info", "patchlevel")),
            "actions": action_bounds, "synthetic": True}


def capture_all(output):
    output = output.resolve()
    if not output.is_relative_to(ROOT / "artifacts"):
        raise ValueError("Capture output must stay inside this checkout's artifacts directory")
    output.mkdir(parents=True, exist_ok=False)
    manifest = {"scope": "Synthetic file/decoder/review presentation, not real device or dialog acceptance",
                "platform": sys.platform, "python": sys.version.split()[0],
                "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "sources": {name: hashlib.sha256((ROOT / "utterleaf" / name).read_bytes()).hexdigest()
                            for name in ("file_ui.py", "file_decoder_ui.py", "review_ui.py", "theme.py", "ui_layout.py", "ui_feedback.py")},
                "captures": [], "status": "incomplete"}
    records = manifest["captures"]
    try:
        with blocked_runtime() as runtime:
            for state in FILE_STATES:
                with owned_root() as (root, errors):
                    window = file_ui.FileWindow(root, Config())
                    root.geometry("800x640+60+40")
                    root.deiconify()
                    settle(root)
                    stage_file(window, runtime, state)
                    records.append(capture(root, errors, f"file-{state}.png", (800, 640), output))
            with owned_root(2.0) as (root, errors):
                window = file_ui.FileWindow(root, Config())
                stage_file(window, runtime, "result")
                records.append(capture(root, errors, "file-result-compact-text-2x.png", (760, 560), output))
            for state, scale in (("none", 1.0), ("selected", 1.0), ("error", 1.0), ("compact-text-2x", 2.0)):
                with owned_root(scale) as (parent, errors):
                    parent.geometry("760x560+60+40")
                    parent.deiconify()
                    parent.update()
                    runtime.decoder = ({"path": "synthetic-tools/ffmpeg.exe"} if state == "selected" else
                                       RuntimeError("Synthetic selection changed; choose FFmpeg again.") if state == "error" else None)
                    dialog = file_decoder_ui.DecoderDialog(parent)
                    dialog.root.report_callback_exception = parent.report_callback_exception
                    records.append(capture(dialog.root, errors, f"decoder-{state}.png",
                                           (560, 500) if scale == 2 else (680, 530), output))
                    dialog.root.destroy()
            for name, allow_insert, size, scale in (
                ("insert", True, (680, 480), 1.0), ("copy-only", False, (680, 480), 1.0),
                ("compact", True, (480, 320), 1.0), ("compact-text-2x", False, (480, 320), 2.0),
            ):
                with owned_root(scale) as (root, errors):
                    response = render_review(root, allow_insert, lambda: records.append(
                        capture(root, errors, f"review-{name}.png", size, output)))
                    if response != "ready\n":
                        raise AssertionError("Review emitted an unexpected action")
            # Deliver errors after mapping, as an actual user-triggered failure
            # arrives. This exercises production error reveal at large text.
            for kind, size in (("file", (760, 560)), ("decoder", (560, 500))):
                with owned_root(2.0) as (root, errors):
                    root.geometry("760x560+60+40")
                    root.deiconify()
                    root.update()
                    runtime.decoder = None
                    window = (file_ui.FileWindow(root, Config()) if kind == "file"
                              else file_decoder_ui.DecoderDialog(root))
                    window.root.geometry(f"{size[0]}x{size[1]}+60+40")
                    settle(window.root)
                    if kind == "file":
                        stage_file(window, runtime, "error")
                    else:
                        runtime.open_path = "synthetic-tools/ffmpeg.exe"
                        runtime.confirm = True
                        with patch.object(file_decoder_ui, "select_decoder",
                                          side_effect=RuntimeError("Synthetic selection could not be verified.")):
                            window.choose()
                    records.append(capture(window.root, errors, f"{kind}-error-compact-text-2x.png", size, output))
                    if kind == "decoder":
                        window.root.destroy()
            if runtime.violations or tuple(record["file"] for record in records) != INVENTORY:
                raise AssertionError("Capture guard or inventory mismatch")
        manifest["status"] = "completed"
    finally:
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Captured {len(records)} synthetic auxiliary states in {output}")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/screenshots/desktop-auxiliary-baseline")
    args = parser.parse_args()
    enable_dpi_awareness()
    capture_all(args.output)
