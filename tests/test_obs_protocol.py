"""Independent wire and invariant tests for the bounded OBS PCM protocol."""

from dataclasses import FrozenInstanceError
import struct

import numpy as np
import pytest

from utterleaf import obs_protocol as protocol


HEADER = struct.Struct("<4sBBHI")
START = struct.Struct("<16sIBBQ")
AUDIO = struct.Struct("<16sBQQI")
GAP = struct.Struct("<16sBQQQ")
END_PREFIX = struct.Struct("<16sBB")
END_SEQUENCE = struct.Struct("<BQ")
SESSION = b"0123456789abcdef"
OTHER_SESSION = b"fedcba9876543210"


def pcm(values=(0.25, -0.25)):
    return np.asarray(values, dtype="<f4").tobytes()


def packet(kind, body, *, magic=b"ULAP", version=1, reserved=0, length=None):
    return HEADER.pack(magic, version, kind, reserved, len(body) if length is None else length) + body


def frames():
    return (
        protocol.StartFrame(SESSION, 48000, 1, 0b000110, 123),
        protocol.AudioFrame(SESSION, 1, 7, 456, 1, pcm()),
        protocol.GapFrame(SESSION, 1, 8, 2, 789),
        protocol.EndFrame(SESSION, protocol.EndReason.STREAM_STOPPED, ((1, 9), (2, None))),
    )


def test_wire_layout_is_exact_and_little_endian():
    start, audio, gap, end = frames()
    start_body = START.pack(SESSION, 48000, 1, 0b000110, 123)
    audio_body = AUDIO.pack(SESSION, 1, 7, 456, 1) + pcm()
    gap_body = GAP.pack(SESSION, 1, 8, 2, 789)
    end_body = END_PREFIX.pack(SESSION, 1, 2) + END_SEQUENCE.pack(1, 9) + END_SEQUENCE.pack(
        2, protocol.UINT64_MAX
    )

    assert protocol.encode_frame(start) == packet(1, start_body)
    assert protocol.encode_frame(audio) == packet(2, audio_body)
    assert protocol.encode_frame(gap) == packet(3, gap_body)
    assert protocol.encode_frame(end) == packet(4, end_body)
    assert [len(body) for body in (start_body, audio_body, gap_body, end_body)] == [30, 45, 41, 36]


def test_decoder_accepts_independently_constructed_wire():
    raw = b"".join(
        (
            packet(1, START.pack(SESSION, 44100, 0, 0b100001, 0)),
            packet(2, AUDIO.pack(SESSION, 5, protocol.MAX_SEQUENCE, protocol.UINT64_MAX, 1) + pcm()),
            packet(3, GAP.pack(SESSION, 5, protocol.MAX_SEQUENCE, 1, 0)),
            packet(
                4,
                END_PREFIX.pack(SESSION, 5, 2)
                + END_SEQUENCE.pack(0, protocol.UINT64_MAX)
                + END_SEQUENCE.pack(5, protocol.MAX_SEQUENCE),
            ),
        )
    )
    decoder = protocol.FrameDecoder()

    decoded = decoder.feed(raw)
    decoder.finish()

    assert decoded == [
        protocol.StartFrame(SESSION, 44100, 0, 0b100001, 0),
        protocol.AudioFrame(SESSION, 5, protocol.MAX_SEQUENCE, protocol.UINT64_MAX, 1, pcm()),
        protocol.GapFrame(SESSION, 5, protocol.MAX_SEQUENCE, 1, 0),
        protocol.EndFrame(
            SESSION,
            protocol.EndReason.TRANSPORT_ERROR,
            ((0, None), (5, protocol.MAX_SEQUENCE)),
        ),
    ]


def test_fragmentation_and_coalescing_preserve_frame_order():
    expected = list(frames())
    raw = b"".join(map(protocol.encode_frame, expected))
    decoder = protocol.FrameDecoder()
    actual = []
    for byte in raw:
        actual.extend(decoder.feed(bytes((byte,))))
    decoder.finish()
    assert actual == expected

    decoder = protocol.FrameDecoder()
    assert decoder.feed(raw) == expected
    decoder.finish()


def test_maximum_audio_packet_can_be_fragmented_at_feed_bound():
    source = protocol.AudioFrame(
        SESSION, 0, 0, 0, protocol.MAX_FRAMES, pcm((0.125, -0.125) * protocol.MAX_FRAMES)
    )
    raw = protocol.encode_frame(source)
    assert len(raw) == protocol.MAX_PACKET_BYTES
    decoder = protocol.FrameDecoder()
    assert decoder.feed(raw[: protocol.MAX_FEED_BYTES]) == []
    assert len(decoder._buffer) == protocol.MAX_FEED_BYTES
    assert decoder.feed(raw[protocol.MAX_FEED_BYTES :]) == [source]
    decoder.finish()


