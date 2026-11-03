"""Guarded artwork-reference captures; export workers and native dialogs are synthetic."""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
import hashlib
import json
from pathlib import Path
import sys
import threading
import tkinter as tk
from tkinter import font as tkfont, ttk
from types import SimpleNamespace
from unittest.mock import patch

from capture_auxiliary import capture, owned_root, settle
from capture_backup import descendants, guard_input
from utterleaf.appearance import AppearanceGuide
from utterleaf.settings_ui import enable_dpi_awareness

ROOT = Path(__file__).resolve().parents[1]
TABS = ("Tray states", "App badges", "Cutout marks", "Utterling", "Wordmark")
CASES = (
    *((tab, (900, 740), 1.0, False) for tab in TABS),
    *((tab, (720, 540), 2.0, False) for tab in ("Tray states", "Utterling", "Wordmark")),
    ("Wordmark", (720, 540), 2.0, True),
)
INVENTORY = tuple(f"artwork-{tab.lower().replace(' ', '-')}-{size[0]}x{size[1]}-{scale:g}x"
                  f"{'-error' if error else ''}.png" for tab, size, scale, error in CASES)
SOURCE_NAMES = ("appearance.py", "brand.py", "brand_export.py", "ui_layout.py", "ui_feedback.py", "theme.py")
SYNTHETIC_ERROR = "Synthetic export destination is unavailable."


@contextmanager
def blocked_runtime():
    runtime = SimpleNamespace(save_path="", allow_worker=False, workers=[], exports=[],
                              dialogs=[], violations=[], export_error=None)

    def deny(name):
        def blocked(*_args, **_kwargs):
            runtime.violations.append(name)
            raise AssertionError(f"Artwork capture blocked {name}")
        return blocked

    def hold_worker(thread):
        if not runtime.allow_worker:
            return deny("unexpected worker")()
        runtime.workers.append(thread._target)

    def export(path):
        runtime.exports.append(str(path))
        if str(path) != runtime.save_path or not runtime.save_path:
            return deny("unstaged export")()
        if runtime.export_error is not None:
            raise runtime.export_error

    with ExitStack() as stack:
        for target in (
            "utterleaf.config.load", "utterleaf.config.save", "utterleaf.config.config_path",
            "utterleaf.config.dictionary_path", "utterleaf.polish.dictionary_text",
            "utterleaf.polish.save_dictionary", "utterleaf.audio.Recorder", "sounddevice.InputStream",
            "socket.socket", "socket.create_connection", "subprocess.Popen", "webbrowser.open",
            "tkinter.Misc.clipboard_get", "tkinter.Misc.clipboard_clear", "tkinter.Misc.clipboard_append",
            "tkinter.filedialog.askopenfilename", "tkinter.messagebox.askyesno",
        ):
            stack.enter_context(patch(target, side_effect=deny(target)))
        stack.enter_context(patch.object(threading.Thread, "start", hold_worker))
        stack.enter_context(patch("utterleaf.brand_export.export_pack", side_effect=export))
        stack.enter_context(patch("tkinter.filedialog.asksaveasfilename", side_effect=lambda **_: runtime.save_path))
        for name in ("showerror", "showinfo", "showwarning"):
            stack.enter_context(patch(f"tkinter.messagebox.{name}",
                side_effect=lambda *args, _kind=name, **kwargs: runtime.dialogs.append((_kind, args))))
        yield runtime


def start_export(guide, runtime, path="synthetic-artwork.zip"):
    runtime.save_path = path
    runtime.allow_worker = True
    try:
        guide.export()
    finally:
        runtime.allow_worker = False


def finish_export(guide, runtime, error=None):
    runtime.export_error = error
    runtime.workers.pop(0)()
    if guide.export_poll is not None:
        guide.root.after_cancel(guide.export_poll)
    guide._export_done()


def select_tab(guide, name):
    guide.tabs.select(TABS.index(name))


