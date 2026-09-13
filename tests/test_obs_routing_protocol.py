"""Independent v2 routing bytes, bounds and strict version isolation."""

from dataclasses import replace
import struct
import traceback

import pytest

from utterleaf import obs_protocol as protocol
from utterleaf.obs_mix import BusLabel, MixSnapshot, SourceAssignment


SESSION = b"0123456789abcdef"
SOURCE_A = bytes(range(16))
SOURCE_B = bytes(range(16, 32))


def packet(body, *, version=2, kind=5, length=None):
    return struct.pack("<4sBBHI", b"ULAP", version, kind, 0,
                       len(body) if length is None else length) + body


def independent_body(*, revision=1, observed=123456789, primary=1, mask=6,
                     labels=((1, 7, b"Stream"), (2, 9, b"Guest")),
                     sources=((SOURCE_A, 6, b"Desktop"), (SOURCE_B, 2, b"Mic")),
                     declared_sources=None):
    return (
        struct.pack("<16sQQBBH", SESSION, revision, observed, primary, mask,
                    len(sources) if declared_sources is None else declared_sources)
        + b"".join(struct.pack("<BQH", bus, seq, len(label)) + label
                   for bus, seq, label in labels)
        + b"".join(struct.pack("<16sBH", identity, buses, len(name)) + name
                   for identity, buses, name in sources)
    )


def routing():
    return protocol.RoutingFrame(
        SESSION, 1, 123456789, ((1, 7), (2, 9)),
        MixSnapshot(1, 6, (SourceAssignment(SOURCE_A, "Desktop", 6),
                           SourceAssignment(SOURCE_B, "Mic", 2)),
                    (BusLabel(1, "Stream"), BusLabel(2, "Guest"))),
    )


def test_native_contract_exact_independent_bytes_and_fragmentation():
    raw = packet(independent_body())
    assert len(raw) == 129  # 12-byte header plus the independent 117-byte body.
    assert protocol.encode_frame(routing(), version=2) == raw
    decoder = protocol.FrameDecoder(version=2)
    frames = []
    for byte in raw:
        frames.extend(decoder.feed(bytes((byte,))))
    decoder.finish()
    assert frames == [routing()]


def test_explicit_version2_can_frame_a_whole_stream_without_default_version_drift():
    frames = (
        protocol.StartFrame(SESSION, 48000, 1, 6, 0),
        routing(),
        protocol.AudioFrame(SESSION, 1, 7, 123456789, 1, struct.pack("<ff", 0.5, -0.5)),
        protocol.EndFrame(SESSION, protocol.EndReason.STREAM_STOPPED, ((1, 7), (2, 8))),
    )
    decoder = protocol.FrameDecoder(version=2)
    assert decoder.feed(b"".join(protocol.encode_frame(frame, version=2) for frame in frames)) == list(frames)
    decoder.finish()
    assert protocol.encode_frame(frames[0])[4] == 1


@pytest.mark.parametrize("decoder_version,wire_version,kind", [(1, 2, 5), (1, 1, 5), (2, 1, 5)])
def test_wrong_version_or_legacy_routing_rejected_from_header(decoder_version, wire_version, kind):
    decoder = protocol.FrameDecoder(version=decoder_version)
    with pytest.raises(protocol.ProtocolError):
        decoder.feed(packet(b"", version=wire_version, kind=kind, length=100))
    assert not decoder.has_partial_frame
    with pytest.raises(protocol.ProtocolError):
        decoder.feed(packet(independent_body()))


@pytest.mark.parametrize("version", [True, False, 0, 3, "2", 2.0, None])
def test_version_selection_requires_exact_supported_integer(version):
    with pytest.raises(protocol.ProtocolError):
        protocol.FrameDecoder(version=version)
    with pytest.raises(protocol.ProtocolError):
        protocol.encode_frame(routing(), version=version)


def test_routing_cannot_be_accidentally_encoded_for_active_v1_transport():
    with pytest.raises(protocol.ProtocolError):
        protocol.encode_frame(routing())


@pytest.mark.parametrize("changes", [
    {"session_id": b"short"}, {"revision": 0}, {"revision": True},
    {"revision": protocol.UINT64_MAX}, {"observed_at_ns": -1},
    {"observed_at_ns": False}, {"snapshot": object()},
    {"positions": [(1, 7), (2, 9)]}, {"positions": ((1, 7),)},
    {"positions": ((2, 7), (1, 9))}, {"positions": ((1, 7), (1, 9))},
    {"positions": ((True, 7), (2, 9))}, {"positions": ((1, -1), (2, 9))},
    {"positions": ((1, 7), (2, protocol.UINT64_MAX + 1))},
])
def test_frame_rejects_invalid_identity_revision_or_publication_positions(changes):
    with pytest.raises(protocol.ProtocolError):
        replace(routing(), **changes)