def test_finish_does_not_require_end_frame():
    decoder = protocol.FrameDecoder()
    assert decoder.feed(protocol.encode_frame(frames()[0])) == [frames()[0]]
    decoder.finish()
    with pytest.raises(protocol.ProtocolError):
        decoder.feed(b"")
    with pytest.raises(protocol.ProtocolError):
        decoder.finish()


@pytest.mark.parametrize(
    "raw",
    [
        packet(1, b"", magic=b"NOPE", length=30),
        packet(1, b"", version=2, length=30),
        packet(1, b"", reserved=1, length=30),
        packet(9, b"", length=0),
        packet(1, b"", length=protocol.MAX_BODY_BYTES + 1),
        packet(1, b"", length=29),
        packet(2, b"", length=AUDIO.size),
        packet(2, b"", length=AUDIO.size + 9),
        packet(3, b"", length=40),
        packet(4, b"", length=END_PREFIX.size),
    ],
)
def test_bad_header_or_kind_length_fails_before_payload_arrives(raw):
    decoder = protocol.FrameDecoder()
    with pytest.raises(protocol.ProtocolError):
        decoder.feed(raw[: protocol.HEADER_BYTES])
    assert decoder._buffer == bytearray()
    with pytest.raises(protocol.ProtocolError):
        decoder.feed(protocol.encode_frame(frames()[0]))


@pytest.mark.parametrize("value", [b"x", b"x" * 17, bytearray(b"x" * 16), memoryview(b"x" * 16)])
def test_session_id_is_exact_16_byte_value(value):
    with pytest.raises(protocol.ProtocolError):
        protocol.StartFrame(value, 48000, 0, 1, 0)


@pytest.mark.parametrize("sample_rate", [True, 0, 8000, 22050, 192000, 48000.0])
def test_start_rejects_unsupported_or_inexact_sample_rate(sample_rate):
    with pytest.raises(protocol.ProtocolError):
        protocol.StartFrame(SESSION, sample_rate, 0, 1, 0)


@pytest.mark.parametrize(
    "primary_bus,bus_mask,origin",
    [(True, 1, 0), (6, 1, 0), (1, 1, 0), (0, 0, 0), (0, 0x40, 0), (0, 1, True), (0, 1, -1)],
)
def test_start_rejects_invalid_bus_mask_or_origin(primary_bus, bus_mask, origin):
    with pytest.raises(protocol.ProtocolError):
        protocol.StartFrame(SESSION, 48000, primary_bus, bus_mask, origin)


@pytest.mark.parametrize(
    "bus,sequence,timestamp,frame_count,payload",
    [
        (True, 0, 0, 1, pcm()),
        (6, 0, 0, 1, pcm()),
        (0, True, 0, 1, pcm()),
        (0, protocol.UINT64_MAX, 0, 1, pcm()),
        (0, 0, True, 1, pcm()),
        (0, 0, 0, True, pcm()),
        (0, 0, 0, 0, b""),
        (0, 0, 0, protocol.MAX_FRAMES + 1, b""),
        (0, 0, 0, 2, pcm()),
        (0, 0, 0, 1, bytearray(pcm())),
    ],
)
def test_audio_constructor_enforces_exact_ranges_and_pcm_size(
    bus, sequence, timestamp, frame_count, payload
):
    with pytest.raises(protocol.ProtocolError):
        protocol.AudioFrame(SESSION, bus, sequence, timestamp, frame_count, payload)


@pytest.mark.parametrize("value", [np.nan, np.inf, -np.inf])
def test_nonfinite_pcm_is_rejected_by_constructor_and_decoder(value):
    payload = pcm((value, 0.0))
    with pytest.raises(protocol.ProtocolError):
        protocol.AudioFrame(SESSION, 0, 0, 0, 1, payload)

    decoder = protocol.FrameDecoder()
    raw = packet(2, AUDIO.pack(SESSION, 0, 0, 0, 1) + payload)
    with pytest.raises(protocol.ProtocolError):
        decoder.feed(raw)
    with pytest.raises(protocol.ProtocolError):
        decoder.feed(b"")


def test_finite_pcm_is_not_amplitude_clamped():
    source = protocol.AudioFrame(SESSION, 0, 0, 0, 1, pcm((1000.0, -1000.0)))
    assert protocol.FrameDecoder().feed(protocol.encode_frame(source)) == [source]


