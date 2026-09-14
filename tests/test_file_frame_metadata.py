from __future__ import annotations

import pytest

from utterleaf.file_frame_metadata import DecodedAudioFrame, parse_compact_audio_frame


def row(**changes):
    values = {
        "stream_index": "2", "pts": "-9223372036854775808", "sample_fmt": "fltp",
        "nb_samples": "1024", "channels": "2", "channel_layout": "stereo",
    }
    values.update(changes)
    return "|".join(f"{key}={value}" for key, value in values.items()).encode()


def test_parses_order_independent_row_and_negative_pts():
    payload = b"channel_layout=5.1(side)|pts=-2|stream_index=2|channels=6|sample_fmt=s16|nb_samples=4\r\n"
    parsed = parse_compact_audio_frame(payload, sample_rate=16000, expected_stream_index=2)
    assert parsed == DecodedAudioFrame(2, -2, "s16", 4, 6, "5.1(side)")


@pytest.mark.parametrize(("payload", "rate", "stream", "fmt", "pts", "count"), [
    (b"stream_index=1|pts=1000|sample_fmt=s16|nb_samples=1600|channels=1|channel_layout=unknown\n",
     16000, 1, "s16", 1000, 1600),
    (b"stream_index=1|pts=0|sample_fmt=fltp|nb_samples=1024|channels=2|channel_layout=stereo\n",
     44100, 1, "fltp", 0, 1024),
])
def test_accepts_compact_pcm_and_m4a_style_rows(payload, rate, stream, fmt, pts, count):
    parsed = parse_compact_audio_frame(payload, sample_rate=rate, expected_stream_index=stream)
    assert (parsed.sample_fmt, parsed.pts, parsed.nb_samples) == (fmt, pts, count)


@pytest.mark.parametrize("kwargs", [
    {"sample_rate": True}, {"sample_rate": 0}, {"sample_rate": 384001},
    {"sample_rate": float("nan")}, {"expected_stream_index": True},
    {"expected_stream_index": -1}, {"expected_stream_index": 2**63},
])
def test_rejects_invalid_keyword_inputs(kwargs):
    arguments = {"sample_rate": 16000, "expected_stream_index": 2, **kwargs}
    with pytest.raises(ValueError):
        parse_compact_audio_frame(row(), **arguments)


@pytest.mark.parametrize("field,value", [
    ("stream_index", "-1"), ("stream_index", "01"), ("stream_index", "1.0"),
    ("pts", "N/A"), ("pts", "+1"), ("pts", "1e3"),
    ("nb_samples", "0"), ("nb_samples", "960001"), ("channels", "0"),
    ("channels", "33"), ("sample_fmt", "pcm_s16le"),
    ("channel_layout", ""), ("channel_layout", "stereo|x"),
    ("channel_layout", "stereo\\x"), ("channel_layout", "stereo=x"),
])
def test_rejects_invalid_row_values(field, value):
    with pytest.raises(ValueError):
            parse_compact_audio_frame(row(**{field: value}), sample_rate=16000, expected_stream_index=2)


def test_expected_stream_index_is_required():
    with pytest.raises(TypeError):
        parse_compact_audio_frame(row(), sample_rate=16000)


def test_missing_original_pts_is_actionable_without_echoing_row():
    with pytest.raises(ValueError, match="Original audio frame timing is unavailable"):
        parse_compact_audio_frame(row(pts="N/A"), sample_rate=16000, expected_stream_index=2)


def test_unknown_layout_is_valid_but_blank_layout_is_not():
    assert parse_compact_audio_frame(row(channel_layout="unknown"), sample_rate=16000,
                                     expected_stream_index=2).channel_layout == "unknown"
    with pytest.raises(ValueError):
        parse_compact_audio_frame(row(channel_layout="   "), sample_rate=16000,
                                   expected_stream_index=2)


@pytest.mark.parametrize("payload", [
    row() + b"\nextra", row() + b"\n\n", b"", b" ",
    row(stream_index="3"),
])
def test_rejects_shape_and_stream_errors(payload):
    with pytest.raises(ValueError):
        parse_compact_audio_frame(payload, sample_rate=16000, expected_stream_index=2)


def test_rejects_duplicate_unknown_missing_and_escaped_fields():
    assert b"stream_index=2|" in row()
    cases = [
        row() + b"|stream_index=2",
        row(foo="bar"),
        b"|".join(row().split(b"|")[:-1]),
        row(channel_layout="stereo\nprivate"),
    ]
    for payload in cases:
        with pytest.raises(ValueError):
            parse_compact_audio_frame(payload, sample_rate=16000, expected_stream_index=2)


def test_rejects_invalid_utf8_and_oversized_payload():
    with pytest.raises(ValueError):
        parse_compact_audio_frame(row() + b"\xff", sample_rate=16000, expected_stream_index=2)
    with pytest.raises(ValueError):
        parse_compact_audio_frame(row() + b" " * 500, sample_rate=16000, expected_stream_index=2)


def test_sample_count_bound_scales_with_required_rate():
    parsed = parse_compact_audio_frame(row(nb_samples="60"), sample_rate=1, expected_stream_index=2)
    assert parsed.nb_samples == 60
