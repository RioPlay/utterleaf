"""Explicit OBS protocol-v2 selection at the authenticated pipe boundary."""

from __future__ import annotations

import hashlib
import hmac
import struct
import time

import numpy as np
import pytest

from utterleaf import obs_audio_pipe
from utterleaf import obs_protocol
from utterleaf.obs_mix import BusLabel, MixSnapshot, SourceAssignment


SESSION = bytes(range(16))
ACK_DOMAIN = b"Utterleaf OBS audio server ack v1\0"


class ProcessLease:
    pid = 314

    def __init__(self) -> None:
        self.closed = False
        self.verified: list[int] = []

    def verify_pid(self, pid, *, cancelled, deadline) -> None:
        assert not cancelled()
        assert deadline > time.monotonic()
        assert pid == self.pid
        self.verified.append(pid)

    def close(self) -> None:
        self.closed = True


class AuthenticatedPipe:
    def __init__(self) -> None:
        self.pending = bytearray()
        self.writes: list[bytes] = []
        self.closed = False
        self.max_chunk = 23

    def server_pid(self) -> int:
        return ProcessLease.pid

    def write_all(self, data, *, deadline) -> None:
        assert deadline > time.monotonic()
        self.writes.append(data)
        if len(data) == 56:
            assert data[:8] == b"ULAH\x01\x01\x00\x00"
            mac = hmac.new(data[24:], ACK_DOMAIN + data[:24], hashlib.sha256).digest()
            self.pending.extend(b"ULAH\x01\x02\x00\x00" + data[8:24] + mac)
            return
        magic, version, kind, reserved, session, mask, status, trailing = struct.unpack(
            "<4sBBH16sBBH", data
        )
        assert (magic, version, reserved, session, trailing) == (
            b"ULAC", 1, 0, SESSION, 0
        )
        if kind == 1:
            assert 0 <= mask <= 63 and status == 0
            self.pending.extend(
                struct.pack("<4sBBH16sBBH", b"ULAC", 1, 2, 0, session, mask, 1, 0)
            )
        else:
            assert (kind, mask, status) == (3, 0, 0)

    def read(self, maximum, *, deadline) -> bytes:
        assert deadline > time.monotonic()
        count = min(maximum, self.max_chunk, len(self.pending))
        result = bytes(self.pending[:count])
        del self.pending[:count]
        return result

    def available_bytes(self, *, deadline) -> int:
        assert deadline > time.monotonic()
        return len(self.pending)

    def wait_for_disconnect(self, *, deadline) -> None:
        assert deadline > time.monotonic()
        assert not self.pending
        assert self.writes[-1] == b"ULAC\x01\x03\x00\x00" + SESSION + b"\x00" * 4
        self.closed = True

    def close(self) -> None:
        self.closed = True


def connect_v2(monkeypatch):
    pipe, lease = AuthenticatedPipe(), ProcessLease()

    def open_pipe(name, **controls):
        assert name == "\\\\.\\pipe\\Utterleaf.OBS." + SESSION.hex()
        assert controls["cancelled"]() is False
        return pipe

    monkeypatch.setattr(obs_audio_pipe.windows_pipe, "connect", open_pipe)
    connection = obs_audio_pipe.connect(
        SESSION,
        lease,
        cancelled=lambda: False,
        deadline=time.monotonic() + 2,
        protocol_version=obs_protocol.PROVENANCE_VERSION,
    )
    connection.arm(deadline=time.monotonic() + 2)
    return connection, pipe, lease


def routing_stream() -> tuple[obs_protocol.Frame, ...]:
    snapshot = MixSnapshot(
        0,
        3,
        (SourceAssignment(b"s" * 16, "Desktop", 3),),
        (BusLabel(0, "Program"), BusLabel(1, "Guest")),
    )
    pcm = np.array(((0.25, -0.25), (0.5, -0.5)), dtype="<f4").tobytes()
    return (
        obs_protocol.StartFrame(SESSION, 16_000, 0, 3, 9_000_000_000),
        obs_protocol.RoutingFrame(
            SESSION, 1, 9_000_000_001, ((0, 0), (1, 0)), snapshot
        ),
        obs_protocol.AudioFrame(SESSION, 0, 0, 9_000_000_002, 2, pcm),
        obs_protocol.EndFrame(
            SESSION, obs_protocol.EndReason.STREAM_STOPPED, ((0, 0), (1, None))
        ),
    )


def test_connect_explicit_v2_decodes_real_fragmented_routing_stream(monkeypatch):
    connection, pipe, lease = connect_v2(monkeypatch)
    expected = routing_stream()
    pipe.pending.extend(
        b"".join(
            obs_protocol.encode_frame(frame, version=obs_protocol.PROVENANCE_VERSION)
            for frame in expected
        )
    )

    received = []
    while not pipe.closed:
        received.extend(connection.read_frames(deadline=time.monotonic() + 2))

    assert tuple(received) == expected
    assert type(received[1]) is obs_protocol.RoutingFrame
    assert received[1].snapshot == expected[1].snapshot
    assert pipe.writes[0][:8] == b"ULAH\x01\x01\x00\x00"
    assert pipe.closed and lease.closed


def test_explicit_v2_rejects_a_version1_stream_and_closes_both_leases(monkeypatch):
    connection, pipe, lease = connect_v2(monkeypatch)
    pipe.pending.extend(obs_protocol.encode_frame(routing_stream()[0]))

    with pytest.raises(obs_audio_pipe.ObsAudioPipeError, match="verified or continued"):
        connection.read_frames(deadline=time.monotonic() + 2)

    assert pipe.closed and lease.closed


@pytest.mark.parametrize("version", [True, False, 0, 3, "2", 2.0, None])
def test_invalid_version_releases_lease_before_pipe_or_secret_dispatch(
    monkeypatch, version
):
    lease = ProcessLease()
    opened = []
    generated = []
    monkeypatch.setattr(
        obs_audio_pipe.windows_pipe,
        "connect",
        lambda *args, **kwargs: opened.append(True) or AuthenticatedPipe(),
    )
    monkeypatch.setattr(
        obs_audio_pipe.secrets,
        "token_bytes",
        lambda count: generated.append(count) or b"s" * count,
    )

    with pytest.raises(
        obs_audio_pipe.ObsAudioPipeError,
        match="could not be verified or continued",
    ):
        obs_audio_pipe.connect(
            SESSION,
            lease,
            cancelled=lambda: False,
            deadline=time.monotonic() + 2,
            protocol_version=version,
        )

    assert lease.closed
    assert lease.verified == []
    assert opened == []
    assert generated == []
