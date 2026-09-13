"""Inspect explicit files before choosing tracks; ordinary PCM WAV needs no tool."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import os
from pathlib import Path
import stat
import wave

from utterleaf.file_metadata import MediaAudioTrack, MediaMetadata
from utterleaf.file_probe import probe_media
from utterleaf.local_filesystem import require_local_filesystem
from utterleaf.transcript import TranscriptionCancelled


@dataclass(frozen=True)
class InspectedFile:
    metadata: MediaMetadata
    signature: tuple[int, ...]


def _signature(info) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, stat.S_IFMT(info.st_mode), info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def current_file_signature(path: str | Path) -> tuple[int, ...]:
    """A source-change check, not a content authenticity claim; call off the UI."""
    path = require_local_filesystem(path)
    try:
        info = path.stat()
    except OSError:
        raise ValueError("The selected file is unavailable. Choose it again.") from None
    if not stat.S_ISREG(info.st_mode) or info.st_size <= 0:
        raise ValueError("Select a nonempty regular local file")
    return _signature(info)


def _cancel(cancel):
    if cancel is not None and cancel.is_set():
        raise TranscriptionCancelled("File inspection cancelled")


def _pcm_metadata(path: Path, cancel) -> MediaMetadata | None:
    try:
        with path.open("rb") as source:
            before = _signature(os.fstat(source.fileno()))
            with wave.open(source, "rb") as audio:
                channels, width, rate, frames, compression, _ = audio.getparams()
                # Match the packaged PCM reader's supported input contract.
                if (channels not in (1, 2) or width not in (1, 2, 3, 4)
                        or not 8000 <= rate <= 48000 or compression != "NONE"):
                    return None
                if frames <= 0:
                    raise ValueError("The selected file contains no audio samples")
            _cancel(cancel)
            if _signature(os.fstat(source.fileno())) != before:
                raise ValueError("The selected file changed. Inspect its tracks again.")
    except (wave.Error, EOFError):
        return None
    except OSError:
        raise ValueError("The selected file could not be inspected") from None
    codec = "pcm_u8" if width == 1 else f"pcm_s{width * 8}le"
    return MediaMetadata(Fraction(0), "pcm-sample-clock", (MediaAudioTrack(
        ordinal=0, stream_index=0, codec=codec, sample_rate=rate, channels=channels,
        layout="mono" if channels == 1 else "stereo", title=None, language=None,
        is_default=True, start=Fraction(0), time_base=Fraction(1, rate),
    ),))


def inspect_file(path: str | Path, *, cancel=None) -> InspectedFile:
    """Return track metadata plus a signature to recheck before recognition.

    PCM WAV describes one stream with a zero-based sample clock. This does not
    interpret BWF time references or claim synchronization with another file.
    Other media uses the explicitly selected FFprobe, with its own process and
    filesystem limits. No model is loaded and no audio is recorded or exported.
    """
    _cancel(cancel)
    path = require_local_filesystem(path)
    before = current_file_signature(path)
    metadata = _pcm_metadata(path, cancel) if path.suffix.lower() == ".wav" else None
    if metadata is None:
        # Legacy recognition uses each track's sample count, so timestamp-less
        # AAC may still be transcribed. Missing common timing stays explicit.
        metadata = probe_media(path, cancel=cancel, require_origin=False)
    _cancel(cancel)
    if current_file_signature(path) != before:
        raise ValueError("The selected file changed. Inspect its tracks again.")
    return InspectedFile(metadata, before)
