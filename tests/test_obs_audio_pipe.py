"""Audio authentication/consent boundary; no OBS or consumer audio."""

import hashlib
import hmac
import secrets
import socket
import struct
import sys
import time

import numpy as np
import pytest

from utterleaf import obs_audio_pipe as audio_pipe
from utterleaf import obs_protocol as protocol
from utterleaf import windows_peer_identity as identity
from utterleaf.obs_session import ObsCaptureSession, ObsSessionError
from windows_pipe_server import start_native_pipe_server


SESSION = bytes(range(16))
DOMAIN = b"Utterleaf OBS audio server ack v1\0"


class Peer:
    pid = 123

    def __init__(self):
        self.checks = []
        self.closed = False
        self.fail_at = None

    def verify_pid(self, pid, *, cancelled, deadline):
        self.checks.append(pid)
        if cancelled():
            raise identity.PeerIdentityCancelled("fixture")
        if self.closed or pid != self.pid or len(self.checks) == self.fail_at:
            raise identity.PeerIdentityError("fixture peer details")

    def close(self):
        self.closed = True


class Pipe:
    def __init__(self):
        self.writes = []
        self.pending = bytearray()
        self.closed = False
        self.pid = 123
        self.max_chunk = 65536
        self.mutate_ack = lambda ack: ack
        self.after_write = lambda: None
        self.read_calls = []
        self.pid_calls = 0

    def server_pid(self):
        self.pid_calls += 1
        return self.pid

    def write_all(self, data, *, deadline):
        self.writes.append(data)
        # Independent server record construction, not the client's private helpers.
        assert len(data) == 56
        assert data[:8] == b"ULAH\x01\x01\x00\x00"
        mac = hmac.new(data[24:], DOMAIN + data[:24], hashlib.sha256).digest()
        ack = b"ULAH\x01\x02\x00\x00" + data[8:24] + mac
        self.pending.extend(self.mutate_ack(ack))
        self.after_write()

    def read(self, maximum, *, deadline):
        self.read_calls.append(maximum)
        result = bytes(self.pending[:min(maximum, self.max_chunk)])
        del self.pending[:len(result)]
        return result

    def close(self):
        self.closed = True


def connect(monkeypatch, pipe=None, peer=None, *, cancelled=lambda: False, session=SESSION):
    pipe, peer = pipe or Pipe(), peer or Peer()

    def open_pipe(name, **controls):
        assert name == "\\\\.\\pipe\\Utterleaf.OBS." + session.hex()
        assert controls["cancelled"] is cancelled
        return pipe

    monkeypatch.setattr(audio_pipe.windows_pipe, "connect", open_pipe)
    result = audio_pipe.connect(session, peer, cancelled=cancelled,
                                deadline=time.monotonic() + 2)
    return result, pipe, peer


def test_fragmented_ack_has_exact_role_bound_mac_and_retains_no_secret(monkeypatch):
    pipe = Pipe()
    pipe.max_chunk = 3
    secret = b"s" * 32
    monkeypatch.setattr(audio_pipe.secrets, "token_bytes", lambda count: secret)
    connection, pipe, peer = connect(monkeypatch, pipe)
    try:
        assert pipe.writes == [b"ULAH\x01\x01\x00\x00" + SESSION + secret]
        assert peer.checks == [123] * 4
        assert pipe.pid_calls == 3
        assert sum(min(value, 3) for value in pipe.read_calls) == 56
        assert all(value <= 56 for value in pipe.read_calls)
        assert repr(connection) == "ObsAudioPipe()"
        assert not any(value == secret for value in vars(connection).values())
    finally:
        connection.close()
    assert pipe.closed and peer.closed


def test_ack_matches_independently_computed_dotnet_hmac_vector(monkeypatch):
    pipe = Pipe()
    # Independently computed with System.Security.Cryptography.HMACSHA256:
    # key = ASCII s repeated 32; session = bytes 0..15; fixed role/domain above.
    mac = bytes.fromhex("f1893739588fa57f393e5b7ca8ffcc3319a3d0f332c4533994b8581c37e8b636")
    pipe.mutate_ack = lambda ack: b"ULAH\x01\x02\x00\x00" + SESSION + mac
    monkeypatch.setattr(audio_pipe.secrets, "token_bytes", lambda count: b"s" * count)
    connection, _, _ = connect(monkeypatch, pipe)
    connection.close()


@pytest.mark.parametrize("position", [0, 4, 5, 6, 8, 24, 55])
def test_wrong_ack_magic_version_kind_reserved_session_or_mac_is_terminal(monkeypatch, position):
    pipe, peer = Pipe(), Peer()

    def mutate(ack):
        changed = bytearray(ack)
        changed[position] ^= 1
        return bytes(changed)

    pipe.mutate_ack = mutate
    with pytest.raises(audio_pipe.ObsAudioPipeError) as caught:
        connect(monkeypatch, pipe, peer)
    assert pipe.closed and peer.closed and len(pipe.writes) == 1
    assert "fixture" not in str(caught.value)


