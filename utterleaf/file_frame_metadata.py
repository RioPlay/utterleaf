"""Strict parser for one compact FFprobe decoded-audio frame row."""

from __future__ import annotations

from dataclasses import dataclass
import re


_FIELDS = ("stream_index", "pts", "sample_fmt", "nb_samples", "channels", "channel_layout")
_SAMPLE_FORMATS = frozenset({
    "u8", "u8p", "s16", "s16p", "s32", "s32p", "s64", "s64p",
    "flt", "fltp", "dbl", "dblp",
})
_INTEGER = re.compile(r"(?:0|[1-9][0-9]*)\Z")
_SIGNED_INTEGER = re.compile(r"-?(?:0|[1-9][0-9]*)\Z")
_MAX_INT64 = 2**63 - 1


@dataclass(frozen=True)
class DecodedAudioFrame:
    stream_index: int
    pts: int
    sample_fmt: str
    nb_samples: int
    channels: int
    channel_layout: str


def _integer(value: str, *, signed: bool = False) -> int:
    if not isinstance(value, str) or len(value) > 20:
        raise ValueError("Invalid compact audio frame")
    pattern = _SIGNED_INTEGER if signed else _INTEGER
    if not pattern.fullmatch(value):
        raise ValueError("Invalid compact audio frame")
    parsed = int(value)
    lower = -(_MAX_INT64 + 1) if signed else 0
    if not lower <= parsed <= _MAX_INT64:
        raise ValueError("Invalid compact audio frame")
    return parsed


def _keyword_integer(value) -> int:
    if type(value) is not int:
        raise ValueError("Invalid compact audio frame")
    if not -_MAX_INT64 <= value <= _MAX_INT64:
        raise ValueError("Invalid compact audio frame")
    if value < 0:
        raise ValueError("Invalid compact audio frame")
    return value


def parse_compact_audio_frame(
    payload: bytes,
    *,
    sample_rate: int,
    expected_stream_index: int,
) -> DecodedAudioFrame:
    """Parse one ``escape=c`` FFprobe row with a bounded decoded sample count."""
    if not isinstance(payload, bytes) or len(payload) > 512:
        raise ValueError("Invalid compact audio frame")
    rate = _keyword_integer(sample_rate)
    if not 1 <= rate <= 384000:
        raise ValueError("Invalid compact audio frame")
    expected = _keyword_integer(expected_stream_index)
    if payload.endswith(b"\r\n"):
        body = payload[:-2]
    elif payload.endswith(b"\n"):
        body = payload[:-1]
    else:
        body = payload
    if not body or b"\n" in body or b"\r" in body:
        raise ValueError("Invalid compact audio frame")
    try:
        text = body.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise ValueError("Invalid compact audio frame") from None
    parts = text.split("|")
    if len(parts) != len(_FIELDS):
        raise ValueError("Invalid compact audio frame")
    values = {}
    for part in parts:
        if not part or "=" not in part:
            raise ValueError("Invalid compact audio frame")
        key, value = part.split("=", 1)
        if key not in _FIELDS or key in values or not value:
            raise ValueError("Invalid compact audio frame")
        if "\\" in value or "|" in value or any(ord(ch) < 0x20 or ord(ch) == 0x7f for ch in value):
            raise ValueError("Invalid compact audio frame")
        values[key] = value
    if set(values) != set(_FIELDS):
        raise ValueError("Invalid compact audio frame")
    stream_index = _integer(values["stream_index"])
    if values["pts"] == "N/A":
        raise ValueError("Original audio frame timing is unavailable")
    pts = _integer(values["pts"], signed=True)
    sample_fmt = values["sample_fmt"]
    if sample_fmt not in _SAMPLE_FORMATS:
        raise ValueError("Invalid compact audio frame")
    nb_samples = _integer(values["nb_samples"])
    if not 1 <= nb_samples <= 60 * rate:
        raise ValueError("Invalid compact audio frame")
    channels = _integer(values["channels"])
    if not 1 <= channels <= 32:
        raise ValueError("Invalid compact audio frame")
    layout = values["channel_layout"]
    if len(layout) > 128 or not layout.strip() or any(not 0x20 <= ord(ch) <= 0x7e for ch in layout) or "=" in layout:
        raise ValueError("Invalid compact audio frame")
    if stream_index != expected:
        raise ValueError("Invalid compact audio frame")
    return DecodedAudioFrame(stream_index, pts, sample_fmt, nb_samples, channels, layout)


__all__ = ["DecodedAudioFrame", "parse_compact_audio_frame"]
