"""Guarded synthetic backup presentation; captures never read or apply user data."""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from capture_auxiliary import capture, owned_root, settle
from utterleaf import backup_store, backup_ui, config
from utterleaf.backup import BackupError, export_backup, inspect_backup
from utterleaf.settings_ui import enable_dpi_awareness

ROOT = Path(__file__).resolve().parents[1]
SOURCE_NAMES = ("backup_ui.py", "backup.py", "backup_store.py", "ui_layout.py", "theme.py")
CASES = (
    ("export", (680, 660), 1.0), ("import", (680, 660), 1.0), ("error", (680, 660), 1.0),
    ("export", (480, 460), 1.0), ("import", (480, 460), 1.0),
    ("export", (480, 460), 2.0), ("import", (480, 460), 2.0), ("error", (480, 460), 2.0),
)
INVENTORY = tuple(f"backup-{state}-{width}x{height}-{scale:g}x.png"
                  for state, (width, height), scale in CASES)
VOCABULARY = "synthetic term = Synthetic Term\ncafe = Café\n"


@contextmanager
def blocked_runtime():
    """Read only synthetic bytes and reject writes, device work, and native dialogs."""
    runtime = SimpleNamespace(violations=[], dialogs=[], preview_error=False)

    def deny(name):
        def blocked(*_args, **_kwargs):
            runtime.violations.append(name)
            raise AssertionError(f"Backup capture blocked {name}")
        return blocked

    with tempfile.TemporaryDirectory(prefix="utterleaf-backup-capture-") as folder, ExitStack() as stack:
        paths = (Path(folder) / "config.toml", Path(folder) / "dictionary.txt")
        cfg = config.Config(beep=True, allow_network=False)
        originals = (config._dump_toml(cfg).encode("utf-8"), VOCABULARY.encode("utf-8"))
        runtime.paths, runtime.originals, runtime.cfg = paths, originals, cfg

        def read(path, _limit):
            if runtime.preview_error:
                raise BackupError("Synthetic preview failure")
            if path not in paths:
                return deny("non-synthetic preference read")()
            return originals[paths.index(path)]

        stack.enter_context(patch.object(config, "config_path", return_value=paths[0]))
        stack.enter_context(patch.object(config, "dictionary_path", return_value=paths[1]))
        stack.enter_context(patch.object(backup_store, "_read", side_effect=read))
        for target in (
            "utterleaf.config.load", "utterleaf.config.save", "utterleaf.polish.dictionary_text",
            "utterleaf.polish.save_dictionary", "utterleaf.backup_store._atomic_write",
            "utterleaf.backup_store.apply_import", "utterleaf.backup_ui.apply_import",
            "utterleaf.backup_store.write_backup", "utterleaf.backup_ui.write_backup",
            "utterleaf.audio.Recorder", "sounddevice.InputStream", "threading.Thread.start",
            "socket.socket", "socket.create_connection", "subprocess.Popen", "webbrowser.open",
            "tkinter.Misc.clipboard_get", "tkinter.Misc.clipboard_clear", "tkinter.Misc.clipboard_append",
            "tkinter.filedialog.askopenfilename", "tkinter.filedialog.asksaveasfilename",
        ):
            stack.enter_context(patch(target, side_effect=deny(target)))
        for name in ("askyesno", "showinfo", "showerror", "showwarning"):
            stack.enter_context(patch(f"tkinter.messagebox.{name}", side_effect=deny(f"dialog:{name}")))
        yield runtime
        if any(path.exists() for path in paths):
            raise AssertionError("Synthetic preview unexpectedly wrote preference files")


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def guard_input(root, errors):
    """Install before mapping so native Tcl edits/copy cannot precede capture."""
    tag = f"BackupCaptureInputGuard{id(root)}"

    def reject(_event):
        errors.append("Unexpected input during backup capture")
        return "break"

    for event in ("<KeyPress>", "<KeyRelease>", "<ButtonPress>", "<ButtonRelease>",
                  "<B1-Motion>", "<B2-Motion>", "<MouseWheel>",
                  "<<Copy>>", "<<Cut>>", "<<Paste>>", "<<PasteSelection>>"):
        root.bind_class(tag, event, reject)
    for widget in (root, *descendants(root)):
        widget.bindtags((tag, *widget.bindtags()))


