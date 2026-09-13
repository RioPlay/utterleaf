import io
import threading
import time

import numpy as np
import pytest

import utterleaf.capture_store as store
from utterleaf.transcript import TranscriptionCancelled


def _wait_written(capture, samples):
    with capture._condition:
        assert capture._condition.wait_for(
            lambda: capture.progress.written_source_samples >= samples,
            timeout=2,
        )


def _append(capture, audio, block_samples=8000):
    for offset in range(0, len(audio), block_samples):
        assert capture.append(audio[offset:offset + block_samples])
    _wait_written(capture, len(audio))


def test_live_read_exposes_only_full_window_before_finish(monkeypatch):
    monkeypatch.setattr(store, "WINDOW_SECONDS", 2)
    capture = store.CaptureStore(8000)
    try:
        source = np.linspace(-0.5, 0.5, 20_000, dtype=np.float32)
        _append(capture, source)

        first = capture.read_window(0)
        assert first.state is store.CaptureReadState.READY
        assert first.source_offset == 0
        assert first.source_samples == 16_000
        assert first.next_source_offset == 16_000
        assert first.audio.dtype == np.float32
        assert len(first.audio) == 32_000

        tail = capture.read_window(first.next_source_offset)
        assert tail.state is store.CaptureReadState.UNAVAILABLE
        assert tail.audio is None
        assert tail.source_samples == 0
        assert capture.progress == store.CaptureProgress(20_000, False, False, None)
    finally:
        capture.close()


def test_live_read_never_waits_behind_writer_file_io(monkeypatch):
    monkeypatch.setattr(store, "WINDOW_SECONDS", 1)
    second_write_started = threading.Event()
    release_write = threading.Event()

    class SlowSecondWrite(io.BytesIO):
        def __init__(self):
            super().__init__()
            self.writes = 0

        def write(self, data):
            self.writes += 1
            if self.writes == 2:
                second_write_started.set()
                assert release_write.wait(2)
            return super().write(data)

    handle = SlowSecondWrite()
    monkeypatch.setattr(store.tempfile, "TemporaryFile", lambda **kw: handle)
    capture = store.CaptureStore(8000)
    try:
        first_source = np.full(8000, 0.125, np.float32)
        assert capture.append(first_source)
        _wait_written(capture, 8000)
        assert capture.append(np.full(1000, 0.5, np.float32))
        assert second_write_started.wait(2)

        started = time.monotonic()
        result = capture.read_window(0)
        elapsed = time.monotonic() - started
        assert result.state is store.CaptureReadState.UNAVAILABLE
        assert elapsed < 0.2

        release_write.set()
        _wait_written(capture, 9000)
        result = capture.read_window(0)
        assert result.state is store.CaptureReadState.READY
        assert result.source_samples == 8000
        np.testing.assert_allclose(result.audio[200:-200], 0.125, atol=1e-5)
    finally:
        release_write.set()
        capture.close()


def test_append_never_waits_behind_live_reader_file_io(monkeypatch):
    monkeypatch.setattr(store, "WINDOW_SECONDS", 1)
    read_started = threading.Event()
    release_read = threading.Event()

    class SlowRead(io.BytesIO):
        def read(self, size=-1):
            read_started.set()
            assert release_read.wait(2)
            return super().read(size)

    monkeypatch.setattr(store.tempfile, "TemporaryFile", lambda **kw: SlowRead())
    capture = store.CaptureStore(8000)
    try:
        _append(capture, np.zeros(8000, np.float32))
        result = []
        reader = threading.Thread(target=lambda: result.append(capture.read_window(0)))
        reader.start()
        assert read_started.wait(2)

        appended = threading.Event()

        def append():
            assert capture.append(np.ones(1000, np.float32))
            appended.set()

        callback = threading.Thread(target=append)
        callback.start()
        assert appended.wait(0.5)
        callback.join(2)
        assert not callback.is_alive()

        release_read.set()
        reader.join(2)
        assert not reader.is_alive()
        assert result[0].state is store.CaptureReadState.READY
    finally:
        release_read.set()
        capture.close()