@pytest.mark.parametrize("check", [2, 3])
def test_pipe_peer_refusal_before_secret_dispatch_sends_nothing(monkeypatch, check):
    pipe, peer = Pipe(), Peer()
    peer.fail_at = check
    with pytest.raises(audio_pipe.ObsAudioPipeError):
        connect(monkeypatch, pipe, peer)
    assert pipe.writes == [] and pipe.closed and peer.closed


def test_wrong_actual_pipe_server_pid_sends_nothing(monkeypatch):
    pipe, peer = Pipe(), Peer()
    pipe.pid = 456
    with pytest.raises(audio_pipe.ObsAudioPipeError):
        connect(monkeypatch, pipe, peer)
    assert pipe.writes == [] and pipe.closed and peer.closed


def test_truncated_ack_does_not_expose_audio(monkeypatch):
    pipe, peer = Pipe(), Peer()
    pipe.mutate_ack = lambda ack: ack[:40]
    with pytest.raises(audio_pipe.ObsAudioPipeError):
        connect(monkeypatch, pipe, peer)
    assert pipe.closed and peer.closed


def test_replayed_ack_fails_with_fresh_session_secret(monkeypatch):
    old_header = b"ULAH\x01\x01\x00\x00" + SESSION
    old_mac = hmac.new(b"o" * 32, DOMAIN + old_header, hashlib.sha256).digest()
    pipe, peer = Pipe(), Peer()
    pipe.mutate_ack = lambda ack: b"ULAH\x01\x02\x00\x00" + SESSION + old_mac
    monkeypatch.setattr(audio_pipe.secrets, "token_bytes", lambda count: b"n" * count)
    with pytest.raises(audio_pipe.ObsAudioPipeError):
        connect(monkeypatch, pipe, peer)
    assert pipe.closed and peer.closed


def test_late_handshake_cancellation_closes_both_leases(monkeypatch):
    pipe, peer = Pipe(), Peer()
    stopped = []
    pipe.after_write = lambda: stopped.append(True)
    with pytest.raises(audio_pipe.ObsAudioPipeCancelled):
        connect(monkeypatch, pipe, peer, cancelled=lambda: bool(stopped))
    assert pipe.closed and peer.closed


@pytest.mark.parametrize("session", [b"short", bytearray(16), "0" * 16, None])
def test_invalid_session_releases_process_before_any_pipe_io(monkeypatch, session):
    peer = Peer()
    monkeypatch.setattr(audio_pipe.windows_pipe, "connect", lambda *a, **k: pytest.fail("IO"))
    with pytest.raises(audio_pipe.ObsAudioPipeError):
        audio_pipe.connect(session, peer, cancelled=lambda: False, deadline=time.monotonic() + 1)
    assert peer.closed and peer.checks == []


def audio_frames(session=SESSION):
    return [
        protocol.StartFrame(session, 16000, 2, 4, 9000000000),
        protocol.AudioFrame(session, 2, 0, 9000000000, 160,
                            np.full((160, 2), 0.25, dtype="<f4").tobytes()),
        protocol.EndFrame(session, protocol.EndReason.STREAM_STOPPED, ((2, 0),)),
    ]


def test_fragmented_audio_retains_receiver_consent_and_actual_primary_bus(monkeypatch):
    connection, pipe, peer = connect(monkeypatch)
    frames = audio_frames()
    pipe.pending.extend(b"".join(protocol.encode_frame(frame) for frame in frames))
    pipe.max_chunk = 31
    receiver = ObsCaptureSession(SESSION, stream_active=False)
    try:
        assert receiver.state == "armed"
        receiver.notify_stream_started(SESSION)
        received = []
        while not pipe.closed:
            batch = connection.read_frames(deadline=time.monotonic() + 2)
            received.extend(batch)
            for frame in batch:
                receiver.accept(frame)
        assert received == frames
        assert receiver.primary_bus == 2 and receiver.buses == (2,)
        result = receiver.take_result()
        try:
            result.wait_ready(lambda: False)
            assert result.complete
        finally:
            result.close()
    finally:
        connection.close()
        receiver.close()
    assert peer.closed


def test_authenticated_pipe_does_not_grant_permission_to_capture(monkeypatch):
    connection, pipe, _ = connect(monkeypatch)
    pipe.pending.extend(protocol.encode_frame(audio_frames()[0]))
    receiver = ObsCaptureSession(SESSION, stream_active=False,
                                 store_factory=lambda rate: pytest.fail("Unarmed storage"))
    try:
        frames = connection.read_frames(deadline=time.monotonic() + 1)
        with pytest.raises(ObsSessionError):
            receiver.accept(frames[0])
    finally:
        connection.close()
        receiver.close()