def stage_dialog(owner, runtime, state):
    if state not in {"export", "import", "error"}:
        raise ValueError(state)
    runtime.preview_error = state == "error"
    plan = None if state == "export" else inspect_backup(export_backup(
        config.Config(beep=False, output_format="markdown"), "new term = New Term\ncafe = Café\n"))
    dialog = backup_ui.BackupDialog(owner, runtime.cfg, VOCABULARY, plan=plan)
    if state == "import":
        dialog.selected["beep"].set(True)
        dialog.selected["output_format"].set(True)
        dialog.mode.set("merge")
        dialog.refresh()
    return dialog


def choice_bounds(dialog):
    records = []
    for widget in descendants(dialog.options_body):
        if widget.winfo_class() not in {"TCheckbutton", "TCombobox"}:
            continue
        widget.focus_force()
        dialog.root.update()
        canvas = dialog.options_canvas
        x, y = widget.winfo_rootx() - canvas.winfo_rootx(), widget.winfo_rooty() - canvas.winfo_rooty()
        width, height = widget.winfo_width(), widget.winfo_height()
        records.append({"label": str(widget.cget("text")) if "text" in widget.keys() else "Vocabulary decision",
                        "bounds": [x, y, width, height],
                        "requested": [widget.winfo_reqwidth(), widget.winfo_reqheight()],
                        "fits_viewport_after_focus": bool(widget.winfo_ismapped()) and x >= 0 and y >= 0
                        and x + width <= canvas.winfo_width() and y + height <= canvas.winfo_height()
                        and width >= widget.winfo_reqwidth() and height >= widget.winfo_reqheight()})
    return records


def capture_all(output):
    output = output.resolve()
    if not output.is_relative_to(ROOT / "artifacts"):
        raise ValueError("Capture output must stay inside this checkout's artifacts directory")
    output.mkdir(parents=True, exist_ok=False)
    manifest = {"scope": "Synthetic backup presentation; not native dialog, device, or accessibility acceptance",
                "platform": sys.platform, "python": sys.version.split()[0],
                "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "capture_helper_sha256": hashlib.sha256((ROOT / "tests/capture_auxiliary.py").read_bytes()).hexdigest(),
                "sources": {name: hashlib.sha256((ROOT / "utterleaf" / name).read_bytes()).hexdigest()
                            for name in SOURCE_NAMES}, "captures": [], "status": "incomplete"}
    try:
        with blocked_runtime() as runtime:
            for (state, size, scale), filename in zip(CASES, INVENTORY):
                with owned_root(scale) as (owner, errors):
                    guard_input(owner, errors)
                    owner.geometry("1x1+5+5")
                    owner.deiconify()
                    settle(owner)
                    dialog = stage_dialog(owner, runtime, state)
                    guard_input(dialog.root, errors)
                    dialog.root.geometry(f"{size[0]}x{size[1]}+70+50")
                    settle(dialog.root)
                    choices = choice_bounds(dialog)
                    record = capture(dialog.root, errors, filename, size, output)
                    record.update(state=state, scale_multiplier=scale, choices=choices)
                    manifest["captures"].append(record)
                    dialog.root.destroy()
            if runtime.violations or tuple(r["file"] for r in manifest["captures"]) != INVENTORY:
                raise AssertionError("Backup capture guard or inventory mismatch")
        manifest["status"] = "completed"
    finally:
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Captured {len(manifest['captures'])} synthetic backup states in {output}")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/screenshots/desktop-backup-baseline")
    args = parser.parse_args()
    enable_dpi_awareness()
    capture_all(args.output)
