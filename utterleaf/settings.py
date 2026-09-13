"""Small settings window. Writes config.toml so you do not have to edit it by hand."""

from __future__ import annotations

import subprocess
import sys
import math
from pathlib import Path

from utterleaf.config import Config, save
from utterleaf.host import default_hotkey
from utterleaf.hotkey import parse_hotkey
from utterleaf.polish import save_dictionary
from utterleaf.startup import set_enabled as set_startup

_HOTKEY_CHOICES = (
    ("Ctrl+Win", "ctrl+win"),
    ("Ctrl+Shift+Space", "ctrl+shift+space"),
    ("Right Ctrl", "right ctrl"),
    ("F8", "f8"),
    ("Custom…", ""),
)


def hotkey_presets() -> tuple[tuple[str, str], ...]:
    """Platform default first, then the rest. Custom always last."""
    wanted = default_hotkey()
    head = [item for item in _HOTKEY_CHOICES if item[1] == wanted]
    mid = [item for item in _HOTKEY_CHOICES if item[1] and item[1] != wanted]
    tail = [item for item in _HOTKEY_CHOICES if not item[1]]
    return tuple(head + mid + tail)

MODE_PRESETS = (
    ("Hold to talk", "hold"),
    ("Press to start / stop", "toggle"),
)

SYSTEM_DEFAULT = "System default"


class FormValidationError(ValueError):
    """Identify the editable field without parsing user-facing error text."""

    def __init__(self, field: str, message: str, line: int | None = None):
        self.field, self.line = field, line
        super().__init__(message)


class SettingsSaveError(RuntimeError):
    """Report durable progress without claiming a multi-file transaction."""

    def __init__(self, saved, failed, pending, cause):
        self.saved = tuple(saved)
        self.failed = failed
        self.pending = tuple(pending)
        details = [f"Saved: {', '.join(saved)}." if saved else "No changes were saved.",
                   f"Could not save {failed}: {cause}"]
        if pending:
            details.append(f"Not attempted: {', '.join(pending)}.")
        details.append("Your form entries are kept. Fix the problem and try Save again.")
        super().__init__("\n\n".join(details))


def microphone_choices(current: str = "") -> list[str]:
    try:
        from utterleaf.audio import list_input_names

        names = list_input_names()
    except Exception:
        names = []
    saved = current.strip()
    values = [SYSTEM_DEFAULT]
    if saved and saved not in names:
        values.append(saved)
    values.extend(names)
    return values