def tab_bounds(guide):
    notebook = guide.tabs
    extents = {}
    for x in range(notebook.winfo_width()):
        try:
            index = notebook.index(f"@{x},10")
        except tk.TclError:
            continue
        extents.setdefault(index, [x, x])[1] = x
    font = tkfont.Font(root=guide.root, font=ttk.Style(guide.root).lookup("TNotebook.Tab", "font"))
    records = []
    for index, tab in enumerate(notebook.tabs()):
        label = notebook.tab(tab, "text")
        text_width = max(font.measure(line) for line in label.splitlines())
        span = extents.get(index)
        records.append({"label": label, "span": span, "text_width": text_width,
                        "fits_text": span is not None and span[1] - span[0] + 1 >= text_width})
    return records


def content_bounds(guide, name):
    canvas = guide.canvases[name]
    records = []
    for key, row in guide.entries.items():
        if not str(row).startswith(str(canvas) + "."):
            continue
        for widget in descendants(row):
            if widget.winfo_class() not in {"Label", "TLabel"}:
                continue
            x = widget.winfo_rootx() - canvas.winfo_rootx()
            width = widget.winfo_width()
            records.append({"entry": key, "label": str(widget.cget("text")),
                            "x": x, "width": width, "requested_width": widget.winfo_reqwidth(),
                            "fits_horizontal": 0 <= x and x + width <= canvas.winfo_width()
                            and width >= widget.winfo_reqwidth()})
    return records


def capture_all(output):
    output = output.resolve()
    if not output.is_relative_to(ROOT / "artifacts"):
        raise ValueError("Capture output must stay inside this checkout's artifacts directory")
    output.mkdir(parents=True, exist_ok=False)
    manifest = {"scope": "Synthetic artwork presentation; native dialogs, real exports and accessibility are not certified",
                "platform": sys.platform, "python": sys.version.split()[0],
                "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "helpers": {name: hashlib.sha256((ROOT / "tests" / name).read_bytes()).hexdigest()
                            for name in ("capture_auxiliary.py", "capture_backup.py")},
                "sources": {name: hashlib.sha256((ROOT / "utterleaf" / name).read_bytes()).hexdigest()
                            for name in SOURCE_NAMES}, "captures": [], "status": "incomplete"}
    try:
        with blocked_runtime() as runtime:
            for (tab, size, scale, failure), filename in zip(CASES, INVENTORY):
                with owned_root(scale) as (owner, errors):
                    guard_input(owner, errors)
                    owner.geometry("1x1+5+5")
                    owner.deiconify()
                    settle(owner)
                    guide = AppearanceGuide(owner)
                    guard_input(guide.root, errors)
                    select_tab(guide, tab)
                    guide.root.geometry(f"{size[0]}x{size[1]}+70+50")
                    settle(guide.root)
                    before_dialogs = len(runtime.dialogs)
                    if failure:
                        start_export(guide, runtime)
                        finish_export(guide, runtime, OSError(SYNTHETIC_ERROR))
                        settle(guide.root)
                    record = capture(guide.root, errors, filename, size, output)
                    record.update(tab=tab, scale_multiplier=scale, content=content_bounds(guide, tab),
                                  tab_labels=tab_bounds(guide),
                                  viewport=[guide.canvases[tab].winfo_width(), guide.canvases[tab].winfo_height()],
                                  intercepted_dialogs=runtime.dialogs[before_dialogs:])
                    manifest["captures"].append(record)
                    guide.close()
            if runtime.violations or tuple(r["file"] for r in manifest["captures"]) != INVENTORY:
                raise AssertionError("Artwork capture guard or inventory mismatch")
        manifest["status"] = "completed"
    finally:
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Captured {len(manifest['captures'])} synthetic artwork states in {output}")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/screenshots/desktop-artwork-baseline")
    args = parser.parse_args()
    enable_dpi_awareness()
    capture_all(args.output)