@pytest.mark.parametrize(
    "first,count,timestamp",
    [
        (True, 1, 0),
        (0, True, 0),
        (0, 0, 0),
        (protocol.MAX_SEQUENCE, 2, 0),
        (protocol.UINT64_MAX, 1, 0),
        (0, 1, True),
    ],
)
def test_gap_rejects_sentinel_overflow_and_inexact_integers(first, count, timestamp):
    with pytest.raises(protocol.ProtocolError):
        protocol.GapFrame(SESSION, 0, first, count, timestamp)


@pytest.mark.parametrize(
    "reason,last_sequences",
    [
        (1, ((0, None),)),
        (protocol.EndReason.DISARMED, ()),
        (protocol.EndReason.DISARMED, tuple((bus, None) for bus in range(6)) + ((0, None),)),
        (protocol.EndReason.DISARMED, ((1, None), (0, None))),
        (protocol.EndReason.DISARMED, ((0, None), (0, 1))),
        (protocol.EndReason.DISARMED, ([0, None],)),
        (protocol.EndReason.DISARMED, ((True, None),)),
        (protocol.EndReason.DISARMED, ((0, True),)),
        (protocol.EndReason.DISARMED, ((0, protocol.UINT64_MAX),)),
    ],
)
def test_end_requires_enum_and_sorted_unique_exact_tuple(reason, last_sequences):
    with pytest.raises(protocol.ProtocolError):
        protocol.EndFrame(SESSION, reason, last_sequences)


@pytest.mark.parametrize(
    "kind,body",
    [
        (1, START.pack(SESSION, 22050, 0, 1, 0)),
        (1, START.pack(SESSION, 48000, 1, 1, 0)),
        (2, AUDIO.pack(SESSION, 6, 0, 0, 1) + pcm()),
        (2, AUDIO.pack(SESSION, 0, protocol.UINT64_MAX, 0, 1) + pcm()),
        (2, AUDIO.pack(SESSION, 0, 0, 0, 2) + pcm()),
        (3, GAP.pack(SESSION, 0, 0, 0, 0)),
        (3, GAP.pack(SESSION, 0, protocol.MAX_SEQUENCE, 2, 0)),
        (4, END_PREFIX.pack(SESSION, 9, 1) + END_SEQUENCE.pack(0, 0)),
        (4, END_PREFIX.pack(SESSION, 1, 2) + END_SEQUENCE.pack(0, 0)),
        (4, END_PREFIX.pack(SESSION, 1, 2) + END_SEQUENCE.pack(1, 0) + END_SEQUENCE.pack(0, 0)),
    ],
)
def test_decoder_strictly_rejects_malformed_frame_fields(kind, body):
    decoder = protocol.FrameDecoder()
    with pytest.raises(protocol.ProtocolError):
        decoder.feed(packet(kind, body))
    assert decoder._buffer == bytearray()


def test_truncation_is_terminal_and_clears_buffer():
    decoder = protocol.FrameDecoder()
    raw = protocol.encode_frame(frames()[1])
    assert decoder.feed(raw[:-1]) == []
    with pytest.raises(protocol.ProtocolError, match="Truncated"):
        decoder.finish()
    assert decoder._buffer == bytearray()
    with pytest.raises(protocol.ProtocolError):
        decoder.feed(raw)


def test_feed_requires_bounded_exact_bytes_and_failure_is_terminal():
    for data in (bytearray(), memoryview(b""), b"x" * (protocol.MAX_FEED_BYTES + 1)):
        decoder = protocol.FrameDecoder()
        with pytest.raises(protocol.ProtocolError):
            decoder.feed(data)
        assert decoder._buffer == bytearray()
        with pytest.raises(protocol.ProtocolError):
            decoder.feed(b"")


def test_sensitive_binary_fields_are_hidden_and_frames_are_frozen():
    secret_session = b"secret-session!!"
    secret_pcm = b"PRIVATE!"
    audio = protocol.AudioFrame(secret_session, 0, 0, 0, 1, secret_pcm)
    start = protocol.StartFrame(secret_session, 48000, 0, 1, 0)
    gap = protocol.GapFrame(secret_session, 0, 0, 1, 0)
    end = protocol.EndFrame(secret_session, protocol.EndReason.OBS_EXIT, ((0, None),))
    for frame in (audio, start, gap, end):
        representation = repr(frame)
        assert "secret-session" not in representation
        assert "PRIVATE" not in representation
        with pytest.raises(FrozenInstanceError):
            frame.session_id = OTHER_SESSION


def test_encode_rejects_unrecognized_objects_without_repr_leak():
    class Secret:
        def __repr__(self):
            raise AssertionError("secret repr inspected")

    with pytest.raises(protocol.ProtocolError, match="Invalid protocol frame"):
        protocol.encode_frame(Secret())