@pytest.mark.parametrize("changes", [
    {"revision": 0}, {"revision": protocol.UINT64_MAX},
    {"primary": 6}, {"primary": 0}, {"mask": 0}, {"mask": 64},
    {"declared_sources": 129}, {"declared_sources": 1}, {"declared_sources": 3},
    {"labels": ((2, 0, b"Guest"), (1, 0, b"Main"))},
    {"labels": ((1, 0, b"Main"), (1, 0, b"Other"))},
    {"labels": ((1, 0, b""), (2, 0, b"Other"))},
    {"labels": ((1, 0, b"x" * 65), (2, 0, b"Other"))},
    {"sources": ((SOURCE_A, 1, b"Unselected"),)},
    {"sources": ((SOURCE_A, 0, b"None"),)},
    {"sources": ((SOURCE_A, 6, b""),)},
    {"sources": ((SOURCE_A, 6, b"x" * 129),)},
    {"sources": ((SOURCE_B, 2, b"Later"), (SOURCE_A, 6, b"Earlier"))},
    {"sources": ((SOURCE_A, 2, b"One"), (SOURCE_A, 4, b"Two"))},
])
def test_malformed_independent_metadata_is_terminal(changes):
    decoder = protocol.FrameDecoder(version=2)
    with pytest.raises(protocol.ProtocolError):
        decoder.feed(packet(independent_body(**changes)))
    assert not decoder.has_partial_frame
    with pytest.raises(protocol.ProtocolError):
        decoder.finish()


@pytest.mark.parametrize("text", [
    b"private\x00name", b"private\nname", b"private\x7fname", b"\xc0\xaf",
    b"\xed\xa0\x80", b"\xf4\x90\x80\x80", b"\xf0\x9f",
    "private\u0085name".encode(), "private\u2028name".encode(),
    "private\u202ename".encode(), "private\u2066name".encode(),
    "private\u061cname".encode(), "private\u200bname".encode(),
    "private\u200ename".encode(), "private\u200fname".encode(),
    "private\ufeffname".encode(), b"   ", "\u00a0\u2009".encode(),
    "\u200c\u200d".encode(),
])
@pytest.mark.parametrize("field", ["label", "source"])
def test_wire_utf8_controls_and_private_error_text(text, field):
    kwargs = {"labels": ((1, 0, text), (2, 0, b"Other"))} if field == "label" else {
        "sources": ((SOURCE_A, 6, text),),
    }
    decoder = protocol.FrameDecoder(version=2)
    with pytest.raises(protocol.ProtocolError) as caught:
        decoder.feed(packet(independent_body(**kwargs)))
    public_error = "".join(traceback.format_exception(caught.value))
    assert "private" not in str(caught.value)
    assert "UnicodeDecodeError" not in public_error
    assert caught.value.__cause__ is None
    assert not decoder.has_partial_frame


def test_maximum_bounded_snapshot_and_uint64_positions():
    body = independent_body(
        revision=protocol.MAX_SEQUENCE, observed=protocol.UINT64_MAX, primary=5, mask=63,
        labels=tuple((bus, protocol.UINT64_MAX, b"L" * 64) for bus in range(6)),
        sources=tuple((index.to_bytes(16, "big"), 63, b"N" * 128) for index in range(128)),
    )
    assert len(body) == 19302 == protocol.MAX_ROUTING_BODY_BYTES
    decoder = protocol.FrameDecoder(version=2)
    frames = decoder.feed(packet(body))
    decoder.finish()
    assert len(frames[0].snapshot.sources) == 128
    assert frames[0].positions == tuple((bus, protocol.UINT64_MAX) for bus in range(6))
    assert protocol.encode_frame(frames[0], version=2) == packet(body)


@pytest.mark.parametrize("length", [0, 47, 19303, 65573, 0xFFFFFFFF])
def test_oversized_or_too_small_body_fails_before_waiting_for_payload(length):
    decoder = protocol.FrameDecoder(version=2)
    with pytest.raises(protocol.ProtocolError):
        decoder.feed(packet(b"", length=length))
    assert not decoder.has_partial_frame


def test_truncated_nested_fields_trailing_bytes_and_no_resynchronization():
    body = independent_body()
    for invalid in (body[:-1], body[:48], body + b"\x00"):
        decoder = protocol.FrameDecoder(version=2)
        with pytest.raises(protocol.ProtocolError):
            decoder.feed(packet(invalid) + packet(body))
        assert not decoder.has_partial_frame


def test_unicode_and_zero_sources_preserve_labels_without_exposing_private_repr():
    raw = packet(independent_body(
        labels=((1, 0, "家庭 👩‍💻".encode()), (2, 0, "Гость".encode())), sources=(),
    ))
    frame, = protocol.FrameDecoder(version=2).feed(raw)
    assert frame.snapshot.labels[0].label == "家庭 👩‍💻"
    assert frame.snapshot.sources == ()
    assert "家庭" not in repr(frame)
    assert SESSION.decode() not in repr(frame)
    assert protocol.encode_frame(frame, version=2) == raw


def test_real_rtl_and_persian_joiner_text_is_preserved_exactly():
    name = "می\u200cتوانم"
    raw = packet(independent_body(
        labels=((1, 0, "  עברית  ".encode()), (2, 0, "العربية".encode())),
        sources=((SOURCE_A, 6, name.encode()),),
    ))
    frame, = protocol.FrameDecoder(version=2).feed(raw)
    assert frame.snapshot.labels[0].label == "  עברית  "
    assert frame.snapshot.labels[1].label == "العربية"
    assert frame.snapshot.sources[0].name == name
    assert protocol.encode_frame(frame, version=2) == raw
