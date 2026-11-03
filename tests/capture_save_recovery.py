"""Guarded Settings-save captures: synthetic writes/IPC and post-alert evidence."""
from __future__ import annotations

import argparse
from contextlib import ExitStack, contextmanager
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys
import threading
from unittest.mock import patch

from capture_auxiliary import capture, settle
from capture_backup import guard_input
from capture_diagnostics import blocked_runtime as guarded_settings_runtime, bounds
from capture_settings import _window
from utterleaf.settings import FormValidationError, SettingsSaveError
from utterleaf.settings_ui import SettingsWindow, enable_dpi_awareness

ROOT = Path(__file__).resolve().parents[1]
REAL_SAVE = SettingsWindow.save
ERROR = "Synthetic persistence failure: /synthetic/private/settings.json"
RELOAD_ERROR = "Synthetic reload failure: /synthetic/private/app.sock"
STATES = ("config-failure", "vocabulary-failure", "startup-failure", "unknown-failure",
          "worker-start-failure", "full-reload-failure", "partial-reload-failure", "validation")
CASES = (*((state, (960, 780), 1.0) for state in STATES),
         ("vocabulary-failure", (760, 560), 2.0), ("unknown-failure", (760, 560), 2.0))
INVENTORY = tuple(f"save-{state}-{size[0]}x{size[1]}-{scale:g}x-post-alert.png"
                  for state, size, scale in CASES)
SOURCE_NAMES = ("settings_ui.py", "settings.py", "config.py", "ui_feedback.py", "theme.py")
HELPER_NAMES = ("capture_settings.py", "capture_diagnostics.py", "capture_auxiliary.py", "capture_backup.py")


@contextmanager
def blocked_runtime():
    with guarded_settings_runtime() as runtime, ExitStack() as stack:
        runtime.apply_calls = []

        def deny(name):
            def blocked(*_args, **_kwargs):
                runtime.violations.append(name)
                raise AssertionError(f"Save capture blocked {name}")
            return blocked

        for target in ("utterleaf.settings.save", "utterleaf.settings.save_dictionary",
                       "utterleaf.settings.set_startup", "utterleaf.startup.set_enabled"):
            stack.enter_context(patch(target, side_effect=deny(target)))
        stack.enter_context(patch("tkinter.messagebox.showwarning", side_effect=lambda title, message, **_:
            runtime.dialogs.append(("warning", title, str(message)))))
        yield runtime


def failure_for(state):
    if state == "config-failure":
        return SettingsSaveError((), "dictation settings", ("vocabulary", "start at login"), OSError(ERROR))
    if state in {"vocabulary-failure", "partial-reload-failure"}:
        return SettingsSaveError(("dictation settings",), "vocabulary", ("start at login",), OSError(ERROR))
    if state == "startup-failure":
        return SettingsSaveError(("dictation settings", "vocabulary"), "start at login", (), OSError(ERROR))
    if state == "unknown-failure":
        return RuntimeError(ERROR)
    if state == "validation":
        return FormValidationError("names", "Vocabulary line 1: use spoken = written.", line=1)
    return None


def stage(window, runtime, state):
    """Invoke the saved production method and its real, held worker completion."""
    if state not in STATES:
        raise ValueError(f"Unknown save capture state: {state}")
    window.vars["beep"].set(not window.vars["beep"].get())
    if state == "validation":
        window.names.delete("1.0", "end")
        window.names.insert("1.0", "synthetic missing separator")
    settle(window.root)
    before = window._snapshot()

    def apply(cfg, **values):
        runtime.apply_calls.append(values)
        failure = failure_for(state)
        if failure is not None:
            raise failure
        return replace(cfg, beep=values["beep"])

    def ipc(command):
        runtime.ipc_commands.append(command)
        if command != "reload":
            raise AssertionError("Unexpected IPC command")
        if state in {"full-reload-failure", "partial-reload-failure"}:
            raise OSError(RELOAD_ERROR)
        return "ok"

    with ExitStack() as stack:
        stack.enter_context(patch("utterleaf.settings_ui.apply_form", side_effect=apply))
        stack.enter_context(patch("utterleaf.ipc.send", side_effect=ipc))
        if state == "worker-start-failure":
            stack.enter_context(patch.object(threading.Thread, "start", side_effect=RuntimeError(ERROR)))
        runtime.allow_worker = True
        try:
            REAL_SAVE(window)
        except RuntimeError as exc:
            if state != "worker-start-failure" or str(exc) != ERROR:
                raise
            runtime.uncaught.append({"type": type(exc).__name__, "message": str(exc)})
        finally:
            runtime.allow_worker = False
        if runtime.workers:
            if len(runtime.workers) != 1:
                raise AssertionError("Expected one held save worker")
            runtime.workers.pop()()
            callback, value = window.events.get_nowait()
            callback(value)
        elif state != "worker-start-failure":
            raise AssertionError("Production save did not start its staged worker")
    if window._snapshot() != before:
        raise AssertionError("Save recovery changed the Settings draft")
    return before


