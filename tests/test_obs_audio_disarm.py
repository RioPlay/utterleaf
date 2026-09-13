"""Manual-stop intent, bounded waiting and no-audio results; no OBS/audio device."""

import struct
import secrets
import socket
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from utterleaf import obs_audio_pipe as audio_pipe
from utterleaf import obs_protocol as protocol
from utterleaf import windows_peer_identity as identity
from utterleaf.obs_session import ObsCaptureSession, ObsSessionError
from test_obs_audio_pipe import Peer, Pipe, SESSION
from windows_pipe_server import start_native_pipe_server


DISARM = b"ULAC\x01\x04\x00\x00" + SESSION + b"\0" * 4
RECEIPT = b"ULAC\x01\x03\x00\x00" + SESSION + b"\0" * 4
EMPTY_END = b"ULAP\x01\x04\x00\x00\x12\x00\x00\x00" + SESSION + b"\x02\x00"
START = protocol.StartFrame(SESSION, 16000, 2, 4, 9000000000)


class DisarmPipe(Pipe):
    def __init__(self):
        super().__init__()
        self.tail = EMPTY_END
        self.probe = lambda: None

    def available_bytes(self, *, deadline):
        self.probe()
        return len(self.pending)

    def write_all(self, data, *, deadline):
        if data == DISARM:
            self.writes.append(data)
            self.pending.extend(self.tail)
            self.after_write()
        else:
            super().write_all(data, deadline=deadline)


def opened(pipe=None, peer=None):
    pipe, peer = pipe or DisarmPipe(), peer or Peer()
    connection = audio_pipe.ObsAudioPipe(pipe, peer, SESSION, lambda: False)
    connection.arm(deadline=time.monotonic() + 2)
    return connection, pipe, peer


class Clock:
    now = 1000.0

    def monotonic(self):
        return self.now


