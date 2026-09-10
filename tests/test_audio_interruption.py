"""Device liveness contracts using synthetic PCM and a controllable clock."""

from types import SimpleNamespace

import numpy as np
import pytest

from utterleaf import audio


@pytest.fixture
def capture(monkeypatch):
    clock = [100.0]
    streams = []

    class Stream:
        def __init__(self, **kwargs):
            self.callback = kwargs["callback"]
            self.active = False
            self.closed = False
            streams.append(self)

        def start(self):
            self.active = True

        def stop(self):
            self.active = False

        def close(self):
            self.active = False
            self.closed = True

    monkeypatch.setattr(audio.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(audio.sd, "query_devices", lambda *a, **k: {
        "name": "Selected microphone", "default_samplerate": 16000,
    })
    monkeypatch.setattr(audio.sd, "InputStream", Stream)
    recorder = audio.Recorder()
    recorder.start(max_seconds=120)

    def callback(seconds=.1, value=0.0, stream=None):
        pcm = np.full((int(seconds * 16000), 1), value, dtype=np.float32)
        (stream or streams[-1]).callback(pcm, len(pcm), None, None)

    yield SimpleNamespace(recorder=recorder, clock=clock, streams=streams, callback=callback)
    recorder.close()


def test_silence_callbacks_are_healthy_for_a_long_take(capture):
    for _ in range(60):
        capture.clock[0] += .5
        capture.callback(.5, 0)
        assert capture.recorder.capture_error() is None
    assert capture.recorder.stop().size == 30 * 16000


def test_no_first_callback_has_a_bounded_grace_period(capture):
    capture.clock[0] += audio.CALLBACK_TIMEOUT_SECONDS - .001
    assert capture.recorder.capture_error() is None
    capture.clock[0] += .001
    assert capture.recorder.capture_error() == "The microphone stopped sending audio."


def test_callback_loss_keeps_already_captured_speech(capture):
    capture.callback(.5, .25)
    capture.clock[0] += audio.CALLBACK_TIMEOUT_SECONDS
    assert capture.recorder.capture_error()
    take = capture.recorder.stop()
    assert take.size == 8000
    np.testing.assert_array_equal(take, np.full(8000, .25, dtype=np.float32))
    assert capture.recorder.capture_error() is None


def test_stopped_stream_detected_even_with_recent_callback(capture):
    capture.callback()
    capture.streams[-1].active = False
    assert capture.recorder.capture_error() == "The microphone stream stopped."
    assert capture.recorder.snapshot().size == 1600


def test_stream_status_error_is_treated_as_interruption(capture):
    class BrokenStream:
        @property
        def active(self):
            raise audio.sd.PortAudioError("Device was removed")

    original = capture.recorder._stream
    capture.recorder._stream = BrokenStream()
    try:
        assert capture.recorder.capture_error() == "The microphone stream stopped."
    finally:
        capture.recorder._stream = original


def test_empty_callbacks_do_not_extend_heartbeat(capture):
    capture.clock[0] += audio.CALLBACK_TIMEOUT_SECONDS
    capture.callback(0)
    assert capture.recorder.capture_error()


def test_new_take_gets_its_own_grace_period(capture):
    capture.callback()
    capture.recorder.stop()
    capture.clock[0] += 60
    capture.recorder.start(max_seconds=120)
    assert capture.recorder.capture_error() is None
    capture.clock[0] += audio.CALLBACK_TIMEOUT_SECONDS
    assert capture.recorder.capture_error()


def test_callbacks_from_closed_stream_cannot_seed_the_next_take(capture):
    old = capture.streams[-1]
    capture.callback(.5, .5)
    capture.recorder.close()
    capture.callback(.5, .9, old)
    assert capture.recorder.snapshot().size == 0
    capture.recorder.start(max_seconds=120)
    capture.callback(.5, .9, old)
    capture.callback(.25, .2)
    np.testing.assert_array_equal(capture.recorder.stop(), np.full(4000, .2, dtype=np.float32))
    assert old.closed


def test_stale_callback_cannot_keep_new_stream_alive(capture):
    old = capture.streams[-1]
    capture.recorder.close()
    capture.recorder.start(max_seconds=120)
    capture.clock[0] += audio.CALLBACK_TIMEOUT_SECONDS
    capture.callback(.5, .9, old)
    assert capture.recorder.capture_error()


def test_liveness_result_ignores_a_stream_closed_during_status_read(capture):
    recorder = capture.recorder
    original = recorder._stream

    class ChangingStream:
        @property
        def active(self):
            recorder.stop()
            return False

    recorder._stream = ChangingStream()
    try:
        assert recorder.capture_error() is None
    finally:
        recorder._stream = original


@pytest.mark.parametrize("close_fails", [False, True])
def test_failed_open_callbacks_cannot_seed_a_retry(capture, monkeypatch, close_fails):
    recorder = capture.recorder
    recorder.close()
    callbacks = []
    original_type = type(capture.streams[-1])

    class FailingStream:
        def __init__(self, **kwargs):
            callbacks.append(kwargs["callback"])

        def start(self):
            raise RuntimeError("Open failed")

        def close(self):
            if close_fails:
                raise RuntimeError("Close failed")

    monkeypatch.setattr(audio.sd, "InputStream", FailingStream)
    with pytest.raises(RuntimeError, match="Open failed"):
        recorder.start()
    pcm = np.ones((1600, 1), dtype=np.float32)
    callbacks[-1](pcm, len(pcm), None, None)
    monkeypatch.setattr(audio.sd, "InputStream", original_type)
    recorder.start(max_seconds=120)
    assert recorder.snapshot().size == 0
    assert recorder.capture_error() is None
