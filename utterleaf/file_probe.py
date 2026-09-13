"""Explicit, identity-checked FFprobe selection; never discovers or runs it."""

from __future__ import annotations

import json
from pathlib import Path
import stat

from utterleaf import config
from utterleaf.file_decoder import DecoderSetupError, executable_identity


MAX_SETTINGS_BYTES = 16 * 1024


def _settings_path() -> Path:
    return config.data_dir() / "file-probe.json"


def select_probe(path: str | Path) -> Path:
    """Remember a user-approved ffprobe executable without running it."""
    path = Path(path).absolute()
    digest = executable_identity(path, program="ffprobe")
    config.atomic_write_text(
        _settings_path(),
        json.dumps({"version": 1, "path": str(path), "sha256": digest}) + "\n",
    )
    return path


def forget_probe() -> None:
    """Forget only the selection; leave the executable untouched."""
    _settings_path().unlink(missing_ok=True)


def probe_selection() -> dict | None:
    """Read the bounded, versioned selection record without validating the file."""
    try:
        settings = _settings_path()
        if not stat.S_ISREG(settings.lstat().st_mode) or settings.is_symlink():
            raise DecoderSetupError(
                "FFprobe settings must be a regular local file. Select FFprobe again."
            )
        with settings.open("rb") as stream:
            payload = stream.read(MAX_SETTINGS_BYTES + 1)
    except FileNotFoundError:
        return None
    try:
        if len(payload) > MAX_SETTINGS_BYTES:
            raise ValueError()
        value = json.loads(payload)
        if (
            not isinstance(value, dict)
            or set(value) != {"version", "path", "sha256"}
            or type(value["version"]) is not int
            or value["version"] != 1
            or not isinstance(value["path"], str)
            or not isinstance(value["sha256"], str)
            or len(value["sha256"]) != 64
            or any(c not in "0123456789abcdef" for c in value["sha256"])
        ):
            raise ValueError()
        return value
    except (ValueError, TypeError, UnicodeError):
        raise DecoderSetupError(
            "FFprobe settings are invalid. Select its installed executable again."
        ) from None


def verified_probe() -> Path:
    """Return the selected unchanged ffprobe path, or raise an actionable error."""
    selected = probe_selection()
    if selected is None:
        raise DecoderSetupError(
            "Select the installed FFprobe executable before inspecting media metadata."
        )
    executable = Path(selected["path"])
    digest = executable_identity(executable, program="ffprobe")
    if digest != selected["sha256"]:
        raise DecoderSetupError(
            "FFprobe changed since you selected it. Select the updated executable again."
        )
    return executable


__all__ = ["forget_probe", "probe_selection", "select_probe", "verified_probe"]
