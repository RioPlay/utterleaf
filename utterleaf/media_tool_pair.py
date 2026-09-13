"""Bounded parsing and comparison of paired FFmpeg tool banners."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

from utterleaf.file_decoder import DecoderSetupError


_LIBRARIES = ("avutil", "avcodec", "avformat", "avdevice", "avfilter", "swscale", "swresample")
_VERSION = re.compile(r"[!-~]{1,256}\Z")
_LIBRARY_VERSION = re.compile(r"[0-9]{1,3}\.\s*[0-9]{1,3}\.\s*[0-9]{1,3}\Z")
_LIBRARY = re.compile(r"lib([a-z]+)\s+([0-9. ]+)\s*/\s*([0-9. ]+)\Z")


@dataclass(frozen=True)
class ToolBuildFingerprint:
    version: str
    compiler: str
    configuration: str
    libraries: tuple[tuple[str, tuple[int, ...], tuple[int, ...]], ...]

    def __post_init__(self):
        _validate_fingerprint(self)


def _fail():
    raise DecoderSetupError("FFmpeg and FFprobe must be matching verified builds")


def _version(value: object) -> str:
    if type(value) is not str or not _VERSION.fullmatch(value):
        _fail()
    return value


def _library_version(value: str) -> tuple[int, ...]:
    value = value.strip()
    if not _LIBRARY_VERSION.fullmatch(value):
        _fail()
    return tuple(int(part) for part in value.replace(" ", "").split("."))


def _validate_fingerprint(value: ToolBuildFingerprint) -> None:
    _version(value.version)
    if (
        type(value.compiler) is not str
        or not value.compiler.startswith("built with ")
        or not value.compiler[len("built with "):].strip()
        or type(value.configuration) is not str
        or not value.configuration.startswith("configuration: ")
        or not value.configuration[len("configuration: "):].strip()
    ):
        _fail()
    for text in (value.compiler, value.configuration):
        if len(text) > 16384 or any(not 0x20 <= ord(ch) <= 0x7E for ch in text):
            _fail()
    if type(value.libraries) is not tuple or len(value.libraries) != len(_LIBRARIES):
        _fail()
    for expected_name, item in zip(_LIBRARIES, value.libraries):
        if (type(item) is not tuple or len(item) != 3
                or type(item[0]) is not str or item[0] != expected_name):
            _fail()
        for version in item[1:]:
            if (
                type(version) is not tuple
                or len(version) != 3
                or any(type(part) is not int or not 0 <= part <= 999 for part in version)
            ):
                _fail()


def parse_tool_version(payload: bytes, *, program: Literal["ffmpeg", "ffprobe"]) -> ToolBuildFingerprint:
    if program not in ("ffmpeg", "ffprobe") or not isinstance(payload, bytes) or len(payload) > 64 * 1024:
        _fail()
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        _fail()
    if "\r" in text.replace("\r\n", "") or any(
            ch not in "\r\n" and not 0x20 <= ord(ch) <= 0x7e for ch in text):
        _fail()
    lines = text.splitlines()
    if text.endswith("\n"):
        if lines and lines[-1] == "":
            lines.pop()
    if any("\r" in line for line in lines) or not lines:
        _fail()
    prefix = f"{program} version "
    header = re.fullmatch(
        re.escape(prefix) + r"([!-~]+) Copyright \(c\) (?:[0-9]{4}|[0-9]{4}-[0-9]{4}) the FFmpeg developers",
        lines[0],
    )
    if header is None:
        _fail()
    version = _version(header.group(1))
    if (len(lines) < 3 or not lines[1].startswith("built with ") or not lines[1][len("built with "):].strip()
            or not lines[2].startswith("configuration: ") or not lines[2][len("configuration: "):].strip()):
        _fail()
    compiler = lines[1]
    configuration = lines[2]
    for value in (compiler, configuration):
        if len(value) > 16384 or any(not 0x20 <= ord(ch) <= 0x7e for ch in value):
            _fail()
    remainder = lines[3:]
    if program == "ffmpeg" and len(remainder) >= 2 and remainder[-2:] == ["", "Exiting with exit code 0"]:
        remainder = remainder[:-2]
    if len(remainder) != len(_LIBRARIES):
        _fail()
    parsed = {}
    for line in remainder:
        match = _LIBRARY.fullmatch(line)
        if match is None:
            _fail()
        name, compiled, runtime = match.groups()
        if name not in _LIBRARIES or name in parsed:
            _fail()
        parsed[name] = (_library_version(compiled), _library_version(runtime))
    if set(parsed) != set(_LIBRARIES):
        _fail()
    return ToolBuildFingerprint(version, compiler, configuration,
                                tuple((name, *parsed[name]) for name in _LIBRARIES))


def compare_tool_pair(ffmpeg: ToolBuildFingerprint, ffprobe: ToolBuildFingerprint) -> None:
    if type(ffmpeg) is not ToolBuildFingerprint or type(ffprobe) is not ToolBuildFingerprint:
        _fail()
    _validate_fingerprint(ffmpeg)
    _validate_fingerprint(ffprobe)
    if (ffmpeg.version, ffmpeg.compiler, ffmpeg.configuration, ffmpeg.libraries) != \
            (ffprobe.version, ffprobe.compiler, ffprobe.configuration, ffprobe.libraries):
        _fail()


__all__ = ["ToolBuildFingerprint", "compare_tool_pair", "parse_tool_version"]
