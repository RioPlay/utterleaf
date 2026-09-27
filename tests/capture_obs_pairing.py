"""Guarded synthetic OBS pairing-dialog baseline; no pairing store is opened.

Run from the desktop checkout. A new output directory is required. The capture
uses production presentation transitions with fixed synthetic outcomes while
blocking pairing storage, native dialogs, network, audio, clipboard and user
preferences. It does not certify OBS, native dialogs or accessibility.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
import hashlib
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from capture_auxiliary import capture, owned_root, settle
from capture_backup import guard_input
from utterleaf import obs_pairing_ui
from utterleaf.settings_ui import enable_dpi_awareness


CASES = (
    ("unpaired", (620, 530), 1.0),
    ("paired", (620, 530), 1.0),
    ("importing", (620, 530), 1.0),
    ("cancelling", (620, 530), 1.0),
    ("file-error", (620, 530), 1.0),
    ("uncertain", (620, 530), 1.0),
    ("storage-unavailable", (620, 530), 1.0),
    ("saved-file-kept", (620, 530), 1.0),
    ("file-error", (450, 460), 2.0),
    ("storage-unavailable", (450, 460), 2.0),
)
INVENTORY = tuple(
    f"obs-pairing-{state}-{width}x{height}-{scale:g}x.png"
    for state, (width, height), scale in CASES
)
SOURCE_NAMES = ("obs_pairing_ui.py", "obs_pairing_store.py", "theme.py")
HELPER_NAMES = ("capture_auxiliary.py", "capture_backup.py")


@contextmanager
def blocked_runtime():
    """Hold the named pairing worker and reject every external boundary."""
    runtime = SimpleNamespace(violations=[], workers=[], dialogs=[])

    def deny(name):
        def blocked(*_args, **_kwargs):
            runtime.violations.append(name)
            raise AssertionError(f"OBS pairing capture blocked {name}")
        return blocked

    def hold_worker(worker):
        if worker.name != "obs-pairing-setup":
            return deny("unexpected worker")()
        runtime.workers.append(worker)

    with ExitStack() as stack:
        for target in (
            "utterleaf.config.load", "utterleaf.config.save",
            "utterleaf.obs_pairing_store.ObsPairingStore.__enter__",
            "utterleaf.obs_pairing_store.ObsPairingStore.claim_owner",
            "utterleaf.obs_pairing_store.ObsPairingStore.load",
            "utterleaf.obs_pairing_store.ObsPairingStore.import_package",
            "utterleaf.obs_pairing_store.ObsPairingStore.forget",
            "utterleaf.audio.Recorder", "sounddevice.InputStream",
            "socket.socket", "socket.create_connection", "subprocess.Popen",
            "webbrowser.open", "tkinter.Misc.clipboard_get",
            "tkinter.Misc.clipboard_clear", "tkinter.Misc.clipboard_append",
            "tkinter.filedialog.askopenfilename",
            "tkinter.filedialog.asksaveasfilename",
        ):
            stack.enter_context(patch(target, side_effect=deny(target)))
        for name in ("askyesno", "showinfo", "showerror", "showwarning"):
            stack.enter_context(patch(
                f"tkinter.messagebox.{name}", side_effect=deny(f"dialog:{name}")
            ))
        stack.enter_context(patch.object(threading.Thread, "start", hold_worker))
        yield runtime


def stage_dialog(owner, state):
    """Build the real dialog and apply one fixed presentation-only outcome."""
    valid = {case[0] for case in CASES}
    if state not in valid:
        raise ValueError(f"Unknown OBS pairing capture state: {state}")
    dialog = obs_pairing_ui.ObsPairingDialog(
        owner, store_factory=lambda: (_ for _ in ()).throw(
            AssertionError("Synthetic pairing store must not be opened")
        )
    )
    outcome = obs_pairing_ui._Outcome
    if state in {"importing", "cancelling"}:
        dialog._receive(outcome("refresh", "ready", False))
        dialog._submit("import", "C:/synthetic/transfer.ulobs", False)
        if state == "cancelling":
            dialog.cancel_import()
    elif state == "unpaired":
        dialog._receive(outcome("refresh", "ready", False))
    elif state == "paired":
        dialog._receive(outcome("refresh", "ready", True))
    elif state == "file-error":
        dialog._receive(outcome("import", "error", None))
    elif state == "uncertain":
        dialog._receive(outcome("import", "uncertain", None))
    elif state == "saved-file-kept":
        dialog._receive(outcome("import", "saved", True, False))
    else:
        dialog.stopped.set()
        dialog._receive(outcome("open", "unavailable", None))
    return dialog


def action_receipt(dialog):
    return {
        "import": str(dialog.import_button.cget("state")),
        "forget": str(dialog.forget_button.cget("state")),
        "refresh_label": str(dialog.refresh_button.cget("text")),
        "refresh": str(dialog.refresh_button.cget("state")),
        "cancel_mapped": bool(dialog.cancel_button.winfo_ismapped()),
    }


def capture_all(output):
    output = output.resolve()
    if not output.is_relative_to(ROOT / "artifacts"):
        raise ValueError("Capture output must stay inside this checkout's artifacts directory")
    output.mkdir(parents=True, exist_ok=False)
    manifest = {
        "scope": (
            "Synthetic OBS pairing presentation only; no pairing store, OBS, native dialog, "
            "physical display or accessibility acceptance"
        ),
        "platform": sys.platform,
        "python": sys.version.split()[0],
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "helpers": {
            name: hashlib.sha256((ROOT / "tests" / name).read_bytes()).hexdigest()
            for name in HELPER_NAMES
        },
        "sources": {
            name: hashlib.sha256((ROOT / "utterleaf" / name).read_bytes()).hexdigest()
            for name in SOURCE_NAMES
        },
        "captures": [],
        "status": "incomplete",
    }
    try:
        with blocked_runtime() as runtime:
            for (state, size, scale), filename in zip(CASES, INVENTORY):
                with owned_root(scale) as (owner, errors):
                    owner.geometry("1x1+5+5")
                    owner.deiconify()
                    settle(owner)
                    dialog = stage_dialog(owner, state)
                    guard_input(dialog.root, errors)
                    dialog.root.geometry(f"{size[0]}x{size[1]}+70+50")
                    dialog.root.deiconify()
                    settle(dialog.root)
                    dialog._reveal(dialog.status_label)
                    settle(dialog.root)
                    record = capture(dialog.root, errors, filename, size, output)
                    record.update(
                        state=state,
                        scale_multiplier=scale,
                        pairing_state=dialog.state.get(),
                        status_text=dialog.status.get(),
                        controls=action_receipt(dialog),
                    )
                    manifest["captures"].append(record)
                    dialog.root.destroy()
            if runtime.violations:
                raise AssertionError("OBS pairing capture crossed an external boundary")
            if len(runtime.workers) != len(CASES):
                raise AssertionError("OBS pairing capture worker inventory mismatch")
        if tuple(record["file"] for record in manifest["captures"]) != INVENTORY:
            raise AssertionError("OBS pairing capture inventory mismatch")
        manifest["status"] = "completed"
    finally:
        (output / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
    print(f"Captured {len(manifest['captures'])} synthetic OBS pairing states in {output}")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    enable_dpi_awareness()
    capture_all(args.output)