@pytest.mark.parametrize("suffix", [b"U", protocol.encode_frame(audio_frames()[0])])
def test_end_with_trailing_partial_or_complete_frame_fails(monkeypatch, suffix):
    connection, pipe, peer = connect(monkeypatch)
    pipe.pending.extend(protocol.encode_frame(audio_frames()[-1]) + suffix)
    with pytest.raises(audio_pipe.ObsAudioPipeError):
        connection.read_frames(deadline=time.monotonic() + 1)
    assert pipe.closed and peer.closed


def test_identity_loss_after_read_prevents_returning_audio(monkeypatch):
    connection, pipe, peer = connect(monkeypatch)
    pipe.pending.extend(protocol.encode_frame(audio_frames()[0]))
    peer.fail_at = len(peer.checks) + 2
    with pytest.raises(audio_pipe.ObsAudioPipeError):
        connection.read_frames(deadline=time.monotonic() + 1)
    assert pipe.closed and peer.closed


def test_foreign_audio_session_is_terminal(monkeypatch):
    connection, pipe, peer = connect(monkeypatch)
    pipe.pending.extend(protocol.encode_frame(protocol.StartFrame(b"x" * 16, 16000, 0, 1, 0)))
    with pytest.raises(audio_pipe.ObsAudioPipeError):
        connection.read_frames(deadline=time.monotonic() + 1)
    assert pipe.closed and peer.closed


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native audio pipe integration")
def test_native_child_pipe_auth_and_receiver_continue_after_tcp_loss():
    session = secrets.token_bytes(16)
    expected_frames = audio_frames(session)
    server = start_native_pipe_server(
        "audio", b"".join(protocol.encode_frame(frame) for frame in expected_frames),
        session_id=session,
    )
    connection = retained = None
    receiver = ObsCaptureSession(session, stream_active=False)
    try:
        with socket.socket() as client:
            client.settimeout(3)
            client.connect(("127.0.0.1", server.tcp_port))
            with identity.open_expected_executable(sys._base_executable) as expected:
                with expected.verify(client, cancelled=lambda: False,
                                     deadline=time.monotonic() + 2) as peer:
                    assert peer.pid == server.server_pid
                    retained = peer.retain_process(cancelled=lambda: False,
                                                   deadline=time.monotonic() + 2)
                    connection = audio_pipe.connect(session, retained, cancelled=lambda: False,
                                                     deadline=time.monotonic() + 3)
                    client.shutdown(socket.SHUT_RDWR)
                    client.close()
                    # The original TCP-based identity fails; the independent
                    # pipe identity must still authenticate the same child.
                    with pytest.raises(identity.PeerIdentityError):
                        peer.revalidate(cancelled=lambda: False, deadline=time.monotonic() + 1)
        receiver.notify_stream_started(session)
        received = []
        while True:
            frames = connection.read_frames(deadline=time.monotonic() + 2)
            received.extend(frames)
            for frame in frames:
                receiver.accept(frame)
            if any(isinstance(frame, protocol.EndFrame) for frame in frames):
                break
        assert received == expected_frames
        result = receiver.take_result()
        try:
            result.wait_ready(lambda: False)
            assert result.complete and receiver.primary_bus == 2
        finally:
            result.close()
        server.process.wait(timeout=4)
        assert server.process.returncode == 0
    finally:
        if connection is not None:
            connection.close()
        if retained is not None:
            retained.close()
        receiver.close()
        if server.process.poll() is None:
            server.process.wait(timeout=10)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native audio pipe integration")
def test_native_wrong_pipe_process_receives_zero_secret_bytes():
    session = secrets.token_bytes(16)
    server = start_native_pipe_server("observe", session_id=session)
    retained = None
    try:
        with socket.socket() as listener, socket.socket() as client:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            client.connect(listener.getsockname())
            accepted, _ = listener.accept()
            with accepted, identity.open_expected_executable(sys._base_executable) as expected:
                with expected.verify(client, cancelled=lambda: False,
                                     deadline=time.monotonic() + 2) as peer:
                    assert peer.pid != server.server_pid
                    retained = peer.retain_process(cancelled=lambda: False,
                                                   deadline=time.monotonic() + 2)
                    with pytest.raises(audio_pipe.ObsAudioPipeError):
                        audio_pipe.connect(session, retained, cancelled=lambda: False,
                                           deadline=time.monotonic() + 3)
        server.process.wait(timeout=4)
        assert server.process.returncode == 0
        assert server.process.stdout.read().strip() == "BYTES 0"
    finally:
        if retained is not None:
            retained.close()
        if server.process.poll() is None:
            server.process.wait(timeout=10)
