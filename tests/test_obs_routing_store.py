"""Bounded storage and lifecycle tests for private OBS routing history."""

from __future__ import annotations

import io
import threading

import pytest

from utterleaf import obs_routing_store as storage
from utterleaf.obs_mix import BusLabel, MixSnapshot, SourceAssignment
from utterleaf.obs_protocol import PROVENANCE_VERSION, RoutingFrame, encode_frame
from utterleaf.transcript import TranscriptionCancelled


SESSION = b"routing-session!"


def routing(revision=1, *, observed=100, name="Input", label="Stream"):
    snapshot = MixSnapshot(
        0,
        1,
        (SourceAssignment(revision.to_bytes(16, "big"), name, 1),),
        (BusLabel(0, label),),
    )
    return RoutingFrame(SESSION, revision, observed, ((0, revision - 1),), snapshot)


def finish(store):
    store.finish()
    store.wait_ready()
    return store


def close(store):
    store.close()
    assert store.wait_closed(2)


def test_records_drain_in_order_and_use_exact_version2_bytes():
    journal = io.BytesIO()
    store = storage.ObsRoutingStore(journal_factory=lambda: journal)
    frames = (routing(1), routing(2, observed=200))
    assert all(store.append(frame) for frame in frames)

    finish(store)

    assert tuple(store.iter_observations()) == frames
    assert journal.getvalue() == b"".join(
        encode_frame(frame, version=PROVENANCE_VERSION) for frame in frames
    )
    close(store)
    assert journal.closed


def test_append_does_no_file_io_while_worker_creation_is_blocked():
    factory_started = threading.Event()
    release_factory = threading.Event()
    journal = io.BytesIO()

    def factory():
        factory_started.set()
        assert release_factory.wait(2)
        return journal

    store = storage.ObsRoutingStore(journal_factory=factory)
    assert factory_started.wait(2)
    returned = threading.Event()
    accepted = []
    caller = threading.Thread(
        target=lambda: (accepted.append(store.append(routing())), returned.set())
    )
    caller.start()
    try:
        assert returned.wait(0.5), "append waited for routing-history file creation"
        assert accepted == [True]
    finally:
        release_factory.set()
        caller.join(2)
    finish(store)
    close(store)


def test_queue_pressure_is_terminal_and_never_silently_accepts_ninth_record():
    factory_started = threading.Event()
    release_factory = threading.Event()
    journal = io.BytesIO()

    def factory():
        factory_started.set()
        assert release_factory.wait(2)
        return journal

    store = storage.ObsRoutingStore(journal_factory=factory)
    assert factory_started.wait(2)
    try:
        assert [store.append(routing(index)) for index in range(1, 9)] == [True] * 8
        assert not store.append(routing(9))
        assert store.failed
        assert str(store.error) == "Private OBS routing history could not keep up."
        assert "Input" not in str(store.error)
        release_factory.set()
        with pytest.raises(storage.ObsRoutingStoreError, match="could not keep up"):
            store.wait_ready()
    finally:
        release_factory.set()
        close(store)


def test_short_writes_are_completed_without_corrupting_records():
    class ShortWriter(io.BytesIO):
        def write(self, data):
            return super().write(bytes(data[:3]))

    journal = ShortWriter()
    frame = routing(name="Private source", label="Private bus")
    store = storage.ObsRoutingStore(journal_factory=lambda: journal)
    assert store.append(frame)
    finish(store)
    assert tuple(store.iter_observations()) == (frame,)
    close(store)


def test_failed_write_rolls_back_partial_record_and_sanitizes_error():
    first = routing(1, name="First private")
    second = routing(2, name="Second private")
    first_bytes = encode_frame(first, version=PROVENANCE_VERSION)

    class FailedWriter(io.BytesIO):
        def write(self, data):
            if self.tell() >= len(first_bytes) + 4:
                raise OSError("Second private raw detail")
            return super().write(bytes(data[:4]))

    journal = FailedWriter()
    store = storage.ObsRoutingStore(journal_factory=lambda: journal)
    assert store.append(first)
    assert store.append(second)
    store.finish()
    with pytest.raises(storage.ObsRoutingStoreError, match="storage failed"):
        store.wait_ready()
    assert journal.getvalue() == first_bytes
    assert "Second private raw detail" not in str(store.error)
    close(store)


def test_creation_failure_is_sanitized_and_default_requires_local_filesystem(monkeypatch):
    monkeypatch.setattr(
        storage,
        "require_local_filesystem",
        lambda _path: (_ for _ in ()).throw(storage.LocalFilesystemError("private path")),
    )
    monkeypatch.setattr(
        storage.tempfile,
        "TemporaryFile",
        lambda **_kwargs: pytest.fail("created history on unverified filesystem"),
    )
    store = storage.ObsRoutingStore()
    with pytest.raises(storage.ObsRoutingStoreError, match="storage failed") as caught:
        store.wait_ready()
    assert "private path" not in str(caught.value)
    close(store)


def test_invalid_journal_factory_result_is_a_sanitized_storage_failure():
    store = storage.ObsRoutingStore(journal_factory=lambda: object())
    with pytest.raises(storage.ObsRoutingStoreError, match="storage failed"):
        store.wait_ready()
    assert "journal" not in str(store.error).lower()
    close(store)


