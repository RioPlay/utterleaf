"""Device liveness contracts using synthetic PCM and a controllable clock."""

from types import SimpleNamespace
from contextlib import nullcontext
import threading

import numpy as np
import pytest

from utterleaf import audio


@pytest.fixture(autouse=True)
def synthetic_com(monkeypatch):
    monkeypatch.setattr("utterleaf.audio_owner._com_scope", nullcontext)


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


def test_windows_native_stream_lifecycle_stays_on_owner(capture, monkeypatch):
    capture.recorder.close()
    monkeypatch.setattr(audio.sys, "platform", "win32")
    calls = []
    stream_type = type(capture.streams[-1])

    class OwnedStream(stream_type):
        def __init__(self, **kwargs):
            calls.append(("open", threading.get_ident()))
            super().__init__(**kwargs)

        def start(self):
            calls.append(("start", threading.get_ident()))
            super().start()

        def stop(self):
            calls.append(("stop", threading.get_ident()))
            super().stop()

        def close(self):
            calls.append(("close", threading.get_ident()))
            super().close()

    monkeypatch.setattr(audio.sd, "InputStream", OwnedStream)
    recorder = capture.recorder
    recorder.start()
    capture.callback(.1, .25)
    assert recorder.capture_error() is None
    assert recorder.stop().size == 1600
    other = threading.Thread(target=recorder.close)
    other.start()
    other.join(timeout=5)
    assert not other.is_alive()
    assert [name for name, _ in calls] == ["open", "start", "stop", "close"]
    assert len({ident for _, ident in calls}) == 1
    assert calls[0][1] != threading.get_ident()
    assert recorder._owner is None


def test_windows_liveness_waits_for_owner_teardown(capture, monkeypatch):
    recorder = capture.recorder
    recorder.close()
    monkeypatch.setattr(audio.sys, "platform", "win32")
    reads = []
    stream_type = type(capture.streams[-1])

    class OwnedStream(stream_type):
        @property
        def active(self):
            reads.append(threading.get_ident())
            return self._active

        @active.setter
        def active(self, value):
            self._active = value

    monkeypatch.setattr(audio.sd, "InputStream", OwnedStream)
    recorder.start()
    owner = recorder._owner
    busy, release = threading.Event(), threading.Event()
    closing, checking, checked = threading.Event(), threading.Event(), threading.Event()
    failures, results = [], []

    def block_owner():
        busy.set()
        if not release.wait(5):
            raise TimeoutError("Synthetic owner was not released")

    original_close = owner.close
    def observed_close(teardown):
        # Recorder detached _owner but still holds its lifecycle lock.
        closing.set()
        original_close(teardown)
    monkeypatch.setattr(owner, "close", observed_close)

    def run(action):
        try:
            action()
        except BaseException as exc:
            failures.append(exc)

    def check():
        checking.set()
        results.append(recorder.capture_error())
        checked.set()

    worker = threading.Thread(target=lambda: run(lambda: owner.call(block_owner)), daemon=True)
    closer = threading.Thread(target=lambda: run(recorder.close), daemon=True)
    checker = threading.Thread(target=lambda: run(check), daemon=True)
    started = []
    try:
        worker.start(); started.append(worker)
        assert busy.wait(2)
        closer.start(); started.append(closer)
        assert closing.wait(2)
        assert recorder._owner is None
        checker.start(); started.append(checker)
        assert checking.wait(2)
        assert not checked.wait(.05)
        assert reads == []  # No active query on caller while teardown is pending.
    finally:
        release.set()
        for thread in started:
            thread.join(3)
    assert all(not thread.is_alive() for thread in started)
    assert failures == []
    assert results == [None]
    assert reads == []
    assert capture.streams[-1].closed
    assert not owner._thread.is_alive()


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
