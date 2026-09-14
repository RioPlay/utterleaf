"""All-or-none recognition and export of explicitly selected recorded-file tracks."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import os
from pathlib import Path
import tempfile
import unicodedata

from utterleaf.config import Config
from utterleaf.file_metadata import MediaAudioTrack
from utterleaf.transcript import Transcript, TranscriptionCancelled, render_transcript


@dataclass(frozen=True)
class TrackTranscript:
    track: MediaAudioTrack
    transcript: Transcript

    def __post_init__(self) -> None:
        if type(self.track) is not MediaAudioTrack or type(self.transcript) is not Transcript:
            raise TypeError("Track transcript has invalid values")


@dataclass(frozen=True)
class FileTranscripts:
    timing: str
    origin: Fraction | None
    origin_kind: str
    tracks: tuple[TrackTranscript, ...]

    def __post_init__(self) -> None:
        tracks = tuple(self.tracks)
        object.__setattr__(self, "tracks", tracks)
        if self.timing not in {"relative", "recording"} or not 1 <= len(tracks) <= 256:
            raise ValueError("File transcripts have invalid timing or tracks")
        if any(type(item) is not TrackTranscript for item in tracks):
            raise TypeError("File transcripts contain an invalid track result")
        ordinals = [item.track.ordinal for item in tracks]
        if len(set(ordinals)) != len(ordinals):
            raise ValueError("File transcripts contain duplicate tracks")
        if self.timing == "relative":
            if self.origin is not None or self.origin_kind != "track-relative":
                raise ValueError("Relative file transcripts have an invalid clock")
        elif (
            type(self.origin) is not Fraction
            or self.origin_kind not in {"container", "all-stream-starts", "pcm-sample-clock"}
        ):
            raise ValueError("Recording file transcripts have an invalid clock")

    @property
    def text(self) -> str:
        return preview_file_transcripts(self)


def _cancel(cancel) -> None:
    if cancel is not None and cancel.is_set():
        raise TranscriptionCancelled("File track transcription cancelled")


def _selected_tracks(metadata, requested) -> tuple[MediaAudioTrack, ...]:
    if isinstance(requested, (str, bytes)):
        raise ValueError("Choose audio track numbers from 1 to 256")
    try:
        iterator = iter(requested)
    except TypeError:
        raise ValueError("Choose audio track numbers from 1 to 256") from None
    numbers = []
    for value in iterator:
        if len(numbers) == 256 or type(value) is not int or not 1 <= value <= 256:
            raise ValueError("Choose at most 256 unique audio track numbers from 1 to 256")
        if value in numbers:
            raise ValueError(f"Audio track {value} was selected more than once")
        numbers.append(value)
    if not numbers:
        raise ValueError("Choose at least one audio track")
    available = {track.ordinal: track for track in metadata.tracks}
    selected = []
    for number in numbers:
        track = available.get(number - 1)
        if track is None:
            raise ValueError(f"Audio track {number} is not present in the selected file")
        selected.append(track)
    return tuple(selected)


def export_destinations(path: str | Path, numbers) -> tuple[Path, ...]:
    """Map 1-based track numbers to one file, or to distinct grouped siblings."""
    path = Path(path)
    if isinstance(numbers, (str, bytes)):
        raise ValueError("Choose audio track numbers from 1 to 256")
    try:
        values = tuple(numbers)
    except TypeError:
        raise ValueError("Choose audio track numbers from 1 to 256") from None
    if not values:
        raise ValueError("Choose at least one audio track")
    grouped = len(values) > 1
    destinations = []
    seen = set()
    for number in values:
        if type(number) is not int or not 1 <= number <= 256:
            raise ValueError("Choose audio track numbers from 1 to 256")
        destination = path if not grouped else path.with_name(f"{path.stem}-track{number}{path.suffix}")
        key = (destination.parent, destination.name)
        if key in seen:
            raise ValueError("Grouped export destinations must be unique")
        seen.add(key)
        destinations.append(destination)
    return tuple(destinations)


def preview_file_transcripts(results: FileTranscripts) -> str:
    """Plain preview text; a single track stays unlabeled."""
    if type(results) is not FileTranscripts:
        raise TypeError("Preview requires grouped file transcripts")
    if all(not item.transcript.text for item in results.tracks):
        return ""
    if len(results.tracks) == 1:
        return results.tracks[0].transcript.text

    def heading(track: MediaAudioTrack) -> str:
        title = " ".join((track.title or "").split())
        title = "".join(" " if unicodedata.category(char).startswith("C") else char for char in title)
        title = " ".join(title.split()).strip()
        label = f"Track {track.ordinal + 1}"
        return f"{label} — {title}" if title else label

    return "\n\n".join(
        f"{heading(item.track)}\n{item.transcript.text}".rstrip()
        for item in results.tracks
    )


def export_transcripts(results: FileTranscripts, path: str | Path, format: str | None = None,
                       *, overwrite: bool = False) -> tuple[Path, ...]:
    """Publish every selected track together, or leave existing files unchanged."""
    if type(results) is not FileTranscripts:
        raise TypeError("Grouped export requires file transcripts")
    numbers = tuple(item.track.ordinal + 1 for item in results.tracks)
    destinations = export_destinations(path, numbers)
    payloads = tuple(
        (destination, render_transcript(item.transcript, format or destination.suffix))
        for item, destination in zip(results.tracks, destinations)
    )
    if not overwrite:
        existing = next((destination for destination, _text in payloads if destination.exists()), None)
        if existing is not None:
            raise FileExistsError(existing)

    published = []
    temps = []
    try:
        for destination, text in payloads:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                             dir=destination.parent, delete=False) as stream:
                temps.append(Path(stream.name))
                stream.write(text)
        remaining = list(temps)
        for temporary, (destination, _text) in zip(remaining, payloads):
            if overwrite:
                os.replace(temporary, destination)
            else:
                os.link(temporary, destination)
            temps.remove(temporary)
            temporary.unlink(missing_ok=True)
            published.append(destination)
    except Exception:
        if not overwrite:
            for destination in published:
                destination.unlink(missing_ok=True)
        raise
    finally:
        for temporary in temps:
            temporary.unlink(missing_ok=True)
    return tuple(published)


def transcribe_tracks(
    path: str | Path,
    cfg: Config,
    *,
    audio_tracks,
    timing: str = "relative",
    cancel=None,
    progress=None,
    expected_signature=None,
) -> FileTranscripts:
    """Recognize selected tracks sequentially and publish only the complete group."""
    from utterleaf.file_external import _HeldSource
    from utterleaf.file_inspection import current_file_signature, inspect_file
    from utterleaf.file_transcription import transcribe_file

    if type(timing) is not str or timing not in {"relative", "recording"}:
        raise ValueError("File timing must be 'relative' or 'recording'")
    _cancel(cancel)
    if expected_signature is not None and current_file_signature(path) != expected_signature:
        raise ValueError("The selected file changed. Inspect its tracks again.")
    inspected = inspect_file(path, cancel=cancel)
    if expected_signature is not None and inspected.signature != expected_signature:
        raise ValueError("The selected file changed. Inspect its tracks again.")
    selected = _selected_tracks(inspected.metadata, audio_tracks)
    if timing == "recording":
        if (
            type(inspected.metadata.origin) is not Fraction
            or inspected.metadata.origin_kind
            not in {"container", "all-stream-starts", "pcm-sample-clock"}
        ):
            raise ValueError("The selected file has no common recording clock")
        origin = inspected.metadata.origin
        origin_kind = inspected.metadata.origin_kind
        expected_clock = (origin, origin_kind) if len(selected) > 1 else None
    else:
        origin, origin_kind, expected_clock = None, "track-relative", None

    path = Path(path)
    results = []
    with _HeldSource(path) as source:
        if current_file_signature(path) != inspected.signature:
            raise ValueError("The selected file changed. Inspect its tracks again.")
        total = len(selected)
        for position, track in enumerate(selected, 1):
            _cancel(cancel)
            source.check()

            def track_progress(phase, amount, *, current=position):
                if progress is not None:
                    progress(current, total, phase, amount)

            transcript = transcribe_file(
                path,
                cfg,
                audio_track=track.ordinal,
                timing=timing,
                cancel=cancel,
                progress=track_progress if progress is not None else None,
                _expected_clock=expected_clock,
            )
            source.check()
            results.append(TrackTranscript(track, transcript))
        source.check()
    _cancel(cancel)
    return FileTranscripts(timing, origin, origin_kind, tuple(results))


__all__ = [
    "FileTranscripts",
    "TrackTranscript",
    "export_destinations",
    "export_transcripts",
    "preview_file_transcripts",
    "transcribe_tracks",
]
