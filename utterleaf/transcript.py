"""Timestamped local recognition results and explicit Unicode exports."""

from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
import tempfile


class TranscriptionCancelled(RuntimeError):
    """The caller cancelled; no transcript is saved automatically."""


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str

    def __post_init__(self):
        if not (math.isfinite(self.start) and math.isfinite(self.end)):
            raise ValueError("Segment timestamps must be finite")
        if self.start < 0 or self.end < self.start:
            raise ValueError("Segment timestamps must be nonnegative and ordered")


@dataclass(frozen=True)
class Transcript:
    segments: tuple[Segment, ...]
    language: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "segments", tuple(self.segments))
        if any(b.start < a.start for a, b in zip(self.segments, self.segments[1:])):
            raise ValueError("Transcript segments must be ordered by start time")

    @property
    def text(self) -> str:
        return " ".join(s.text.strip() for s in self.segments if s.text.strip())


def _timestamp(seconds: float, separator: str) -> str:
    milliseconds = int(seconds * 1000 + 0.5)
    hours, remainder = divmod(milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02}{separator}{milliseconds:03}"


def render_transcript(result: Transcript, format: str) -> str:
    format = format.lower().lstrip(".")
    if format == "txt":
        return result.text + ("\n" if result.text else "")
    if format not in {"srt", "vtt"}:
        raise ValueError("Export format must be txt, srt, or vtt")
    cues = []
    for segment in result.segments:
        text = " ".join(segment.text.split())
        if not text:
            continue
        start = _timestamp(segment.start, "," if format == "srt" else ".")
        end = _timestamp(segment.end, "," if format == "srt" else ".")
        if start == end:
            raise ValueError("Subtitle cue has no duration at millisecond precision")
        # Escape markup so recognized text is displayed literally by subtitle players.
        text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        cues.append(f"{len(cues) + 1}\n{start} --> {end}\n{text}\n")
    body = "\n".join(cues)
    return ("WEBVTT\n\n" if format == "vtt" else "") + body


def export_transcript(result: Transcript, path: str | Path, format: str | None = None,
                      *, overwrite: bool = False) -> Path:
    """Write only the selected destination, refusing existing files by default."""
    path = Path(path)
    text = render_transcript(result, format or path.suffix)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
        if overwrite:
            os.replace(temporary, path)
        else:
            # Atomic no-clobber publication; failure leaves existing content intact.
            os.link(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path
