import json
from fractions import Fraction

import pytest

from utterleaf.file_metadata import parse_media_metadata


def stream(index, codec_type="audio", **extra):
    value = {
        "index": index,
        "codec_type": codec_type,
        "codec_name": "pcm_s16le",
        "sample_rate": "48000",
        "channels": 2,
        "channel_layout": "stereo",
        "time_base": "1/48000",
        "start_pts": 0,
        "tags": {"title": "Guest", "language": "en"},
        "disposition": {"default": 1},
    }
    value.update(extra)
    return value


def payload(streams, start_time="0"):
    return json.dumps({"streams": streams, "format": {"start_time": start_time}}).encode()


def test_parses_tracks_and_container_origin_exactly():
    result = parse_media_metadata(payload([
        stream(4, start_pts="-4800", tags={"title": "A", "language": "en"}),
        stream(9, start_pts=9600, tags={}),
    ], start_time="-0.1"))
    assert result.origin == Fraction(-1, 10)
    assert result.origin_kind == "container"
    assert [track.ordinal for track in result.tracks] == [0, 1]
    assert [track.stream_index for track in result.tracks] == [4, 9]
    assert result.tracks[0].start == Fraction(-1, 10)
    assert result.tracks[1].start == Fraction(1, 5)
    assert result.tracks[0].title == "A"


def test_fallback_uses_all_av_starts_and_allows_missing_audio_start_only_with_container():
    result = parse_media_metadata(payload([
        stream(0, "video", codec_name="h264", time_base="1/90000", start_pts=9000),
        stream(1, start_pts=4800),
    ], start_time="N/A"))
    assert result.origin == Fraction(1, 10)
    assert result.origin_kind == "all-stream-starts"
    missing_audio = stream(1)
    missing_audio.pop("start_pts")
    with pytest.raises(ValueError, match="incomplete|missing or invalid A/V"):
        parse_media_metadata(payload([stream(0, "video", time_base="1/90000", start_pts=0), missing_audio], "N/A"))
    assert parse_media_metadata(payload([missing_audio], "0")).tracks[0].start is None


@pytest.mark.parametrize("bad", [
    {"streams": [], "format": {"start_time": "0"}},
    {"streams": [{**stream(0), "index": True}], "format": {"start_time": "0"}},
    {"streams": [stream(0), stream(0)], "format": {"start_time": "0"}},
    {"streams": [stream(0, time_base="1/100")], "format": {"start_time": "0"}},
    {"streams": [stream(0, sample_rate="0")], "format": {"start_time": "0"}},
])
def test_rejects_malformed_shape_indexes_precision_and_format(bad):
    with pytest.raises(ValueError):
        parse_media_metadata(json.dumps(bad).encode())


def test_rejects_invalid_origin_and_unbounded_or_control_text():
    with pytest.raises(ValueError, match="start_time"):
        parse_media_metadata(payload([stream(0)], "not-a-number"))
    sanitized = parse_media_metadata(payload([stream(0, tags={"title": "bad\ntext"})]))
    assert sanitized.tracks[0].title == "bad text"
    with pytest.raises(ValueError, match="1 MiB"):
        parse_media_metadata(b"{" + b" " * (1024 * 1024) + b"}")


def test_non_av_streams_do_not_affect_audio_tracks_but_are_bounded():
    result = parse_media_metadata(payload([
        stream(0, "data", codec_name="bin_data"),
        stream(1),
    ]))
    assert len(result.tracks) == 1 and result.tracks[0].stream_index == 1
    too_many = [stream(index) for index in range(257)]
    with pytest.raises(ValueError, match="too many"):
        parse_media_metadata(payload(too_many))


def test_rejects_adversarial_number_forms_duplicate_keys_and_unhashable_type():
    with pytest.raises(ValueError):
        parse_media_metadata(payload([stream(0)], "1e999999999"))
    with pytest.raises(ValueError):
        parse_media_metadata(payload([stream(0, time_base="1/" + "9" * 20)]))
    with pytest.raises(ValueError):
        parse_media_metadata(b'{"streams":[' + json.dumps(stream(0)).encode() + b'],"streams":[]}')
    with pytest.raises(ValueError):
        parse_media_metadata(json.dumps({"streams": [{**stream(0), "codec_type": []}], "format": {"start_time": "0"}}).encode())
    for value in (b'{"streams":[],"format":{"start_time":NaN}}',
                  b'{"streams":[],"format":{"start_time":Infinity}}'):
        with pytest.raises(ValueError):
            parse_media_metadata(value)


def test_rejects_deep_or_invalid_utf8_and_sanitizes_display_text():
    deep = b"[" * 20_000 + b"]" * 20_000
    with pytest.raises(ValueError):
        parse_media_metadata(deep)
    with pytest.raises(ValueError):
        parse_media_metadata(b"\xff")
    result = parse_media_metadata(payload([stream(
        0, tags={"title": " guest\n\u202e name ", "language": "en\u200b"}
    )]))
    assert result.tracks[0].title == "guest name"
    assert result.tracks[0].language == "en"


def test_rejects_unicode_controls_and_blank_strict_fields():
    with pytest.raises(ValueError, match="control"):
        parse_media_metadata(payload([stream(0, codec_name="\u0081")]))
    with pytest.raises(ValueError, match="control"):
        parse_media_metadata(payload([stream(0, channel_layout=" ")]))
    sanitized = parse_media_metadata(payload([stream(
        0, tags={"title": "\u0081private", "language": "\ud800"}
    )]))
    assert sanitized.tracks[0].title == "private"
    assert sanitized.tracks[0].language is None


@pytest.mark.parametrize("field", ["tags", "disposition"])
def test_rejects_explicit_null_object_fields(field):
    with pytest.raises(ValueError, match="invalid"):
        parse_media_metadata(payload([{**stream(0), field: None}]))


def test_rejects_explicit_null_format_object():
    with pytest.raises(ValueError, match="format metadata"):
        parse_media_metadata(json.dumps({"streams": [stream(0)], "format": None}).encode())


def test_inventory_can_omit_origin_without_inventing_zero_or_weakening_strict_default():
    missing = stream(0)
    missing.pop("start_pts")
    data = payload([missing], "N/A")
    with pytest.raises(ValueError, match="missing or invalid A/V"):
        parse_media_metadata(data)
    result = parse_media_metadata(data, require_origin=False)
    assert result.origin is None
    assert result.origin_kind == "unavailable"
    assert result.tracks[0].start is None
    assert result.tracks[0].sample_rate == 48000
    # A known start in a different track is not a common-origin fallback.
    partial = parse_media_metadata(payload([missing, stream(1, start_pts=4800)], "N/A"), require_origin=False)
    assert partial.origin is None and partial.tracks[1].start == Fraction(1, 10)


@pytest.mark.parametrize("data", [
    payload([stream(0)], "bad"),
    payload([stream(0, start_pts="bad")], "N/A"),
    payload([stream(0, time_base="0/1")], "N/A"),
    payload([stream(0, start_pts=None), stream(1, "video", start_pts="bad")], "N/A"),
])
def test_inventory_still_rejects_present_malformed_timing(data):
    with pytest.raises(ValueError):
        parse_media_metadata(data, require_origin=False)
