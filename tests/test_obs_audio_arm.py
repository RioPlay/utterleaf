"""Focused Arm codec checks, independent of OBS or a microphone."""
import struct
import threading
import time

import pytest

from utterleaf import obs_audio_pipe as audio_pipe
from utterleaf import obs_protocol as protocol
from test_obs_audio_pipe import Peer, Pipe, SESSION


def opened():
    return audio_pipe.ObsAudioPipe(ArmPipe(), Peer(), SESSION, lambda: False)


class ArmPipe(Pipe):
    def write_all(self, data, *, deadline):
        self.writes.append(data)


ARM_REPLY = struct.Struct("<4sBBH16sBBH")


def accepted(pipe, *, mask=0, trailing=b""):
    pipe.pending.extend(ARM_REPLY.pack(b"ULAC", 1, 2, 0, SESSION, mask, 1, 0))
    pipe.pending.extend(trailing)


def test_arm_writes_exact_record_and_accepts_matching_reply():
    pipe = ArmPipe()
    connection = audio_pipe.ObsAudioPipe(pipe, Peer(), SESSION, lambda: False)
    pipe.pending.extend(struct.pack("<4sBBH16sBBH", b"ULAC", 1, 2, 0,
                                    SESSION, 7, 1, 0))
    connection.arm(additional_mix_mask=7, deadline=time.monotonic() + 1)
    assert pipe.writes == [struct.pack("<4sBBH16sBBH", b"ULAC", 1, 1, 0,
                                       SESSION, 7, 0, 0)]
    connection.close()


@pytest.mark.parametrize("reply", [
    struct.pack("<4sBBH16sBBH", b"NOPE", 1, 2, 0, SESSION, 0, 1, 0),
    struct.pack("<4sBBH16sBBH", b"ULAC", 9, 2, 0, SESSION, 0, 1, 0),
    struct.pack("<4sBBH16sBBH", b"ULAC", 1, 9, 0, SESSION, 0, 1, 0),
    struct.pack("<4sBBH16sBBH", b"ULAC", 1, 2, 1, SESSION, 0, 1, 0),
    struct.pack("<4sBBH16sBBH", b"ULAC", 1, 2, 0, b"x" * 16, 0, 1, 0),
    struct.pack("<4sBBH16sBBH", b"ULAC", 1, 2, 0, SESSION, 9, 1, 0),
    struct.pack("<4sBBH16sBBH", b"ULAC", 1, 2, 0, SESSION, 0, 2, 0),
    struct.pack("<4sBBH16sBBH", b"ULAC", 1, 2, 0, SESSION, 0, 3, 0),
    struct.pack("<4sBBH16sBBH", b"ULAC", 1, 2, 0, SESSION, 0, 1, 1),
])
def test_arm_rejects_bad_reply(reply):
    pipe = ArmPipe()
    pipe.pending.extend(reply)
    connection = audio_pipe.ObsAudioPipe(pipe, Peer(), SESSION, lambda: False)
    with pytest.raises(audio_pipe.ObsAudioPipeError):
        connection.arm(deadline=time.monotonic() + 1)
    assert pipe.closed


def test_read_frames_requires_arm_and_closes():
    connection = opened()
    with pytest.raises(audio_pipe.ObsAudioPipeError):
        connection.read_frames(deadline=time.monotonic() + 1)
    assert connection._closed.is_set()


def test_arm_is_single_use_and_coalesced_audio_remains_for_reader():
    pipe = ArmPipe()
    connection = audio_pipe.ObsAudioPipe(pipe, Peer(), SESSION, lambda: False)
    frame = protocol.encode_frame(protocol.StartFrame(SESSION, 16000, 2, 4, 9000000000))
    accepted(pipe, mask=3, trailing=frame)
    connection.arm(additional_mix_mask=3, deadline=time.monotonic() + 1)
    assert pipe.pending == frame
    assert connection.read_frames(deadline=time.monotonic() + 1) == [
        protocol.StartFrame(SESSION, 16000, 2, 4, 9000000000)
    ]
    with pytest.raises(audio_pipe.ObsAudioPipeError):
        connection.arm(additional_mix_mask=3, deadline=time.monotonic() + 1)
    assert pipe.closed and len(pipe.writes) == 1


@pytest.mark.parametrize("mask", [-1, 64, True, "0"])
def test_arm_bad_mask_is_terminal_before_dispatch(mask):
    pipe = ArmPipe()
    connection = audio_pipe.ObsAudioPipe(pipe, Peer(), SESSION, lambda: False)
    with pytest.raises(audio_pipe.ObsAudioPipeError):
        connection.arm(additional_mix_mask=mask, deadline=time.monotonic() + 1)
    assert pipe.closed and pipe.writes == []


def test_arm_deadline_and_peer_failure_are_terminal():
    pipe = ArmPipe()
    peer = Peer()
    connection = audio_pipe.ObsAudioPipe(pipe, peer, SESSION, lambda: False)
    with pytest.raises(audio_pipe.ObsAudioPipeError):
        connection.arm(deadline=time.monotonic() - 1)
    assert pipe.closed and pipe.writes == []

    pipe = Pipe()
    peer = Peer()
    peer.fail_at = len(peer.checks) + 2
    connection = audio_pipe.ObsAudioPipe(pipe, peer, SESSION, lambda: False)
    with pytest.raises(audio_pipe.ObsAudioPipeError):
        connection.arm(deadline=time.monotonic() + 1)
    assert pipe.closed and peer.closed

    pipe = ArmPipe()
    peer = Peer()
    peer.fail_at = 1
    connection = audio_pipe.ObsAudioPipe(pipe, peer, SESSION, lambda: False)
    with pytest.raises(audio_pipe.ObsAudioPipeError):
        connection.arm(deadline=time.monotonic() + 1)
    assert pipe.closed and pipe.writes == []


def test_arm_cancellation_after_dispatch_is_terminal():
    pipe = Pipe()
    stopped = []
    pipe.after_write = lambda: stopped.append(True)
    connection = audio_pipe.ObsAudioPipe(pipe, Peer(), SESSION,
                                         lambda: bool(stopped))
    with pytest.raises(audio_pipe.ObsAudioPipeCancelled):
        connection.arm(deadline=time.monotonic() + 1)
    assert pipe.closed and len(pipe.writes) == 1


class BlockingArmPipe(ArmPipe):
    def __init__(self):
        super().__init__()
        self.released = threading.Event()

    def read(self, maximum, *, deadline):
        self.released.wait(2)
        raise audio_pipe.ObsAudioPipeCancelled("closed")

    def close(self):
        self.closed = True
        self.released.set()


def test_close_interrupts_blocked_arm_without_second_dispatch():
    pipe = BlockingArmPipe()
    connection = audio_pipe.ObsAudioPipe(pipe, Peer(), SESSION, lambda: False)
    result = []

    def worker():
        try:
            connection.arm(deadline=time.monotonic() + 5)
        except BaseException as exc:
            result.append(exc)

    thread = threading.Thread(target=worker)
    thread.start()
    for _ in range(100):
        if pipe.writes:
            break
        time.sleep(0.01)
    connection.close()
    thread.join(2)
    assert not thread.is_alive()
    assert len(pipe.writes) == 1
    assert result and isinstance(result[0], audio_pipe.ObsAudioPipeCancelled)