def capture_all(output):
    output = output.resolve()
    if not output.is_relative_to(ROOT / "artifacts"):
        raise ValueError("Capture output must stay inside this checkout's artifacts directory")
    output.mkdir(parents=True, exist_ok=False)
    sources = (*SOURCE_NAMES, *(("save_presentation.py",) if (ROOT / "utterleaf/save_presentation.py").exists() else ()))
    manifest = {"scope": "Synthetic save presentation after intercepted alerts; native dialog interiors and real persistence are not certified",
        "platform": sys.platform, "python": sys.version.split()[0],
        "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "helpers": {name: hashlib.sha256((ROOT / "tests" / name).read_bytes()).hexdigest() for name in HELPER_NAMES},
        "sources": {name: hashlib.sha256((ROOT / "utterleaf" / name).read_bytes()).hexdigest() for name in sources},
        "captures": [], "status": "incomplete"}
    try:
        with blocked_runtime() as runtime:
            for (state, size, scale), filename in zip(CASES, INVENTORY):
                with _window(runtime, visible=False, text_scale=scale) as window:
                    errors = []
                    window.root.report_callback_exception = lambda kind, value, trace: errors.append(str(value))
                    guard_input(window.root, errors)
                    window.root.geometry(f"{size[0]}x{size[1]}+70+50")
                    window.root.deiconify()
                    settle(window.root)
                    starts = (len(runtime.dialogs), len(runtime.uncaught), len(runtime.ipc_commands), len(runtime.apply_calls))
                    draft = stage(window, runtime, state)
                    settle(window.root)
                    record = capture(window.root, errors, filename, size, output)
                    record["actions"] = {name: bounds(getattr(window, name), window.root)
                        for name in ("save_button", "close_button")}
                    if hasattr(window, "save_details_button"):
                        record["actions"]["save_details_button"] = bounds(window.save_details_button, window.root)
                    record.update(state=state, scale_multiplier=scale, status_text=window.status.get(),
                        footer_status=bounds(window.footer_status, window.root, clip=window.footer_status.master),
                        saving=window.saving, save_state=str(window.save_button.cget("state")),
                        reset_state=str(window.reset_button.cget("state")),
                        page=window._current_page, draft_unchanged=window._snapshot() == draft,
                        baseline_matches_draft=window.baseline == draft,
                        navigation={name: bounds(button, window.root, clip=button.master)
                                    for name, button in window.nav.items()},
                        intercepted_alerts=runtime.dialogs[starts[0]:], intercepted_uncaught=runtime.uncaught[starts[1]:],
                        ipc_commands=runtime.ipc_commands[starts[2]:], apply_calls=len(runtime.apply_calls) - starts[3])
                    manifest["captures"].append(record)
            if runtime.violations or runtime.blocked_actions or runtime.workers:
                raise AssertionError("Unexpected action in save recovery capture")
            manifest["scale_receipts"] = runtime.scale_receipts
        if tuple(record["file"] for record in manifest["captures"]) != INVENTORY:
            raise AssertionError("Save capture inventory mismatch")
        manifest["status"] = "completed"
    finally:
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Captured {len(manifest['captures'])} synthetic save states in {output}")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    enable_dpi_awareness()
    capture_all(args.output)
