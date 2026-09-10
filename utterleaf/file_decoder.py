"""Optional, explicitly selected FFmpeg process; no bundled codecs or downloads."""

from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import queue
import stat
import subprocess
import sys
import threading
import time

import numpy as np

from utterleaf import config
from utterleaf.transcript import TranscriptionCancelled

DOWNLOAD_URL = "https://ffmpeg.org/download.html"
MAX_EXECUTABLE_BYTES = 512 * 1024 * 1024
DECODE_TIMEOUT_SECONDS = 120.0
BLOCK_BYTES = 65536
# Force a selected container: playlists, devices, scripts and concat are excluded.
FORMATS = {".mp3": "mp3", ".aac": "aac", ".m4a": "mov", ".m4b": "mov",
           ".mp4": "mov", ".mov": "mov", ".flac": "flac", ".ogg": "ogg",
           ".opus": "ogg", ".webm": "matroska", ".mkv": "matroska", ".wav": "wav"}


class DecoderSetupError(RuntimeError):
    pass


def _settings_path() -> Path:
    return config.data_dir() / "file-decoder.json"


def _identity(path: Path) -> str:
    if not path.is_absolute() or path.name.lower() not in {"ffmpeg", "ffmpeg.exe"}:
        raise DecoderSetupError("Choose the installed ffmpeg executable, not an archive or installer")
    # Never choose an executable from a network share implicitly.
    if str(path).startswith(("\\\\", "//")):
        raise DecoderSetupError("Choose FFmpeg installed on this computer, not a network share")
    try:
        if str(path.resolve()).startswith(("\\\\", "//")) or not stat.S_ISREG(path.stat().st_mode):
            raise DecoderSetupError("Choose a regular local FFmpeg executable")
        with path.open("rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_EXECUTABLE_BYTES:
                raise DecoderSetupError("The selected FFmpeg executable is invalid or too large")
            if sys.platform == "win32" and stream.read(2) != b"MZ":
                raise DecoderSetupError("Choose ffmpeg.exe, not a script or installer archive")
            stream.seek(0)
            digest = hashlib.sha256()
            count = 0
            while block := stream.read(1024 * 1024):
                count += len(block)
                if count > MAX_EXECUTABLE_BYTES:
                    raise DecoderSetupError("The selected FFmpeg executable is too large")
                digest.update(block)
            return digest.hexdigest()
    except OSError as exc:
        raise DecoderSetupError("FFmpeg could not be read. Choose its installed executable again.") from exc


def select_decoder(path: str | Path) -> Path:
    """Remember a user-approved executable without running it. No PATH searching."""
    path = Path(path).absolute()
    digest = _identity(path)
    config.atomic_write_text(_settings_path(), json.dumps({"version": 1, "path": str(path), "sha256": digest}) + "\n")
    return path


def forget_decoder() -> None:
    """Forget the selection, leaving the user's installation untouched."""
    _settings_path().unlink(missing_ok=True)


def decoder_selection() -> dict | None:
    try:
        settings = _settings_path()
        if not stat.S_ISREG(settings.lstat().st_mode) or settings.is_symlink():
            raise DecoderSetupError("Decoder settings must be a regular local file. Open More formats and select FFmpeg again.")
        with settings.open("rb") as stream:
            payload = stream.read(16385)
    except FileNotFoundError:
        return None
    try:
        if len(payload) > 16384:
            raise ValueError()
        value = json.loads(payload)
        if (not isinstance(value, dict) or set(value) != {"version", "path", "sha256"}
                or type(value["version"]) is not int or value["version"] != 1
                or not isinstance(value["path"], str) or not isinstance(value["sha256"], str)
                or len(value["sha256"]) != 64 or any(c not in "0123456789abcdef" for c in value["sha256"])):
            raise ValueError()
        return value
    except (ValueError, TypeError, UnicodeError):
        raise DecoderSetupError("Decoder settings are invalid. Open More formats and choose FFmpeg again.") from None


def _command(executable: Path, path: Path, seconds: float) -> list[str]:
    format = FORMATS.get(path.suffix.lower())
    if format is None:
        raise ValueError("Choose MP3, M4A, AAC, FLAC, OGG, Opus, MP4, MOV, WebM, MKV, or WAV media")
    options = [str(executable), "-nostdin", "-hide_banner", "-loglevel", "error", "-nostats",
               "-xerror", "-max_alloc", "67108864", "-threads", "2", "-filter_threads", "1",
               "-protocol_whitelist", "file", "-format_whitelist", format, "-f", format]
    if format == "mov":
        options += ["-enable_drefs", "0", "-use_absolute_path", "0"]
    return options + ["-i", str(path), "-map", "0:a:0", "-vn", "-sn", "-dn", "-ac", "1",
                      "-ar", "16000", "-t", str(seconds + 0.001), "-f", "s16le", "pipe:1"]


def decode_with_ffmpeg(path: Path, *, max_bytes: int, max_seconds: float,
                       cancel=None, progress=None) -> np.ndarray:
    """Bound PCM and process lifetime; the selected executable remains trusted code."""
    def check():
        if cancel is not None and cancel.is_set():
            raise TranscriptionCancelled("File transcription cancelled")

    check()
    path = Path(path).absolute()
    if str(path).startswith(("\\\\", "//")):
        raise ValueError("Select a media file on this computer, not a network share")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= max_bytes:
        raise ValueError("Select a nonempty local file no larger than 256 MiB")
    selected = decoder_selection()
    if selected is None:
        raise DecoderSetupError("For MP3, M4A and video, open More formats and select a local FFmpeg installation. PCM WAV needs no setup.")
    executable = Path(selected["path"])
    if _identity(executable) != selected["sha256"]:
        raise DecoderSetupError("FFmpeg changed since you selected it. Open More formats and select the updated executable again.")
    check()
    command = _command(executable, path, max_seconds)
    environment = os.environ.copy()
    environment.pop("FFREPORT", None)  # Never create FFmpeg's automatic report file.
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    try:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, shell=False, cwd=executable.parent,
                                   env=environment, creationflags=flags)
    except OSError as exc:
        raise DecoderSetupError("FFmpeg could not start. Check the installation in More formats.") from exc
    chunks = queue.Queue(maxsize=4)
    stopped = threading.Event()

    def reader():
        try:
            while not stopped.is_set():
                data = process.stdout.read(BLOCK_BYTES)
                while not stopped.is_set():
                    try:
                        chunks.put(data, timeout=0.1)
                        break
                    except queue.Full:
                        pass
                if not data:
                    return
        except (OSError, ValueError):
            while not stopped.is_set():
                try:
                    chunks.put(None, timeout=0.1)
                    return
                except queue.Full:
                    pass

    thread = threading.Thread(target=reader, name="utterleaf-decoder-output", daemon=True)
    thread.start()
    raw = io.BytesIO()
    deadline = time.monotonic() + DECODE_TIMEOUT_SECONDS
    try:
        while True:
            check()
            if time.monotonic() >= deadline:
                raise RuntimeError("Media decoding took too long and was stopped. Try a shorter or different file.")
            try:
                data = chunks.get(timeout=0.1)
            except queue.Empty:
                continue
            if data is None:
                raise RuntimeError("Could not read decoded audio from FFmpeg")
            if not data:
                break
            if raw.tell() + len(data) > max_seconds * 16000 * 2:
                raise ValueError("File audio exceeds the current 10-minute limit; select a shorter clip")
            raw.write(data)
            if progress is not None:
                progress("decoding", None)
        check()
        while process.poll() is None:
            check()
            if time.monotonic() >= deadline:
                raise RuntimeError("Media decoding took too long and was stopped")
            try:
                process.wait(timeout=0.1)
            except subprocess.TimeoutExpired:
                pass
        code = process.returncode
        if code != 0:
            raise RuntimeError("FFmpeg could not decode the selected audio track. The file may be damaged or unsupported by this installation.")
        if not raw.tell() or raw.tell() % 2:
            raise ValueError("The selected file contains no complete decodable audio")
        return np.frombuffer(raw.getbuffer(), dtype="<i2").astype(np.float32) / 32768.0
    finally:
        stopped.set()
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        thread.join(timeout=2)
        process.stdout.close()