def use_clock(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(audio_pipe, "time", SimpleNamespace(monotonic=clock.monotonic))
    return clock


def test_stop_intent_performs_no_io_and_coalesces_one_command():
    connection, pipe, peer = opened()
    original = list(pipe.writes)
    checks = list(peer.checks)
    assert connection.request_disarm()
    assert connection.request_disarm()
    assert pipe.writes == original and peer.checks == checks
    assert connection.read_frames() == [protocol.EndFrame(SESSION, protocol.EndReason.DISARMED, ())]
    assert pipe.writes == original + [DISARM, RECEIPT]
    assert pipe.closed and peer.closed
    assert not connection.request_disarm()
    assert pipe.writes == original + [DISARM, RECEIPT]


def test_stop_requires_completed_arm():
    pipe = DisarmPipe()
    connection = audio_pipe.ObsAudioPipe(pipe, Peer(), SESSION, lambda: False)
    try:
        with pytest.raises(audio_pipe.ObsAudioPipeError, match="not armed"):
            connection.request_disarm()
        assert not pipe.writes
    finally:
        connection.close()


def test_empty_end_independent_bytes_decode_fragmented_and_encode_exactly():
    decoder = protocol.FrameDecoder()
    frames = []
    for value in EMPTY_END:
        frames.extend(decoder.feed(bytes([value])))
    assert frames == [protocol.EndFrame(SESSION, protocol.EndReason.DISARMED, ())]
    assert not decoder.has_partial_frame
    decoder.finish()
    assert protocol.encode_frame(frames[0]) == EMPTY_END


@pytest.mark.parametrize("reason", [1, 3, 4, 5, 9])
def test_zero_sequence_end_is_rejected_for_every_other_reason(reason):
    decoder = protocol.FrameDecoder()
    raw = EMPTY_END[:-2] + bytes([reason, 0])
    with pytest.raises(protocol.ProtocolError):
        decoder.feed(raw)
    assert not decoder.has_partial_frame


@pytest.mark.parametrize("started_event", [False, True])
def test_pre_audio_disarm_never_constructs_stores_or_complete_transcript(started_event):
    receiver = ObsCaptureSession(SESSION, buses=(1, 4), stream_active=False,
                                 store_factory=lambda _: pytest.fail("unexpected audio store"))
    if started_event:
        receiver.notify_stream_started(SESSION)
    receiver.accept(protocol.EndFrame(SESSION, protocol.EndReason.DISARMED, ()))
    assert receiver.state == "finished"
    result = receiver.take_result()
    try:
        result.wait_ready()
        assert not result.complete and not result.tracks
        assert result.origin_ns is None and result.primary_bus is None
        assert "before audio began" in result.reason
        with pytest.raises(ObsSessionError):
            receiver.accept(START)
        with pytest.raises(ObsSessionError):
            receiver.take_result()
    finally:
        receiver.close()
        result.close()


def test_pre_audio_end_cannot_claim_a_bus_or_sequence():
    receiver = ObsCaptureSession(SESSION, stream_active=False,
                                 store_factory=lambda _: pytest.fail("unexpected audio store"))
    try:
        with pytest.raises(ObsSessionError):
            receiver.accept(protocol.EndFrame(SESSION, protocol.EndReason.DISARMED, ((0, None),)))
        assert receiver.state == "incomplete"
    finally:
        receiver.close()


def test_active_disarm_drains_ordered_audio_before_terminal_receipt():
    connection, pipe, peer = opened()
    samples = struct.pack("<ffff", 0.25, 0.5, -0.25, -0.5)
    audio = protocol.AudioFrame(SESSION, 2, 0, START.origin_ns, 2, samples)
    end = protocol.EndFrame(SESSION, protocol.EndReason.DISARMED, ((2, 0),))
    pipe.pending.extend(protocol.encode_frame(START))
    assert connection.read_frames() == [START]
    pipe.tail = protocol.encode_frame(audio) + protocol.encode_frame(end)
    assert connection.request_disarm()
    assert connection.read_frames() == [audio, end]
    assert pipe.writes[-2:] == [DISARM, RECEIPT]
    assert pipe.closed and peer.closed


def test_normal_end_racing_stop_still_has_one_receipt():
    connection, pipe, _ = opened()
    end = protocol.EndFrame(SESSION, protocol.EndReason.STREAM_STOPPED, ((2, None),))
    pipe.pending.extend(protocol.encode_frame(START) + protocol.encode_frame(end))
    pipe.tail = b""  # Server has already committed normal stop.
    connection.request_disarm()
    assert connection.read_frames() == [START, end]
    assert pipe.writes[-2:] == [DISARM, RECEIPT]


@pytest.mark.parametrize("start_first", [False, True])
def test_unsolicited_or_post_start_empty_end_is_not_acknowledged(start_first):
    connection, pipe, peer = opened()
    if start_first:
        pipe.pending.extend(protocol.encode_frame(START))
        assert connection.read_frames() == [START]
        connection.request_disarm()
    else:
        pipe.pending.extend(EMPTY_END)
    with pytest.raises(audio_pipe.ObsAudioPipeError):
        connection.read_frames()
    assert RECEIPT not in pipe.writes and pipe.closed and peer.closed


@pytest.mark.parametrize("preceding", [
    protocol.AudioFrame(SESSION, 2, 0, START.origin_ns, 1, struct.pack("<ff", 0.0, 0.0)),
    protocol.GapFrame(SESSION, 2, 0, 1, START.origin_ns),
])
@pytest.mark.parametrize("separate_reads", [False, True])
def test_empty_end_after_any_prior_pcm_frame_is_not_acknowledged(preceding, separate_reads):
    connection, pipe, peer = opened()
    raw = protocol.encode_frame(preceding)
    if separate_reads:
        pipe.pending.extend(raw)
        assert connection.read_frames() == [preceding]
    else:
        pipe.pending.extend(raw)
    connection.request_disarm()
    with pytest.raises(audio_pipe.ObsAudioPipeError):
        connection.read_frames()
    assert RECEIPT not in pipe.writes and pipe.closed and peer.closed


def test_armed_idle_has_no_duration_cutoff_but_stop_is_serviced(monkeypatch):
    connection, pipe, peer = opened()
    clock = use_clock(monkeypatch)
    probes = []

    def idle():
        probes.append(clock.now)
        clock.now += 24 * 60 * 60
        if len(probes) == 3:
            connection.request_disarm()

    pipe.probe = idle
    try:
        # Once Disarm is dispatched, stop advancing time and supply the End.
        pipe.after_write = lambda: setattr(pipe, "probe", lambda: None)
        assert connection.read_frames() == [protocol.EndFrame(SESSION, protocol.EndReason.DISARMED, ())]
        assert len(probes) == 3 and len(peer.checks) >= 8
    finally:
        connection.close()


def test_partial_packet_deadline_survives_multiple_read_calls(monkeypatch):
    connection, pipe, peer = opened()
    clock = use_clock(monkeypatch)
    raw = protocol.encode_frame(START)
    pipe.pending.extend(raw[:1])
    assert connection.read_frames() == []
    clock.now += 4
    pipe.pending.extend(raw[1:2])
    assert connection.read_frames() == []
    clock.now += 2
    pipe.pending.extend(raw[2:])
    with pytest.raises(audio_pipe.ObsAudioPipeError):
        connection.read_frames()
    assert pipe.closed and peer.closed


def test_active_idle_is_bounded_even_without_caller_deadline(monkeypatch):
    connection, pipe, peer = opened()
    pipe.pending.extend(protocol.encode_frame(START))
    assert connection.read_frames() == [START]
    clock = use_clock(monkeypatch)
    pipe.probe = lambda: setattr(clock, "now", clock.now + 6)
    with pytest.raises(audio_pipe.ObsAudioPipeError):
        connection.read_frames()
    assert pipe.closed and peer.closed


def test_requested_stop_deadline_is_not_reset_by_fragmented_data(monkeypatch):
    connection, pipe, peer = opened()
    clock = use_clock(monkeypatch)
    pipe.tail = EMPTY_END[:5]
    connection.request_disarm()
    assert connection.read_frames() == []
    clock.now += 8
    pipe.pending.extend(EMPTY_END[5:])
    with pytest.raises(audio_pipe.ObsAudioPipeError):
        connection.read_frames()
    assert pipe.writes.count(DISARM) == 1 and RECEIPT not in pipe.writes
    assert pipe.closed and peer.closed


def test_peer_failure_before_disarm_sends_no_command():
    connection, pipe, peer = opened()
    peer.fail_at = len(peer.checks) + 1
    connection.request_disarm()
    with pytest.raises(audio_pipe.ObsAudioPipeError):
        connection.read_frames()
    assert DISARM not in pipe.writes and pipe.closed and peer.closed


@pytest.mark.parametrize("deadline", [True, "tomorrow", float("nan"), float("inf"), -1])
def test_invalid_or_expired_deadline_is_terminal_before_stop_write(deadline):
    connection, pipe, peer = opened()
    connection.request_disarm()
    with pytest.raises(audio_pipe.ObsAudioPipeError):
        connection.read_frames(deadline=deadline)
    assert DISARM not in pipe.writes and pipe.closed and peer.closed


def test_stop_request_does_not_wait_for_busy_reader():
    connection, pipe, _ = opened()
    entered, release = threading.Event(), threading.Event()
    frames, errors = [], []

    def probe():
        entered.set()
        assert release.wait(2)
        pipe.probe = lambda: None

    def read():
        try:
            frames.extend(connection.read_frames())
        except BaseException as exc:
            errors.append(exc)

    pipe.probe = probe
    thread = threading.Thread(target=read)
    thread.start()
    try:
        assert entered.wait(2)
        assert connection.request_disarm()  # I/O lock is held by the reader.
    finally:
        release.set()
        thread.join(2)
        connection.close()
    assert not thread.is_alive() and not errors
    assert frames == [protocol.EndFrame(SESSION, protocol.EndReason.DISARMED, ())]


def test_close_interrupts_indefinite_idle_reader_and_releases_lease():
    connection, pipe, peer = opened()
    queried = threading.Event()
    pipe.probe = queried.set
    errors = []

    def read():
        try:
            connection.read_frames()
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=read)
    thread.start()
    assert queried.wait(2)
    connection.close()
    thread.join(2)
    assert not thread.is_alive() and pipe.closed and peer.closed
    assert len(errors) == 1 and isinstance(errors[0], audio_pipe.ObsAudioPipeCancelled)
    assert DISARM not in pipe.writes


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native audio pipe integration")
def test_native_armed_disarm_receipt_after_control_socket_closed():
    session = secrets.token_bytes(16)
    raw_end = EMPTY_END[:12] + session + EMPTY_END[-2:]
    server = start_native_pipe_server("audio_disarm", raw_end, session_id=session)
    connection = retained = None
    receiver = ObsCaptureSession(session, stream_active=False,
                                 store_factory=lambda _: pytest.fail("unexpected audio store"))
    try:
        with socket.socket() as client:
            client.settimeout(3)
            client.connect(("127.0.0.1", server.tcp_port))
            with identity.open_expected_executable(sys._base_executable) as expected:
                with expected.verify(client, cancelled=lambda: False,
                                     deadline=time.monotonic() + 2) as peer:
                    retained = peer.retain_process(cancelled=lambda: False,
                                                   deadline=time.monotonic() + 2)
                    connection = audio_pipe.connect(session, retained, cancelled=lambda: False,
                                                     deadline=time.monotonic() + 3)
                    connection.arm(deadline=time.monotonic() + 2)
                    client.shutdown(socket.SHUT_RDWR)
        assert connection.request_disarm()
        frames = connection.read_frames()
        assert frames == [protocol.EndFrame(session, protocol.EndReason.DISARMED, ())]
        receiver.accept(frames[0])
        result = receiver.take_result()
        try:
            result.wait_ready()
            assert not result.tracks and not result.complete
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
