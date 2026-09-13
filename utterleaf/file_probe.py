"""Explicit, identity-checked FFprobe selection; never discovers or runs it."""

from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import stat
import subprocess
import sys
import threading
import time
from typing import TYPE_CHECKING

from utterleaf import config
from utterleaf.file_decoder import DecoderSetupError, FORMATS, executable_identity
from utterleaf.transcript import TranscriptionCancelled

if TYPE_CHECKING:
    from utterleaf.file_metadata import MediaMetadata


MAX_SETTINGS_BYTES = 16 * 1024
MAX_PROBE_BYTES = 1024 * 1024
PROBE_TIMEOUT_SECONDS = 30.0
READ_BYTES = 64 * 1024


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


def _source_fingerprint(info: os.stat_result) -> tuple[int, int, int, int, int, int]:
    """Fields stable across reads from the same stat API; access time is excluded."""
    return (
        stat.S_IFMT(info.st_mode),
        info.st_dev,
        info.st_ino,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _same_file(left: os.stat_result, right: os.stat_result) -> bool:
    """Compare a held handle with its pathname without comparing API-specific times."""
    if left.st_dev != right.st_dev:
        return False
    if left.st_ino and right.st_ino and left.st_ino != right.st_ino:
        return False
    return stat.S_IFMT(left.st_mode) == stat.S_IFMT(right.st_mode) and left.st_size == right.st_size


def _probe_command(executable: Path, path: Path) -> list[str]:
    media_format = FORMATS.get(path.suffix.lower())
    if media_format is None:
        raise ValueError(
            "Choose MP3, M4A, AAC, FLAC, OGG, Opus, MP4, MOV, WebM, MKV, or WAV media"
        )
    command = [
        str(executable),
        "-v", "error",
        "-max_alloc", "67108864",
        "-probesize", "8388608",
        "-analyzeduration", "5000000",
        "-protocol_whitelist", "file",
        "-format_whitelist", media_format,
        "-f", media_format,
    ]
    if media_format == "mov":
        command += ["-enable_drefs", "0", "-use_absolute_path", "0"]
    return command + [
        "-show_streams",
        "-show_format",
        "-show_entries",
        (
            "stream=index,codec_type,codec_name,sample_rate,channels,channel_layout,"
            "time_base,start_pts:stream_tags=language,title:stream_disposition=default:"
            "format=start_time"
        ),
        "-of", "json",
        "-i", str(path),
    ]


def _cancelled(cancel) -> bool:
    return cancel is not None and cancel.is_set()


def probe_media(path: Path | str, *, cancel=None, require_origin: bool = True) -> MediaMetadata:
    """Inspect one explicit local media file with a bounded verified FFprobe process."""
    from utterleaf.local_filesystem import require_local_filesystem

    if _cancelled(cancel):
        raise TranscriptionCancelled("File inspection cancelled")
    path = require_local_filesystem(path)
    try:
        path_preopen = path.stat()
    except OSError:
        raise ValueError("Select an existing local media file") from None
    if not stat.S_ISREG(path_preopen.st_mode) or path_preopen.st_size <= 0:
        raise ValueError("Select a nonempty regular local file")
    try:
        source = path.open("rb")
    except OSError:
        raise ValueError("Select an existing local media file") from None

    with source:
        try:
            handle_before = os.fstat(source.fileno())
            path_before = path.stat()
        except OSError:
            raise ValueError("The selected media file could not be inspected") from None
        if (
            not stat.S_ISREG(handle_before.st_mode)
            or handle_before.st_size <= 0
            or not stat.S_ISREG(path_before.st_mode)
            or path_before.st_size <= 0
            or _source_fingerprint(path_preopen) != _source_fingerprint(path_before)
            or not _same_file(handle_before, path_before)
        ):
            raise ValueError("Select a nonempty regular local file")

        # Identity verification is intentionally adjacent to process creation. The
        # operating-system pathname launch still has the same narrow replacement
        # window as the established FFmpeg runner.
        executable = verified_probe()
        command = _probe_command(executable, path)
        environment = os.environ.copy()
        environment.pop("FFREPORT", None)
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
        if _cancelled(cancel):
            raise TranscriptionCancelled("File inspection cancelled")
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                shell=False,
                cwd=executable.parent,
                env=environment,
                creationflags=flags,
            )
        except OSError:
            raise DecoderSetupError(
                "FFprobe could not start. Check the selected installation."
            ) from None

        output: queue.Queue[tuple[bool, bytes | None]] = queue.Queue(maxsize=1)

        def read_output() -> None:
            try:
                payload = bytearray()
                while len(payload) <= MAX_PROBE_BYTES:
                    block = process.stdout.read(
                        min(READ_BYTES, MAX_PROBE_BYTES + 1 - len(payload))
                    )
                    if not block:
                        break
                    payload.extend(block)
                result = (True, bytes(payload))
            except (OSError, ValueError):
                result = (False, None)
            try:
                output.put_nowait(result)
            except queue.Full:
                pass

        reader = threading.Thread(
            target=read_output, name="utterleaf-probe-output", daemon=True
        )
        failure: BaseException | None = None
        payload: bytes | None = None
        deadline = time.monotonic() + PROBE_TIMEOUT_SECONDS
        try:
            reader.start()
            while payload is None:
                if _cancelled(cancel):
                    raise TranscriptionCancelled("File inspection cancelled")
                if time.monotonic() >= deadline:
                    raise DecoderSetupError("Media inspection took too long and was stopped")
                try:
                    ok, candidate = output.get(timeout=0.1)
                except queue.Empty:
                    continue
                if not ok or candidate is None:
                    raise DecoderSetupError("Could not read metadata from FFprobe")
                if len(candidate) > MAX_PROBE_BYTES:
                    raise DecoderSetupError("FFprobe returned too much media metadata")
                payload = candidate

            while process.poll() is None:
                if _cancelled(cancel):
                    raise TranscriptionCancelled("File inspection cancelled")
                if time.monotonic() >= deadline:
                    raise DecoderSetupError("Media inspection took too long and was stopped")
                try:
                    process.wait(timeout=0.1)
                except subprocess.TimeoutExpired:
                    pass
            if process.returncode != 0:
                raise DecoderSetupError(
                    "FFprobe could not inspect this media file; it may be damaged or unsupported"
                )
        except (TranscriptionCancelled, DecoderSetupError, KeyboardInterrupt, SystemExit) as exc:
            failure = exc
        except Exception:
            failure = DecoderSetupError("FFprobe inspection could not continue")
        finally:
            if process.poll() is None:
                try:
                    process.kill()
                except OSError:
                    pass
            try:
                process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                if failure is None:
                    failure = DecoderSetupError("FFprobe could not be stopped safely")
            if reader.ident is not None:
                reader.join(timeout=2)
            if reader.is_alive():
                if not isinstance(failure, (KeyboardInterrupt, SystemExit)):
                    failure = DecoderSetupError("FFprobe output could not be stopped safely")
            else:
                try:
                    process.stdout.close()
                except (OSError, ValueError):
                    pass

        if failure is not None:
            raise failure
        if payload is None:
            raise DecoderSetupError("Could not read metadata from FFprobe")
        if _cancelled(cancel):
            raise TranscriptionCancelled("File inspection cancelled")
        try:
            handle_after = os.fstat(source.fileno())
            path_after = path.stat()
        except OSError:
            raise ValueError("The selected media file changed during inspection") from None
        if (
            _source_fingerprint(handle_before) != _source_fingerprint(handle_after)
            or _source_fingerprint(path_before) != _source_fingerprint(path_after)
            or not _same_file(handle_after, path_after)
        ):
            raise ValueError("The selected media file changed during inspection")

    from utterleaf.file_metadata import parse_media_metadata

    return parse_media_metadata(payload, require_origin=require_origin)


__all__ = [
    "forget_probe",
    "probe_media",
    "probe_selection",
    "select_probe",
    "verified_probe",
]
