"""Strict, bounded parsing of explicitly obtained FFprobe metadata."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import json
import re
from typing import Literal
import unicodedata


MAX_PAYLOAD_BYTES = 1 * 1024 * 1024
MAX_STREAMS = 256
MAX_TEXT_LENGTH = 256
MAX_INT64 = 2**63 - 1
MAX_AUDIO_TICK = Fraction(1, 1000)
_INTEGER = re.compile(r"-?[0-9]+\Z")
_DECIMAL = re.compile(r"[-+]?[0-9]+(?:\.[0-9]+)?\Z")


@dataclass(frozen=True)
class MediaAudioTrack:
    ordinal: int
    stream_index: int
    codec: str
    sample_rate: int
    channels: int
    layout: str | None
    title: str | None
    language: str | None
    is_default: bool
    start: Fraction | None
    time_base: Fraction


@dataclass(frozen=True)
class MediaMetadata:
    origin: Fraction | None
    origin_kind: Literal["container", "all-stream-starts", "pcm-sample-clock", "unavailable"]
    tracks: tuple[MediaAudioTrack, ...]


def _bounded_text(value, field: str, *, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if not isinstance(value, str) or len(value) > MAX_TEXT_LENGTH:
        raise ValueError(f"Media metadata field {field} is invalid or too long")
    if not value.strip() or any(unicodedata.category(char).startswith("C") for char in value):
        raise ValueError(f"Media metadata field {field} contains unsupported control text")
    return value


def _display_text(value, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > MAX_TEXT_LENGTH * 4:
        raise ValueError(f"Media metadata field {field} is invalid or too long")
    cleaned = "".join(" " if unicodedata.category(char).startswith("C") else char
                      for char in value)
    cleaned = " ".join(cleaned.split())[:MAX_TEXT_LENGTH].strip()
    return cleaned or None


def _integer(value, field: str, *, minimum: int = 0, maximum: int = MAX_INT64) -> int:
    if type(value) is int:
        parsed = value
    elif isinstance(value, str) and len(value) <= 20 and _INTEGER.fullmatch(value):
        parsed = int(value)
    else:
        raise ValueError(f"Media metadata field {field} is invalid")
    if not minimum <= parsed <= maximum:
        raise ValueError(f"Media metadata field {field} is outside its safe range")
    return parsed


def _time_base(value, field: str) -> Fraction:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,19}/[0-9]{1,19}", value):
        raise ValueError(f"Media metadata field {field} has an invalid time base")
    numerator, denominator = value.split("/", 1)
    if not _INTEGER.fullmatch(numerator) or not _INTEGER.fullmatch(denominator):
        raise ValueError(f"Media metadata field {field} has an invalid time base")
    numerator_int, denominator_int = int(numerator), int(denominator)
    if not 0 < numerator_int <= MAX_INT64 or not 0 < denominator_int <= MAX_INT64:
        raise ValueError(f"Media metadata field {field} has an unsafe time base")
    return Fraction(numerator_int, denominator_int)


def _timestamp(value, field: str) -> Fraction:
    if not isinstance(value, str) or len(value) > 64 or not _DECIMAL.fullmatch(value):
        raise ValueError(f"Media metadata field {field} is invalid")
    try:
        result = Fraction(value)
    except (ValueError, ZeroDivisionError, OverflowError):
        raise ValueError(f"Media metadata field {field} is invalid") from None
    if abs(result.numerator) > MAX_INT64 or result.denominator > MAX_INT64:
        raise ValueError(f"Media metadata field {field} is invalid")
    return result


def _stream_start(stream: dict, *, required: bool) -> Fraction | None:
    pts = stream.get("start_pts")
    time_base = stream.get("time_base")
    if pts is None:
        if required:
            raise ValueError("The media has missing or invalid A/V stream timing")
        return None
    if time_base is None:
        raise ValueError("The media has incomplete A/V stream timing")
    return _integer(pts, "start_pts", minimum=-MAX_INT64) * _time_base(time_base, "time_base")


def parse_media_metadata(payload: bytes, *, require_origin: bool = True) -> MediaMetadata:
    """Parse bounded JSON; only relative-track inventory may omit a common clock.

    Missing timing is represented as None/unavailable, never a fabricated zero.
    Present malformed timing remains invalid in either mode.
    """
    if not isinstance(payload, bytes) or len(payload) > MAX_PAYLOAD_BYTES:
        raise ValueError("Media metadata is missing or exceeds the 1 MiB limit")
    def reject_duplicates(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = item
        return result

    def reject_constant(constant):
        raise ValueError(constant)

    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=reject_duplicates,
                           parse_constant=reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, OverflowError, ValueError):
        raise ValueError("Media metadata is not valid UTF-8 JSON") from None
    if not isinstance(value, dict) or not isinstance(value.get("streams"), list):
        raise ValueError("Media metadata must contain a stream list")
    streams = value["streams"]
    if len(streams) > MAX_STREAMS:
        raise ValueError("The media contains too many streams")

    seen: set[int] = set()
    audio_rows = []
    av_rows = []
    for stream in streams:
        if not isinstance(stream, dict):
            raise ValueError("Media metadata contains an invalid stream")
        index = _integer(stream.get("index"), "index")
        if index in seen:
            raise ValueError("Media metadata contains duplicate stream indexes")
        seen.add(index)
        stream_type = stream.get("codec_type")
        if not isinstance(stream_type, str):
            raise ValueError("Media metadata contains an invalid codec type")
        if stream_type not in {"audio", "video"}:
            continue
        time_base = _time_base(stream.get("time_base"), "time_base")
        if stream_type == "audio":
            if time_base > MAX_AUDIO_TICK:
                raise ValueError("Audio timestamp precision is too coarse")
            codec = _bounded_text(stream.get("codec_name"), "codec_name")
            sample_rate = _integer(stream.get("sample_rate"), "sample_rate", maximum=384_000)
            channels = _integer(stream.get("channels"), "channels", maximum=32)
            if sample_rate < 1 or channels < 1:
                raise ValueError("Media audio format is outside its safe range")
            layout = _bounded_text(stream.get("channel_layout"), "channel_layout", optional=True)
            tags = stream.get("tags", {})
            if "tags" in stream and tags is None:
                raise ValueError("Media stream tags are invalid")
            if not isinstance(tags, dict):
                raise ValueError("Media stream tags are invalid")
            title = _display_text(tags.get("title"), "title")
            language = _display_text(tags.get("language"), "language")
            disposition = stream.get("disposition", {})
            if "disposition" in stream and disposition is None:
                raise ValueError("Media stream disposition is invalid")
            if not isinstance(disposition, dict):
                raise ValueError("Media stream disposition is invalid")
            default = _integer(disposition.get("default", 0), "default", maximum=1)
            start = _stream_start(stream, required=False)
            audio_rows.append((index, codec, sample_rate, channels, layout, title,
                               language, bool(default), start, time_base))
        av_rows.append((stream, time_base))

    if not audio_rows:
        raise ValueError("The selected file has no audio track")
    format_value = value.get("format", {})
    if "format" in value and format_value is None:
        raise ValueError("Media format metadata is invalid")
    if not isinstance(format_value, dict):
        raise ValueError("Media format metadata is invalid")
    raw_origin = format_value.get("start_time")
    if raw_origin is None or raw_origin == "N/A":
        origin = None
    else:
        origin = _timestamp(raw_origin, "format.start_time")
    if origin is None:
        starts = []
        missing_start = False
        for stream, time_base in av_rows:
            pts = stream.get("start_pts")
            if pts is None:
                missing_start = True
            else:
                starts.append(_integer(pts, "start_pts", minimum=-MAX_INT64) * time_base)
        if missing_start or not starts:
            if require_origin:
                raise ValueError("The media has missing or invalid A/V stream timing")
            origin_kind = "unavailable"
        else:
            origin = min(starts)
            origin_kind = "all-stream-starts"
    else:
        origin_kind = "container"

    tracks = tuple(
        MediaAudioTrack(ordinal, index, codec, rate, channels, layout, title, language,
                        default, start, time_base)
        for ordinal, (index, codec, rate, channels, layout, title, language,
                      default, start, time_base) in enumerate(audio_rows)
    )
    return MediaMetadata(origin, origin_kind, tracks)


__all__ = ["MediaAudioTrack", "MediaMetadata", "parse_media_metadata"]