def test_live_readers_use_independent_absolute_offsets(monkeypatch):
    monkeypatch.setattr(store, "WINDOW_SECONDS", 1)
    read_started = threading.Event()
    release_read = threading.Event()

    class BlockingFirstRead(io.BytesIO):
        def __init__(self):
            super().__init__()
            self.first_read = True

        def read(self, size=-1):
            if self.first_read:
                self.first_read = False
                read_started.set()
                if not release_read.wait(2):
                    raise RuntimeError("Timed out waiting for deterministic reader handoff")
            return super().read(size)

    monkeypatch.setattr(store.tempfile, "TemporaryFile", lambda **kw: BlockingFirstRead())
    capture = store.CaptureStore(8000)
    try:
        source = np.concatenate([
            np.full(8000, 0.1, np.float32),
            np.full(8000, 0.2, np.float32),
        ])
        _append(capture, source)
        results = {}
        errors = []

        def read_second():
            try:
                results["second"] = capture.read_window(8000)
            except Exception as exc:
                errors.append(exc)

        reader = threading.Thread(target=read_second)
        reader.start()
        assert read_started.wait(2)

        unavailable = capture.read_window(0)
        assert unavailable.state is store.CaptureReadState.UNAVAILABLE

        release_read.set()
        reader.join(2)
        assert not reader.is_alive()
        assert errors == []
        results["first"] = capture.read_window(0)
        assert set(results) == {"first", "second"}
        assert all(result.state is store.CaptureReadState.READY for result in results.values())
        assert results["first"].source_offset == 0
        assert results["second"].source_offset == 8000
        np.testing.assert_allclose(results["first"].audio[200:-200], 0.1, atol=1e-5)
        np.testing.assert_allclose(results["second"].audio[200:-200], 0.2, atol=1e-5)

        repeated = capture.read_window(8000)
        assert repeated.state is store.CaptureReadState.READY
        np.testing.assert_array_equal(repeated.audio, results["second"].audio)
    finally:
        release_read.set()
        capture.close()


def test_final_partial_window_then_clean_completion(monkeypatch):
    monkeypatch.setattr(store, "WINDOW_SECONDS", 2)
    capture = store.CaptureStore(16000)
    try:
        source = np.arange(12_345, dtype=np.float32) / 20_000
        _append(capture, source)
        assert capture.read_window(0).state is store.CaptureReadState.UNAVAILABLE

        capture.finish().wait_ready()
        tail = capture.read_window(0)
        assert tail.state is store.CaptureReadState.READY
        assert tail.source_samples == len(source)
        assert tail.next_source_offset == len(source)
        np.testing.assert_array_equal(tail.audio, source)

        done = capture.read_window(tail.next_source_offset)
        assert done.state is store.CaptureReadState.COMPLETE
        assert done.audio is None
        assert done.error is None
        assert capture.progress.terminal
    finally:
        capture.close()


def test_storage_failure_keeps_exact_readable_prefix(monkeypatch):
    class PartialFile(io.BytesIO):
        def write(self, data):
            if self.tell() >= 10:
                raise OSError("disk full")
            return super().write(data[:10])

    monkeypatch.setattr(store.tempfile, "TemporaryFile", lambda **kw: PartialFile())
    capture = store.CaptureStore(16000)
    try:
        assert capture.append(np.arange(8, dtype=np.float32))
        capture.finish().wait_ready()
        assert capture.progress.written_source_samples == 2
        assert capture.progress.error == capture.error

        prefix = capture.read_window(0)
        assert prefix.state is store.CaptureReadState.READY
        assert prefix.source_samples == 2
        np.testing.assert_array_equal(prefix.audio, [0, 1])

        failed = capture.read_window(prefix.next_source_offset)
        assert failed.state is store.CaptureReadState.FAILED
        assert failed.source_offset == 2
        assert failed.error == capture.error
        assert failed.audio is None
    finally:
        capture.close()


def test_empty_store_changes_from_unavailable_to_complete():
    capture = store.CaptureStore(16000)
    try:
        assert capture.read_window(0).state is store.CaptureReadState.UNAVAILABLE
        assert not capture.progress.terminal
        capture.finish().wait_ready()
        assert capture.read_window(0).state is store.CaptureReadState.COMPLETE
        assert capture.progress == store.CaptureProgress(0, True, False, None)
    finally:
        capture.close()