def test_cancel_is_nonblocking_while_file_close_is_slow():
    close_started = threading.Event()
    release_close = threading.Event()

    class SlowClose(io.BytesIO):
        def close(self):
            close_started.set()
            assert release_close.wait(2)
            super().close()

    journal = SlowClose()
    store = finish(storage.ObsRoutingStore(journal_factory=lambda: journal))
    returned = threading.Event()
    caller = threading.Thread(target=lambda: (store.close(), returned.set()))
    caller.start()
    try:
        assert close_started.wait(2)
        assert returned.wait(0.5)
        assert not store.wait_closed(0.05)
    finally:
        release_close.set()
        caller.join(2)
    assert store.wait_closed(2)


def test_cancel_waits_for_active_streaming_reader_before_claiming_cleanup():
    journal = io.BytesIO()
    store = storage.ObsRoutingStore(journal_factory=lambda: journal)
    assert store.append(routing(1))
    assert store.append(routing(2))
    finish(store)

    observations = store.iter_observations()
    assert next(observations).revision == 1
    store.close()
    assert not store.wait_closed(0.05)
    observations.close()
    assert store.wait_closed(2)
    assert journal.closed


def test_close_before_drain_suppresses_reading_and_wait_ready_success():
    factory_started = threading.Event()
    release_factory = threading.Event()

    def factory():
        factory_started.set()
        assert release_factory.wait(2)
        return io.BytesIO()

    store = storage.ObsRoutingStore(journal_factory=factory)
    assert factory_started.wait(2)
    assert store.append(routing())
    store.close()
    release_factory.set()
    assert store.wait_closed(2)
    with pytest.raises(TranscriptionCancelled):
        store.wait_ready()
    assert tuple(store.iter_observations()) == ()


def test_wait_ready_honors_external_cancellation_without_taking_ownership():
    factory_started = threading.Event()
    release_factory = threading.Event()
    cancelled = threading.Event()

    def factory():
        factory_started.set()
        assert release_factory.wait(2)
        return io.BytesIO()

    store = storage.ObsRoutingStore(journal_factory=factory)
    assert factory_started.wait(2)
    cancelled.set()
    with pytest.raises(TranscriptionCancelled):
        store.wait_ready(cancelled.is_set)
    assert not store.wait_closed(0), "wait_ready took cleanup ownership"

    store.close()
    release_factory.set()
    assert store.wait_closed(2)


def test_close_failure_is_terminal_sanitized_and_reported_after_wait():
    class FailedClose(io.BytesIO):
        def close(self):
            raise OSError("private cleanup detail")

    journal = FailedClose()
    store = finish(storage.ObsRoutingStore(journal_factory=lambda: journal))
    store.close()
    assert store.wait_closed(2)
    assert store.failed
    assert store.cleanup_failed
    assert str(store.error) == "Private OBS routing history cleanup failed."
    assert "private cleanup detail" not in str(store.error)
    io.BytesIO.close(journal)


def test_iterator_rejects_nonrouting_or_corrupt_records_without_private_bytes():
    journal = io.BytesIO()
    store = storage.ObsRoutingStore(journal_factory=lambda: journal)
    assert store.append(routing(name="Hidden input"))
    finish(store)
    data = bytearray(journal.getvalue())
    data[5] = 1
    journal.seek(0)
    journal.write(data)

    with pytest.raises(storage.ObsRoutingStoreError, match="^Invalid OBS routing history$"):
        tuple(store.iter_observations())
    assert store.failed
    assert "Hidden" not in str(store.error)
    close(store)


def test_iterator_sanitizes_arbitrary_storage_read_failures():
    class FailedRead(io.BytesIO):
        def read(self, _size=-1):
            raise RuntimeError("private source read detail")

    journal = FailedRead()
    store = storage.ObsRoutingStore(journal_factory=lambda: journal)
    assert store.append(routing(name="Hidden input"))
    finish(store)

    with pytest.raises(storage.ObsRoutingStoreError, match="^Invalid OBS routing history$"):
        tuple(store.iter_observations())
    assert "private source read detail" not in str(store.error)
    close(store)


def test_maximum_record_is_bounded_and_streamed_without_materializing_history():
    labels = tuple(BusLabel(bus, "l" * 64) for bus in range(6))
    sources = tuple(
        SourceAssignment(index.to_bytes(16, "big"), "n" * 128, 0x3F)
        for index in range(128)
    )
    frame = RoutingFrame(
        SESSION,
        1,
        2**64 - 1,
        tuple((bus, 2**64 - 1) for bus in range(6)),
        MixSnapshot(5, 0x3F, sources, labels),
    )
    encoded = encode_frame(frame, version=PROVENANCE_VERSION)
    assert len(encoded) == storage.MAX_ROUTING_RECORD_BYTES
    journal = io.BytesIO()
    store = storage.ObsRoutingStore(journal_factory=lambda: journal)
    assert store.append(frame)
    finish(store)
    iterator = store.iter_observations()
    assert next(iterator) == frame
    with pytest.raises(StopIteration):
        next(iterator)
    close(store)


def test_finish_and_nonexact_frames_are_rejected_without_publication():
    store = storage.ObsRoutingStore(journal_factory=io.BytesIO)
    with pytest.raises(TypeError, match="exact RoutingFrame"):
        store.append(object())
    store.finish()
    assert not store.append(routing())
    store.wait_ready()
    assert tuple(store.iter_observations()) == ()
    close(store)
