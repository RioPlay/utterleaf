from __future__ import annotations

import pytest

from utterleaf.file_decoder import DecoderSetupError
from utterleaf.media_tool_pair import ToolBuildFingerprint, compare_tool_pair, parse_tool_version


LIBS = (("avutil", (61, 1, 101), (61, 1, 101)), ("avcodec", (63, 1, 101), (63, 1, 101)),
        ("avformat", (63, 1, 101), (63, 1, 101)), ("avdevice", (63, 1, 101), (63, 1, 101)),
        ("avfilter", (12, 1, 101), (12, 1, 101)), ("swscale", (10, 1, 101), (10, 1, 101)),
        ("swresample", (7, 1, 101), (7, 1, 101)))


def payload(program="ffmpeg", version="9.0.1"):
    start_year = "2000" if program == "ffmpeg" else "2007"
    lines = [f"{program} version {version} Copyright (c) {start_year}-2025 the FFmpeg developers",
             "built with gcc 16.1.0", "configuration: --enable-gpl"]
    lines += [f"lib{name:<12} {'.'.join(map(str, compiled))} / {'.'.join(map(str, runtime))}"
              for name, compiled, runtime in LIBS]
    if program == "ffmpeg":
        lines.append("")
        lines.append("Exiting with exit code 0")
    return ("\n".join(lines) + "\n").encode()


def test_parses_realistic_ffmpeg_and_ffprobe_banners_and_compares():
    ffmpeg = parse_tool_version(payload(), program="ffmpeg")
    ffprobe = parse_tool_version(payload("ffprobe"), program="ffprobe")
    assert ffmpeg == ffprobe
    compare_tool_pair(ffmpeg, ffprobe)
    assert ffmpeg.libraries == LIBS


@pytest.mark.parametrize("program", ["ffmpeg", "ffprobe"])
def test_accepts_crlf_and_rejects_wrong_program(program):
    parsed = parse_tool_version(payload(program).replace(b"\n", b"\r\n"), program=program)
    assert parsed.version == "9.0.1"
    with pytest.raises(DecoderSetupError):
        other = "ffprobe" if program == "ffmpeg" else "ffmpeg"
        parse_tool_version(payload(other), program=program)


@pytest.mark.parametrize("version", (
    "9.0.1-essentials_build-www.gyan.dev",
    "N-123456-gdeadbeef",
    "n9.0.1",
))
def test_accepts_single_token_release_and_snapshot_versions(version):
    assert parse_tool_version(payload(version=version), program="ffmpeg").version == version


def test_rejects_malformed_pair_fingerprint_or_extra_output():
    for mutator in (
        lambda p: p.replace(b"libavcodec", b"libavcodecX"),
        lambda p: p.replace(b"libswscale", b"libavutil"),
        lambda p: p.replace(b"Exiting with exit code 0", b"extra"),
    ):
        with pytest.raises(DecoderSetupError):
            parse_tool_version(mutator(payload()), program="ffmpeg")
    first = parse_tool_version(payload(), program="ffmpeg")
    for mutator in (
        lambda p: p.replace(b"9.0.1", b"9.0.2"),
        lambda p: p.replace(b"gcc 16.1.0", b"clang 19"),
        lambda p: p.replace(b"--enable-gpl", b"--disable-gpl"),
    ):
        with pytest.raises(DecoderSetupError):
            compare_tool_pair(first, parse_tool_version(mutator(payload()), program="ffmpeg"))


def test_rejects_malformed_utf8_extra_or_oversize():
    for bad in (b"", b"\xff", payload() + b"x", payload() + b"\n\n", payload() + b" " * 65000):
        with pytest.raises(DecoderSetupError):
            parse_tool_version(bad, program="ffmpeg")


@pytest.mark.parametrize("version", (
    "error output",
    " 9.0.1",
    "9.0.1 ",
    "x Copyright (c) 1111 the FFmpeg developers",
))
def test_rejects_whitespace_or_embedded_banner_text_in_version(version):
    with pytest.raises(DecoderSetupError):
        parse_tool_version(payload(version=version), program="ffmpeg")


def test_rejects_duplicate_missing_unknown_and_control_library_lines():
    base = payload().decode().splitlines()
    cases = [base[:3] + base[3:-1] + [base[3], base[-1]],
             base[:3] + base[3:-2] + base[-1:],
             base[:3] + [base[3].replace("libavutil", "libunknown")] + base[4:],
             base[:3] + [base[3] + "\x01"] + base[4:]]
    for lines in cases:
        with pytest.raises(DecoderSetupError):
            parse_tool_version(("\n".join(lines) + "\n").encode(), program="ffmpeg")


def test_pair_comparison_rejects_different_fingerprint():
    first = parse_tool_version(payload(), program="ffmpeg")
    second = parse_tool_version(payload().replace(b"--enable-gpl", b"--enable-version3"), program="ffmpeg")
    with pytest.raises(DecoderSetupError):
        compare_tool_pair(first, second)


def test_direct_fingerprints_are_validated_and_subclasses_are_rejected():
    valid = parse_tool_version(payload(), program="ffmpeg")
    invalid_fields = (
        ("bad version", valid.compiler, valid.configuration, valid.libraries),
        (valid.version, "gcc 16.1.0", valid.configuration, valid.libraries),
        (valid.version, valid.compiler, "--enable-gpl", valid.libraries),
        (valid.version, valid.compiler, valid.configuration, list(valid.libraries)),
        (valid.version, valid.compiler, valid.configuration,
         (("wrong", *valid.libraries[0][1:]), *valid.libraries[1:])),
        (valid.version, valid.compiler, valid.configuration,
         ((valid.libraries[0][0], (True, 1, 101), valid.libraries[0][2]),
          *valid.libraries[1:])),
    )
    for fields in invalid_fields:
        with pytest.raises(DecoderSetupError):
            ToolBuildFingerprint(*fields)

    class FingerprintSubclass(ToolBuildFingerprint):
        pass

    subclass = FingerprintSubclass(
        valid.version, valid.compiler, valid.configuration, valid.libraries
    )
    with pytest.raises(DecoderSetupError):
        compare_tool_pair(valid, subclass)

    # Frozen instances can still be deliberately altered through object.__setattr__;
    # comparison revalidates instead of trusting construction provenance.
    object.__setattr__(valid, "libraries", ())
    with pytest.raises(DecoderSetupError):
        compare_tool_pair(valid, valid)