def test_cancelled_or_closed_read_fails_promptly(monkeypatch):
    monkeypatch.setattr(store, "WINDOW_SECONDS", 1)
    read_started = threading.Event()
    release_read = threading.Event()

    class BlockingRead(io.BytesIO):
        def read(self, size=-1):
            read_started.set()
            assert release_read.wait(2)
            return super().read(size)

    handle = BlockingRead()
    monkeypatch.setattr(store.tempfile, "TemporaryFile", lambda **kw: handle)
    capture = store.CaptureStore(8000)
    _append(capture, np.ones(8000, np.float32))
    capture.finish().wait_ready()

    errors = []

    def read():
        try:
            capture.read_window(0)
        except Exception as exc:
            errors.append(exc)

    reader = threading.Thread(target=read)
    reader.start()
    assert read_started.wait(2)
    started = time.monotonic()
    capture.close()
    assert time.monotonic() - started < 0.2
    assert capture.progress.closed
    with pytest.raises(TranscriptionCancelled):
        capture.read_window(0)

    release_read.set()
    reader.join(2)
    assert not reader.is_alive()
    assert len(errors) == 1
    assert isinstance(errors[0], TranscriptionCancelled)
    assert handle.closed


def test_cancel_callback_prevents_file_access(monkeypatch):
    capture = store.CaptureStore(16000)
    try:
        capture.finish().wait_ready()
        monkeypatch.setattr(capture._file, "read", lambda size: pytest.fail("read after cancel"))
        with pytest.raises(TranscriptionCancelled):
            capture.read_window(0, lambda: True)
    finally:
        capture.close()


def test_cancellation_during_conversion_discards_late_audio(monkeypatch):
    monkeypatch.setattr(store, "WINDOW_SECONDS", 1)
    conversion_started = threading.Event()
    release_conversion = threading.Event()
    cancelled = threading.Event()

    def resample(audio, rate):
        conversion_started.set()
        assert release_conversion.wait(2)
        return audio.copy()

    monkeypatch.setattr("utterleaf.audio.resample_audio", resample)
    capture = store.CaptureStore(16000)
    _append(capture, np.ones(16000, np.float32))
    errors = []

    def read():
        try:
            capture.read_window(0, cancelled.is_set)
        except Exception as exc:
            errors.append(exc)

    reader = threading.Thread(target=read)
    reader.start()
    assert conversion_started.wait(2)
    cancelled.set()
    release_conversion.set()
    reader.join(2)
    assert not reader.is_alive()
    assert len(errors) == 1
    assert isinstance(errors[0], TranscriptionCancelled)
    capture.close()


def test_live_reads_and_legacy_chunks_do_not_share_a_cursor(monkeypatch):
    monkeypatch.setattr(store, "WINDOW_SECONDS", 1)
    capture = store.CaptureStore(8000)
    try:
        source = np.concatenate([
            np.full(8000, 0.1, np.float32),
            np.full(8000, 0.2, np.float32),
            np.full(1000, 0.3, np.float32),
        ])
        _append(capture, source)
        capture.finish().wait_ready()

        live_second = capture.read_window(8000)
        chunks = list(capture.chunks())
        live_first = capture.read_window(0)

        assert [len(chunk) for chunk in chunks] == [16000, 16000, 2000]
        assert live_first.state is store.CaptureReadState.READY
        assert live_second.state is store.CaptureReadState.READY
        np.testing.assert_array_equal(live_first.audio, chunks[0])
        np.testing.assert_array_equal(live_second.audio, chunks[1])
    finally:
        capture.close()


def test_each_live_disk_read_is_bounded_to_one_window(monkeypatch):
    monkeypatch.setattr(store, "WINDOW_SECONDS", 1)

    class RecordingFile(io.BytesIO):
        def __init__(self):
            super().__init__()
            self.read_sizes = []

        def read(self, size=-1):
            self.read_sizes.append(size)
            return super().read(size)

    handle = RecordingFile()
    monkeypatch.setattr(store.tempfile, "TemporaryFile", lambda **kw: handle)
    capture = store.CaptureStore(192000)
    try:
        source = np.linspace(-0.5, 0.5, 200_000, dtype=np.float32)
        _append(capture, source, block_samples=100_000)
        first = capture.read_window(0)
        assert first.state is store.CaptureReadState.READY
        assert first.source_samples == 192_000
        assert len(first.audio) == 16_000
        assert handle.read_sizes == [192_000 * 4]
        assert first.audio.nbytes == 16_000 * 4
        assert capture.pending_bytes <= store.MAX_PENDING_BYTES
    finally:
        capture.close()


@pytest.mark.parametrize("offset", [-1, 1.5, "0", None, True])
def test_live_read_rejects_invalid_offsets(offset):
    capture = store.CaptureStore(16000)
    try:
        with pytest.raises(ValueError, match="nonnegative integer"):
            capture.read_window(offset)
    finally:
        capture.close()