def apply_form(
    cfg: Config,
    *,
    hotkey: str,
    mode: str,
    model: str,
    device: str,
    language: str,
    denoise: str,
    beep: bool,
    indicator: bool,
    start_at_login: bool,
    live_preview: bool | None = None,
    microphone: str = "",
    names: str | None = None,
    remove_fillers: bool | None = None,
    fix_corrections: bool | None = None,
    restore_clipboard: bool | None = None,
    allow_network: bool | None = None,
    text_cleanup: bool | None = None,
    output_format: str | None = None,
    speech_end_enabled: bool | None = None,
    speech_end_pause_seconds: float | str | None = None,
    speech_end_insert: bool | None = None,
) -> Config:
    hotkey = hotkey.strip().lower()
    try:
        parse_hotkey(hotkey)
    except ValueError as exc:
        raise FormValidationError("hotkey", str(exc)) from exc
    if mode not in {"hold", "toggle"}:
        raise FormValidationError("mode", "Mode must be hold or toggle")
    if not model.strip():
        raise FormValidationError("model", "Choose a speech model.")
    if device.strip() not in {"auto", "cpu", "gpu", "npu"}:
        raise FormValidationError("device", "Choose Automatic, CPU, GPU, or NPU.")
    if denoise.strip() not in {"auto", "on", "off"}:
        raise FormValidationError("denoise", "Noise reduction must be auto, on, or off.")
    if not language.strip():
        raise FormValidationError("language", "Enter a language code, such as en, or auto.")
    if output_format is not None and output_format not in {"prose", "markdown"}:
        raise FormValidationError("output_format", "Choose prose or Markdown output.")
    for field, value in (("speech_end_enabled", speech_end_enabled),
                         ("speech_end_insert", speech_end_insert)):
        if value is not None and type(value) is not bool:
            raise FormValidationError(field, "Choose an available speech-end option.")
    pause = cfg.speech_end_pause_seconds
    if speech_end_pause_seconds is not None:
        if isinstance(speech_end_pause_seconds, bool):
            raise FormValidationError("speech_end_pause_seconds", "Choose a pause from 0.5 to 3 seconds.")
        try:
            pause = float(speech_end_pause_seconds)
        except (TypeError, ValueError):
            raise FormValidationError("speech_end_pause_seconds", "Choose a pause from 0.5 to 3 seconds.") from None
        if not math.isfinite(pause) or not 0.5 <= pause <= 3.0:
            raise FormValidationError("speech_end_pause_seconds", "Choose a pause from 0.5 to 3 seconds.")
    if names is not None:
        for number, line in enumerate(names.splitlines(), 1):
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split("=", 1)
            if len(parts) != 2 or not all(part.strip() for part in parts):
                raise FormValidationError("names", f"Vocabulary line {number}: use spoken = written.", line=number)
    mic = microphone.strip()
    if mic in {SYSTEM_DEFAULT, ""}:
        mic = ""
    updated = Config(**{**cfg.__dict__, **{
        "hotkey": hotkey,
        "mode": mode,
        "model": model.strip(),
        "device": device.strip(),
        "language": language.strip(),
        "denoise": denoise.strip(),
        "beep": beep,
        "indicator": indicator,
        "live_preview": cfg.live_preview if live_preview is None else live_preview,
        "microphone": mic,
        "remove_fillers": cfg.remove_fillers if remove_fillers is None else remove_fillers,
        "fix_corrections": cfg.fix_corrections if fix_corrections is None else fix_corrections,
        "restore_clipboard": cfg.restore_clipboard if restore_clipboard is None else restore_clipboard,
        "allow_network": cfg.allow_network if allow_network is None else allow_network,
        "text_cleanup": cfg.text_cleanup if text_cleanup is None else text_cleanup,
        "output_format": cfg.output_format if output_format is None else output_format,
        "speech_end_enabled": cfg.speech_end_enabled if speech_end_enabled is None else speech_end_enabled,
        "speech_end_pause_seconds": pause,
        "speech_end_insert": cfg.speech_end_insert if speech_end_insert is None else speech_end_insert,
    }})
    steps = [("dictation settings", lambda: save(updated))]
    if names is not None:
        steps.append(("vocabulary", lambda: save_dictionary(names)))
    steps.append(("start at login", lambda: set_startup(start_at_login)))
    saved = []
    for index, (label, action) in enumerate(steps):
        try:
            action()
        except Exception as exc:
            raise SettingsSaveError(saved, label, [item[0] for item in steps[index + 1:]], exc) from exc
        saved.append(label)
    return updated


def _relaunch(*args: str) -> None:
    """Spawn Utterleaf again with args. Works from a venv or a frozen exe."""
    exe = Path(sys.executable)
    if getattr(sys, "frozen", False) and sys.platform == "win32":
        gui = exe.with_name("utterleafw.exe")
        if gui.exists():
            exe = gui
    cmd = [str(exe), *args]
    if not getattr(sys, "frozen", False):
        cmd = [str(exe), "-m", "utterleaf", *args]
        runner = exe.with_name("pythonw.exe")
        if runner.exists():
            cmd = [str(runner), "-m", "utterleaf", *args]
    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(cmd, **kwargs)


def launch_settings() -> None:
    from utterleaf.settings_instance import activate

    if not activate():
        _relaunch("--settings")


def run_settings() -> int:
    from utterleaf.settings_ui import run

    return run()

